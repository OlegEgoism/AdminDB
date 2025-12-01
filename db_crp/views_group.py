from datetime import datetime
import psycopg2
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from psycopg2 import sql

from .audit_views import (
    group_data, create_audit_log, delete_group_messages_success, delete_group_messages_error,
    create_group_messages_error, create_group_messages_error_pg, create_group_messages_error_info,
    edit_group_messages_error_pg, edit_group_messages_error_name, edit_group_messages_success_name,
    edit_group_messages_error, edit_groups_privileges_tables_success, edit_groups_privileges_tables_error,
    edit_group_messages_error_info, create_group_messages_group_success
)
from .forms import CreateGroupForm, GroupEditForm
from django.shortcuts import render, redirect, get_object_or_404
from .models import GroupLog, ConnectingDB
from django.contrib import messages

created_at = datetime(2000, 1, 1, 0, 0)
updated_at = timezone.now()

# Разрешённые привилегии для таблиц
ALLOWED_TABLE_PRIVILEGES = {'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'}


@login_required
def group_list(request, db_id):
    """Список групп"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    connection_info = get_object_or_404(ConnectingDB, id=db_id)
    temp_db_settings = {
        'dbname': connection_info.name_db,
        'user': connection_info.user_db,
        'password': connection_info.get_decrypted_password(),
        'host': connection_info.host_db,
        'port': connection_info.port_db,
    }
    user_groups_data = []
    try:
        with psycopg2.connect(**temp_db_settings) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT rolname 
                    FROM pg_roles 
                    WHERE rolcanlogin = FALSE AND rolname NOT LIKE 'pg_%';  
                """)
                group_names = [group[0] for group in cursor.fetchall()]
                group_user_counts = {}
                for group in group_names:
                    cursor.execute("""
                        SELECT COUNT(*)
                        FROM pg_auth_members m
                        JOIN pg_roles r ON m.roleid = r.oid
                        WHERE r.rolname = %s;
                    """, [group])
                    count = cursor.fetchone()[0]
                    group_user_counts[group] = count
                group_logs = {log.groupname: log for log in GroupLog.objects.filter(groupname__in=group_user_counts.keys())}
                user_groups_data = [{
                    "groupname": group,
                    "user_count": group_user_counts[group],
                    "created_at": group_logs[group].created_at if group in group_logs else None,
                    "updated_at": group_logs[group].updated_at if group in group_logs else None,
                } for group in group_user_counts.keys()]
    except Exception as e:
        message = f"Ошибка подключения к группам: {str(e)}"
        messages.error(request, message)
        create_audit_log(user_requester, 'info', 'group', user_requester, f"{message}: {str(e)}")
    return render(request, 'groups/group_list.html', {
        'user_groups_data': user_groups_data,
        'db_id': db_id
    })


@login_required
def group_create(request, db_id):
    """Создание группы"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    connection_info = get_object_or_404(ConnectingDB, id=db_id)
    temp_db_settings = {
        'dbname': connection_info.name_db,
        'user': connection_info.user_db,
        'password': connection_info.get_decrypted_password(),
        'host': connection_info.host_db,
        'port': connection_info.port_db,
    }
    if request.method == "POST":
        form = CreateGroupForm(request.POST)
        if form.is_valid():
            group_name = form.cleaned_data['groupname']
            try:
                with psycopg2.connect(**temp_db_settings) as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", [group_name])
                        if cursor.fetchone():
                            message = create_group_messages_error(group_name)
                            messages.error(request, message)
                            create_audit_log(user_requester, 'create', 'group', user_requester, message)
                            return render(request, 'groups/group_create.html', {'form': form, 'db_id': db_id})
                        if group_name.startswith('pg_'):
                            message = create_group_messages_error_pg(group_name)
                            messages.error(request, message)
                            create_audit_log(user_requester, 'create', 'group', user_requester, message)
                            return render(request, 'groups/group_create.html', {'form': form, 'db_id': db_id})
                        cursor.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(group_name)))
                        GroupLog.objects.create(groupname=group_name, created_at=created_at, updated_at=timezone.now())
                        message = create_group_messages_group_success(group_name)
                        messages.success(request, message)
                        create_audit_log(user_requester, 'create', 'group', user_requester, message)
                return redirect('group_list', db_id=db_id)
            except Exception as e:
                message = create_group_messages_error_info(group_name)
                messages.error(request, f"{message}: {str(e)}")
                create_audit_log(user_requester, 'create', 'group', user_requester, f"{message}: {str(e)}")
                return render(request, 'groups/group_create.html', {'form': form, 'db_id': db_id})
    else:
        form = CreateGroupForm()
    return render(request, 'groups/group_create.html', {'form': form, 'db_id': db_id})


@login_required
def group_edit(request, db_id, group_name):
    """Редактирование группы"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    connection_info = get_object_or_404(ConnectingDB, id=db_id)
    temp_db_settings = {
        'dbname': connection_info.name_db,
        'user': connection_info.user_db,
        'password': connection_info.get_decrypted_password(),
        'host': connection_info.host_db,
        'port': connection_info.port_db,
    }
    group_log, created = GroupLog.objects.get_or_create(
        groupname=group_name,
        defaults={'created_at': created_at, 'updated_at': timezone.now()}
    )
    if created:
        message = group_data(group_name)
        messages.success(request, message)
        create_audit_log(user_requester, 'create', 'group', user_requester, message)

    try:
        with psycopg2.connect(**temp_db_settings) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", [group_name])
                if not cursor.fetchone():
                    message = edit_group_messages_error_info(group_name)
                    messages.error(request, message)
                    create_audit_log(user_requester, 'update', 'group', user_requester, message)
                    return redirect('group_list', db_id=db_id)

                if request.method == "POST":
                    form = GroupEditForm(request.POST)
                    if form.is_valid():
                        new_group_name = form.cleaned_data['groupname']
                        if new_group_name.startswith('pg_'):
                            message = edit_group_messages_error_pg(group_name, new_group_name)
                            messages.error(request, message)
                            create_audit_log(user_requester, 'update', 'group', user_requester, message)
                            return render(request, 'groups/group_edit.html', {
                                'form': form, 'db_id': db_id, 'group_name': group_name
                            })
                        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", [new_group_name])
                        if cursor.fetchone():
                            message = edit_group_messages_error_name(group_name, new_group_name)
                            messages.error(request, message)
                            create_audit_log(user_requester, 'update', 'group', user_requester, message)
                            return render(request, 'groups/group_edit.html', {
                                'form': form, 'db_id': db_id, 'group_name': group_name
                            })
                        cursor.execute(
                            sql.SQL("ALTER ROLE {} RENAME TO {}").format(
                                sql.Identifier(group_name),
                                sql.Identifier(new_group_name)
                            )
                        )
                        group_log.groupname = new_group_name
                        group_log.updated_at = timezone.now()
                        group_log.save()
                        message = edit_group_messages_success_name(group_name, new_group_name)
                        messages.success(request, message)
                        create_audit_log(user_requester, 'update', 'group', user_requester, message)
                        return redirect('group_list', db_id=db_id)
                else:
                    form = GroupEditForm(initial={'groupname': group_log.groupname})
    except Exception as e:
        message = edit_group_messages_error(group_name)
        messages.error(request, f"{message}: {str(e)}")
        create_audit_log(user_requester, 'update', 'group', user_requester, f"{message}: {str(e)}")
        return redirect('group_list', db_id=db_id)

    return render(request, 'groups/group_edit.html', {
        'form': form,
        'db_id': db_id,
        'group_name': group_name,
        'group_log': group_log
    })


@login_required
def groups_edit_privileges_tables(request, db_id, group_name):
    """Редактирование прав группы на таблицы"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    connection_info = get_object_or_404(ConnectingDB, id=db_id)
    temp_db_settings = {
        'dbname': connection_info.name_db,
        'user': connection_info.user_db,
        'password': connection_info.get_decrypted_password(),
        'host': connection_info.host_db,
        'port': connection_info.port_db,
    }

    tables_by_schema = {}
    granted_tables = {}

    # Системные схемы, которые НЕ нужно показывать
    SYSTEM_SCHEMAS = {
        "pg_catalog", "information_schema", "pg_toast", "pg_temp_1", "pg_toast_temp_1",
        "gp_toolkit", "pg_bitmapindex", "pg_aoseg", "pg_exttable", "pg_internal",
        "pg_brin", "pglogical", "pg_prewarm"
    }

    try:
        with psycopg2.connect(**temp_db_settings) as conn:
            with conn.cursor() as cursor:

                # 1. Получаем ВСЕ схемы
                cursor.execute("SELECT schema_name FROM information_schema.schemata;")
                schemas_raw = {row[0] for row in cursor.fetchall()}

                # 2. Фильтруем системные и временные
                schemas = sorted([
                    s for s in schemas_raw
                    if s not in SYSTEM_SCHEMAS and not s.startswith("pg_temp")
                ])

                # 3. Получаем таблицы по схемам
                if schemas:
                    cursor.execute("""
                        SELECT schemaname, tablename
                        FROM pg_catalog.pg_tables
                        WHERE schemaname = ANY(%s);
                    """, (schemas,))

                    for schema, table in cursor.fetchall():
                        tables_by_schema.setdefault(schema, {})[table] = set()

                # 4. Получаем права группы
                cursor.execute("""
                    SELECT table_schema, table_name, privilege_type
                    FROM information_schema.role_table_grants
                    WHERE grantee = %s;
                """, [group_name])

                for schema, table, privilege in cursor.fetchall():
                    if schema in tables_by_schema and table in tables_by_schema[schema]:
                        tables_by_schema[schema][table].add(privilege)
                        granted_tables.setdefault(schema, {}).setdefault(table, set()).add(privilege)

    except Exception as e:
        message = edit_group_messages_error(group_name)
        messages.error(request, f"{message}: {str(e)}")
        create_audit_log(user_requester, 'update', 'group', user_requester, f"{message}: {str(e)}")
        return redirect('groups_edit_privileges_tables', db_id=db_id, group_name=group_name)

    # === POST: сохраняем права ===
    if request.method == "POST":
        changes_log = []

        try:
            with psycopg2.connect(**temp_db_settings) as conn:
                with conn.cursor() as cursor:

                    # 1. REVOKE ALL
                    for schema, tables in tables_by_schema.items():
                        for table in tables:
                            cursor.execute(
                                sql.SQL("REVOKE ALL ON TABLE {}.{} FROM {}").format(
                                    sql.Identifier(schema),
                                    sql.Identifier(table),
                                    sql.Identifier(group_name)
                                )
                            )

                    # 2. GRANT выбранных прав
                    for key, raw_permissions in request.POST.items():
                        if not key.startswith("permissions_"):
                            continue

                        schema_name, table_name = key[len("permissions_"):].split(".", 1)

                        if schema_name not in tables_by_schema:
                            continue
                        if table_name not in tables_by_schema[schema_name]:
                            continue

                        new_perms = request.POST.getlist(key)
                        valid_perms = [p for p in new_perms if p in ALLOWED_TABLE_PRIVILEGES]

                        if not valid_perms:
                            continue

                        cursor.execute(
                            sql.SQL("GRANT {} ON TABLE {}.{} TO {}").format(
                                sql.SQL(', ').join(sql.SQL(p) for p in valid_perms),
                                sql.Identifier(schema_name),
                                sql.Identifier(table_name),
                                sql.Identifier(group_name)
                            )
                        )

                        old_perms = granted_tables.get(schema_name, {}).get(table_name, set())
                        new_set = set(valid_perms)
                        added = new_set - old_perms
                        removed = old_perms - new_set

                        if added or removed:
                            changes_log.append(
                                f"Изменены права на {schema_name}.{table_name}: "
                                f"Добавлены: {', '.join(added) if added else '—'} | "
                                f"Удалены: {', '.join(removed) if removed else '—'}"
                            )

            if changes_log:
                message = edit_groups_privileges_tables_success(group_name)
                messages.success(request, message)
                create_audit_log(user_requester, 'update', 'group', user_requester,
                                 message + "\n" + "\n".join(changes_log))

        except Exception as e:
            message = edit_groups_privileges_tables_error(group_name)
            messages.error(request, f"{message}: {str(e)}")
            create_audit_log(user_requester, 'error', 'group', user_requester, f"{message}: {str(e)}")
            return redirect('groups_edit_privileges_tables', db_id=db_id, group_name=group_name)

        return redirect('group_list', db_id=db_id)

    # сортируем схемы
    tables_by_schema = dict(sorted(tables_by_schema.items()))

    return render(request, "groups/groups_edit_privileges_tables.html", {
        'db_id': db_id,
        'group_name': group_name,
        'db_name': connection_info.name_db,
        'schemas': list(tables_by_schema.keys()),  # очищенные схемы
        'tables_by_schema': tables_by_schema,
    })


@login_required
def group_delete(request, db_id, group_name):
    """Удаление группы"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
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
                cursor.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(group_name)))
        group_log = GroupLog.objects.filter(groupname=group_name).first()
        if group_log:
            group_log.delete()
            message = delete_group_messages_success(group_name)
            messages.success(request, message)
            create_audit_log(user_requester, 'delete', 'group', user_requester, message)
    except Exception as e:
        message = delete_group_messages_error(group_name)
        messages.error(request, f"{message}: {str(e)}")
        create_audit_log(user_requester, 'delete', 'group', user_requester, f"{message}: {str(e)}")
    return HttpResponseRedirect(reverse('group_list', kwargs={'db_id': db_id}))


@login_required
def group_info(request, db_id, group_name):
    """Вывод списка пользователей, входящих в группу"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    connection_info = get_object_or_404(ConnectingDB, id=db_id)
    temp_db_settings = {
        'dbname': connection_info.name_db,
        'user': connection_info.user_db,
        'password': connection_info.get_decrypted_password(),
        'host': connection_info.host_db,
        'port': connection_info.port_db,
    }
    users = []
    try:
        with psycopg2.connect(**temp_db_settings) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", [group_name])
                if not cursor.fetchone():
                    message = edit_group_messages_error_info(group_name)
                    messages.error(request, message)
                    create_audit_log(user_requester, 'info', 'group', user_requester, message)
                cursor.execute("""
                    SELECT u.usename 
                    FROM pg_user u
                    JOIN pg_auth_members m ON u.usesysid = m.member
                    JOIN pg_roles g ON m.roleid = g.oid
                    WHERE g.rolname = %s;
                """, [group_name])
                users = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        message = edit_group_messages_error_info(group_name)
        messages.error(request, f"{message}: {str(e)}")
        create_audit_log(user_requester, 'info', 'group', user_requester, f"{message}: {str(e)}")

    group_log, created = GroupLog.objects.get_or_create(
        groupname=group_name,
        defaults={'created_at': created_at, 'updated_at': timezone.now()}
    )
    if created:
        message = group_data(group_name)
        messages.success(request, message)
        create_audit_log(user_requester, 'create', 'group', user_requester, message)

    return render(request, 'groups/group_info.html', {
        'db_id': db_id,
        'group_name': group_name,
        'users': users,
        'user_count': len(users),
        'group_log': group_log
    })
