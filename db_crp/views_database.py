import psycopg2
from psycopg2 import sql
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.db.backends.postgresql.base import DatabaseWrapper
from django.conf import settings
from .audit_views import connect_data_base_success, create_audit_log, delete_data_base_success, delete_data_base_error, update_data_base_success, \
    sync_data_base_success, sync_data_base_error
from .forms import DatabaseConnectForm
from .models import ConnectingDB, UserLog, GroupLog, SettingsProject
from django.db.utils import OperationalError
from django.core.paginator import Paginator
from django.db.models import Q

@login_required
def database_list(request):
    """Список баз данных с пагинацией и поиском"""
    pagination_size = SettingsProject.objects.first().pagination_size if SettingsProject.objects.exists() else 20
    search_query = request.GET.get('search', '')
    if search_query:
        databases = ConnectingDB.objects.filter(Q(name_db__icontains=search_query)).order_by('id')
    else:
        databases = ConnectingDB.objects.all().order_by('id')
    paginator = Paginator(databases, pagination_size)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    databases_info = [{"db": db} for db in page_obj]
    return render(request, "databases/database_list.html", {
        "databases_info": databases_info,
        "page_obj": page_obj,
        "search_query": search_query
    })




@login_required
def tables_list(request, db_id):
    """Список таблиц в выбранной базе данных (с отображением владельца таблиц)"""

    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    connection_info = get_object_or_404(ConnectingDB, id=db_id)

    db_settings = settings.DATABASES.get('default', {})

    temp_db_settings = {
        'ENGINE': 'db_backends.greenplum',
        'NAME': connection_info.name_db,
        'USER': connection_info.user_db,
        'PASSWORD': connection_info.get_decrypted_password(),
        'HOST': connection_info.host_db,
        'PORT': connection_info.port_db,
        'ATOMIC_REQUESTS': db_settings.get('ATOMIC_REQUESTS'),
        'CONN_HEALTH_CHECKS': db_settings.get('CONN_HEALTH_CHECKS'),
        'CONN_MAX_AGE': db_settings.get('CONN_MAX_AGE'),
        'AUTOCOMMIT': db_settings.get('AUTOCOMMIT'),
        'OPTIONS': db_settings.get('OPTIONS'),
        'TIME_ZONE': db_settings.get('TIME_ZONE'),
    }

    tables_info = []
    db_size = "Неизвестно"

    try:
        temp_connection = DatabaseWrapper(temp_db_settings, alias="temp_connection")
        temp_connection.connect()

        with temp_connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    n.nspname AS schemaname,
                    c.relname AS tablename,
                    pg_size_pretty(pg_total_relation_size(c.oid)) AS size,
                    (c.relpersistence = 't'
                        OR c.relname ILIKE 'tmp_%'
                        OR c.relname ILIKE 'temp_%'
                        OR n.nspname LIKE 'pg_temp%') AS is_temporary,
                    pg_get_userbyid(c.relowner) AS owner
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'r'
                  AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                ORDER BY n.nspname, c.relname;
            """)

            rows = cursor.fetchall()

            tables_info = [
                {
                    "schema": row[0],
                    "name": row[1],
                    "size": row[2],
                    "is_temp": row[3],
                    "owner": row[4] if row[4] else "",
                }
                for row in rows
            ]

            cursor.execute(
                f"SELECT pg_size_pretty(pg_database_size('{connection_info.name_db}'));"
            )
            db_size = cursor.fetchone()[0]

    except Exception as e:
        message = f"Ошибка при загрузке таблиц: {str(e)}"
        messages.error(request, message)
        tables_info = []

    finally:
        if 'temp_connection' in locals():
            temp_connection.close()

    # ============================
    # УНИКАЛЬНЫЕ схемы и авторы
    # ============================
    schemas = sorted({t["schema"] for t in tables_info})
    owners = sorted({t["owner"] for t in tables_info if t["owner"]})

    return render(request, "databases/tables_info.html", {
        "db_name": connection_info.name_db,
        "db_size": db_size,
        "db_id": db_id,
        "tables_info": tables_info,
        "schemas": schemas,
        "owners": owners,
    })





@login_required
def delete_temp_table(request, db_id, schema_name, table_name):
    """Удаление временной таблицы (устойчиво к pg_temp_* особенностям)"""

    user_requester = request.user.username if request.user.is_authenticated else "Аноним"

    if request.method != "POST":
        messages.error(request, "Неподдерживаемый метод запроса")
        return redirect('tables_list', db_id=db_id)

    connection_info = get_object_or_404(ConnectingDB, id=db_id)
    temp_db_settings = {
        'dbname': connection_info.name_db,
        'user': connection_info.user_db,
        'password': connection_info.get_decrypted_password(),
        'host': connection_info.host_db,
        'port': connection_info.port_db,
    }

    try:
        with psycopg2.connect(**temp_db_settings) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        c.oid,
                        c.relname,
                        n.nspname,
                        c.relpersistence = 't' AS persist_temp,
                        n.nspname LIKE 'pg_temp%%' AS schema_temp,
                        c.relname ILIKE 'tmp_%%' AS name_tmp,
                        c.relname ILIKE 'temp_%%' AS name_temp
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = %s
                      AND c.relname = %s
                      AND c.relkind IN ('r','t');
                """, (schema_name, table_name))
                row = cursor.fetchone()
                if row is None:
                    message = f"Таблица {schema_name}.{table_name} не найдена"
                    messages.error(request, message)
                    create_audit_log(user_requester, 'error', 'table',
                                     f"{schema_name}.{table_name}", message)
                    return redirect('tables_list', db_id=db_id)
                if isinstance(row, tuple) and len(row) == 0:
                    message = (
                        f"PostgreSQL вернул пустые данные по таблице "
                        f"{schema_name}.{table_name} — невозможно определить её тип"
                    )
                    messages.error(request, message)
                    create_audit_log(user_requester, 'error', 'table',
                                     f"{schema_name}.{table_name}", message)
                    return redirect('tables_list', db_id=db_id)
                (_, _, _, persist_temp, schema_temp, name_tmp, name_temp) = row
                is_temp = (
                    persist_temp
                    or schema_temp
                    or name_tmp
                    or name_temp
                )
                if not is_temp:
                    message = "Можно удалять только временные таблицы"
                    messages.error(request, message)
                    create_audit_log(user_requester, 'error', 'table',
                                     f"{schema_name}.{table_name}", message)
                    return redirect('tables_list', db_id=db_id)
                cursor.execute(
                    sql.SQL("DROP TABLE IF EXISTS {}.{};").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(table_name)
                    )
                )
                success_message = (
                    f"Временная таблица {schema_name}.{table_name} успешно удалена"
                )
                messages.success(request, success_message)
                create_audit_log(user_requester, 'delete', 'table',
                                 f"{schema_name}.{table_name}", success_message)
    except Exception as e:
        message = f"Ошибка при удалении таблицы {schema_name}.{table_name}: {str(e)}"
        messages.error(request, message)
        create_audit_log(user_requester, 'error', 'table',
                         f"{schema_name}.{table_name}", message)
    return redirect('tables_list', db_id=db_id)





def database_connect(request):
    """Подключение к базе данных"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    if request.method == "POST":
        form = DatabaseConnectForm(request.POST)
        if form.is_valid():
            form.save()
            name_db = form.cleaned_data['name_db']
            user_db = form.cleaned_data['user_db']
            port_db = form.cleaned_data['port_db']
            host_db = form.cleaned_data['host_db']
            message = connect_data_base_success(name_db, user_db, port_db, host_db)
            messages.success(request, message)
            create_audit_log(user_requester, 'create', 'database', name_db, message)
            return redirect('database_list')
    else:
        form = DatabaseConnectForm()
    return render(request, "databases/database_connect.html", {"form": form})


@login_required
def database_edit(request, db_id):
    """Редактирование подключения к базе данных"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    database = get_object_or_404(ConnectingDB, id=db_id)
    if request.method == "POST":
        form = DatabaseConnectForm(request.POST, instance=database)
        if form.is_valid():
            form.save()
            name_db = form.cleaned_data['name_db']
            user_db = form.cleaned_data['user_db']
            port_db = form.cleaned_data['port_db']
            host_db = form.cleaned_data['host_db']
            message = update_data_base_success(name_db, user_db, port_db, host_db)
            messages.success(request, message)
            create_audit_log(user_requester, 'update', 'database', name_db, message)
            return redirect('database_list')
    else:
        form = DatabaseConnectForm(instance=database)
    return render(request, "databases/database_edit.html", {
        "form": form,
        "database": database
    })


@login_required
def database_delete(request, db_id):
    """Удаление подключения к базе данных"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    database = get_object_or_404(ConnectingDB, id=db_id)
    name_db = database.name_db
    user_db = database.user_db
    port_db = database.port_db
    host_db = database.host_db
    try:
        database.delete()
        message = delete_data_base_success(name_db, user_db, port_db, host_db)
        messages.success(request, message)
        create_audit_log(user_requester, 'delete', 'database', name_db, message)
    except Exception as e:
        message = delete_data_base_error(name_db, user_db, port_db, host_db)
        messages.success(request, f"{message}: {str(e)}")
        create_audit_log(user_requester, 'delete', 'database', name_db, f"{message}: {str(e)}")
    return redirect('database_list')


@login_required
def sync_users_and_groups(request, db_id):
    """Синхронизация пользователей и групп из базы данных"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    connection_info = ConnectingDB.objects.get(id=db_id)
    temp_db_settings = {
        'dbname': connection_info.name_db,
        'user': connection_info.user_db,
        'password': connection_info.get_decrypted_password(),
        'host': connection_info.host_db,
        'port': connection_info.port_db,
    }
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(**temp_db_settings)
        cursor = conn.cursor()
        existing_users = set(UserLog.objects.values_list('username', flat=True))
        existing_groups = set(GroupLog.objects.values_list('groupname', flat=True))
        cursor.execute("""
            SELECT
                rolname, rolcreatedb, rolsuper, rolinherit,
                rolcreaterole, rolcanlogin, rolreplication, rolbypassrls
            FROM pg_catalog.pg_roles;
        """)
        users = cursor.fetchall()
        new_users = []
        for user in users:
            (
                username, can_create_db, is_superuser,
                inherit, create_role, login, replication, bypass_rls
            ) = user
            if username not in existing_users:
                new_users.append(UserLog(
                    username=username,
                    can_create_db=can_create_db,
                    is_superuser=is_superuser,
                    inherit=inherit,
                    create_role=create_role,
                    login=login,
                    replication=replication,
                    bypass_rls=bypass_rls,
                ))
        if new_users:
            UserLog.objects.bulk_create(new_users)
        cursor.execute("SELECT groname FROM pg_catalog.pg_group;")
        groups = cursor.fetchall()
        new_groups = []
        for group in groups:
            groupname = group[0]
            if groupname not in existing_groups:
                new_groups.append(GroupLog(groupname=groupname))
        if new_groups:
            GroupLog.objects.bulk_create(new_groups)
        message = sync_data_base_success(temp_db_settings['dbname'])
        messages.success(request, message)
        create_audit_log(user_requester, 'info', 'database', user_requester, message)
    except Exception as e:
        message = sync_data_base_error(temp_db_settings['dbname'])
        messages.error(request, f"{message}: {str(e)}")
        create_audit_log(user_requester, 'error', 'database', user_requester, f"{message}: {str(e)}")
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
    return redirect("database_list")

