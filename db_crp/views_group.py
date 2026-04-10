from datetime import datetime
import psycopg2
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from .audit_views import group_data, create_audit_log, delete_group_messages_success, delete_group_messages_error, create_group_messages_error, \
    create_group_messages_error_pg, create_group_messages_error_info, edit_group_messages_error_pg, edit_group_messages_error_name, \
    edit_group_messages_success_name, edit_group_messages_error, edit_groups_privileges_tables_success, edit_groups_privileges_tables_error, \
    create_group_messages_group_success, edit_group_messages_error_info
from .db_connection_settings import get_db_connection_settings
from .forms import CreateGroupForm, GroupEditForm
from django.shortcuts import render, redirect, get_object_or_404
from .models import GroupLog, ConnectingDB
from django.contrib import messages
from .htmx import render_htmx

created_at = datetime(2000, 1, 1, 0, 0)
updated_at = timezone.now()


@login_required
def group_list(request, db_id):
    """Список групп"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    temp_db_settings = get_db_connection_settings(db_id)
    search_query = request.GET.get("q", "").strip().lower()
    user_groups_data = []
    try:
        conn = psycopg2.connect(**temp_db_settings)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT rolname 
            FROM pg_roles 
            WHERE rolcanlogin = FALSE AND rolname NOT LIKE 'pg_%';  
        """)
        group_names = [group[0] for group in cursor.fetchall()]
        if search_query:
            group_names = [group for group in group_names if search_query in group.lower()]
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
        cursor.close()
        conn.close()
    except Exception as e:
        message = f"Ошибка подключения к группам: {str(e)}"
        messages.error(request, message)
        create_audit_log(user_requester, 'info', 'group', user_requester, f"{message}: {str(e)}")
    return render_htmx(request, 'groups/group_list.html', {
        'user_groups_data': user_groups_data,
        'db_id': db_id,
        'search_query': search_query
    }, partial_template='groups/_group_list_content.html')


@login_required
def group_create(request, db_id):
    """Создание группы"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    temp_db_settings = get_db_connection_settings(db_id)
    if request.method == "POST":
        form = CreateGroupForm(request.POST)
        if form.is_valid():
            group_name = form.cleaned_data['groupname']
            try:
                conn = psycopg2.connect(**temp_db_settings)
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", [group_name])
                existing_group = cursor.fetchone()
                if existing_group:
                    message = create_group_messages_error(group_name)
                    messages.error(request, message)
                    create_audit_log(user_requester, 'create', 'group', user_requester, message)
                    return render(request, 'groups/group_create.html', {'form': form, 'db_id': db_id})
                if group_name.startswith('pg_'):
                    message = create_group_messages_error_pg(group_name)
                    messages.error(request, message)
                    create_audit_log(user_requester, 'create', 'group', user_requester, message)
                    return render(request, 'groups/group_create.html', {
                        'form': form,
                        'db_id': db_id
                    })
                cursor.execute(f"CREATE ROLE {group_name};")
                conn.commit()
                GroupLog.objects.create(groupname=group_name, created_at=created_at, updated_at=timezone.now())  # Записываем в модель
                message = create_group_messages_group_success(group_name)
                messages.success(request, message)
                create_audit_log(user_requester, 'create', 'group', user_requester, message)
                cursor.close()
                conn.close()
                return redirect('group_list', db_id=db_id)
            except Exception as e:
                message = create_group_messages_error_info(group_name)
                messages.error(request, f"{message}: {str(e)}")
                create_audit_log(user_requester, 'create', 'group', user_requester, f"{message}: {str(e)}")
                return render(request, 'groups/group_create.html', {
                    'form': form,
                    'db_id': db_id
                })
    else:
        form = CreateGroupForm()
    return render(request, 'groups/group_create.html', {
        'form': form,
        'db_id': db_id
    })


@login_required
def group_edit(request, db_id, group_name):
    """Редактирование группы"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    temp_db_settings = get_db_connection_settings(db_id)
    group_log, created = GroupLog.objects.get_or_create(
        groupname=group_name,
        defaults={'created_at': created_at, 'updated_at': timezone.now()}
    )
    if created:
        message = group_data(group_name)
        messages.success(request, message)
        create_audit_log(user_requester, 'create', 'group', user_requester, message)
    try:
        conn = psycopg2.connect(**temp_db_settings)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", [group_name])
        existing_group = cursor.fetchone()
        if not existing_group:
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
                        'form': form,
                        'db_id': db_id,
                        'group_name': group_name
                    })
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", [new_group_name])
                existing_new_group = cursor.fetchone()
                if existing_new_group:
                    message = edit_group_messages_error_name(group_name, new_group_name)
                    messages.error(request, message)
                    create_audit_log(user_requester, 'update', 'group', user_requester, message)
                    return render(request, 'groups/group_edit.html', {
                        'form': form,
                        'db_id': db_id,
                        'group_name': group_name
                    })
                cursor.execute(f"ALTER ROLE {group_name} RENAME TO {new_group_name};")
                conn.commit()
                group_log.groupname = new_group_name
                group_log.updated_at = timezone.now()
                group_log.save()
                message = edit_group_messages_success_name(group_name, new_group_name)
                messages.success(request, message)
                create_audit_log(user_requester, 'update', 'group', user_requester, message)
                return redirect('group_list', db_id=db_id)
        else:
            form = GroupEditForm(initial={'groupname': group_log.groupname})
        cursor.close()
        conn.close()
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
    temp_db_settings = get_db_connection_settings(db_id)
    tables_by_schema = {}
    granted_tables = {}
    schemas = []
    try:
        conn = psycopg2.connect(**temp_db_settings)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'pg_temp_1', 'pg_toast_temp_1');
        """)
        schemas = [row[0] for row in cursor.fetchall()]
        cursor.execute("""
            SELECT schemaname, tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname IN %s;
        """, (tuple(schemas),))
        for schema, table in cursor.fetchall():
            if schema not in tables_by_schema:
                tables_by_schema[schema] = {}
            tables_by_schema[schema][table] = set()
        cursor.execute("""
            SELECT table_schema, table_name, privilege_type
            FROM information_schema.role_table_grants
            WHERE grantee = %s;
        """, [group_name])
        for schema, table, privilege in cursor.fetchall():
            if schema in tables_by_schema and table in tables_by_schema[schema]:
                tables_by_schema[schema][table].add(privilege)
                if schema not in granted_tables:
                    granted_tables[schema] = {}
                if table not in granted_tables[schema]:
                    granted_tables[schema][table] = set()
                granted_tables[schema][table].add(privilege)
        cursor.close()
        conn.close()
    except Exception as e:
        message = edit_group_messages_error(group_name)
        messages.error(request, f"{message}: {str(e)}")
        create_audit_log(user_requester, 'update', 'group', user_requester, f"{message}: {str(e)}")
        return redirect('groups_edit_privileges_tables', db_id=db_id, group_name=group_name)
    if request.method == "POST":
        table_permissions = {}
        for schema, tables in tables_by_schema.items():
            for table in tables:
                table_permissions[f"{schema}.{table}"] = request.POST.getlist(f"permissions_{schema}.{table}")
        changes_log = []
        try:
            conn = psycopg2.connect(**temp_db_settings)
            cursor = conn.cursor()
            for schema, tables in tables_by_schema.items():
                for table in tables:
                    cursor.execute(f"REVOKE ALL ON {schema}.{table} FROM {group_name};")
            for table, new_permissions in table_permissions.items():
                if new_permissions:
                    permissions_str = ", ".join(new_permissions)
                    cursor.execute(f"GRANT {permissions_str} ON {table} TO {group_name};")
                    schema, table_name = table.split(".")
                    old_permissions = granted_tables.get(schema, {}).get(table_name, set())
                    new_permissions = set(new_permissions)
                    added_perms = new_permissions - old_permissions
                    removed_perms = old_permissions - new_permissions
                    if added_perms or removed_perms:
                        changes_log.append(f"Изменены права на {schema}.{table_name}: "
                                           f"Добавлены: {', '.join(added_perms) if added_perms else '—'} | "
                                           f"Удалены: {', '.join(removed_perms) if removed_perms else '—'}")
            conn.commit()
            cursor.close()
            conn.close()
            if changes_log:
                message = edit_groups_privileges_tables_success(group_name)
                messages.success(request, message)
                create_audit_log(user_requester, 'update', 'group', user_requester, message + "\n".join(changes_log))
        except Exception as e:
            message = edit_groups_privileges_tables_error(group_name)
            messages.error(request, f"{message}: {str(e)}")
            create_audit_log(user_requester, 'update', 'group', user_requester, f"{message}: {str(e)}")
            return redirect('groups_edit_privileges_tables', db_id=db_id, group_name=group_name)
        return redirect('group_list', db_id=db_id)
    tables_by_schema = dict(sorted(tables_by_schema.items()))
    return render(request, 'groups/groups_edit_privileges_tables.html', {
        'db_id': db_id,
        'group_name': group_name,
        'db_name': connection_info.name_db,
        'schemas': schemas,
        'tables_by_schema': tables_by_schema,
    })


@login_required
def group_delete(request, db_id, group_name):
    """Удаление группы"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    temp_db_settings = get_db_connection_settings(db_id)
    try:
        conn = psycopg2.connect(**temp_db_settings)
        cursor = conn.cursor()
        cursor.execute(f'DROP ROLE IF EXISTS "{group_name}";')
        conn.commit()
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
    finally:
        cursor.close()
        conn.close()
    return HttpResponseRedirect(reverse('group_list', kwargs={'db_id': db_id}))


@login_required
def group_info(request, db_id, group_name):
    """Вывод списка пользователей, входящих в группу"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    temp_db_settings = get_db_connection_settings(db_id)
    try:
        conn = psycopg2.connect(**temp_db_settings)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", [group_name])
        group_exists = cursor.fetchone()
        if not group_exists:
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
        cursor.close()
        conn.close()
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
