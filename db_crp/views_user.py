from datetime import datetime
import psycopg2
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMultiAlternatives
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.utils import timezone
from .forms import UserCreateForm
from django.shortcuts import render, redirect, get_object_or_404
from .models import UserLog, SettingsProject, ConnectingDB
from django.contrib import messages
from .audit_views import delete_user_messages_email, delete_user_messages_success, delete_user_messages_error, create_audit_log, create_user_messages_error, \
    create_user_messages_error_email, create_user_messages_success, create_user_messages_email, user_info_error, edit_user_messages_success, \
    edit_user_messages_delete_group_success, edit_user_messages_add_group_success, user_error, create_user_error, create_user_messages_email_error, \
    user_info_all_error, edit_user_messages_db_error

created_at = datetime(2000, 1, 1, 0, 0)
updated_at = timezone.now()


@login_required
def user_list(request, db_id):
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    pagination_size = SettingsProject.objects.first().pagination_size if SettingsProject.objects.exists() else 20
    connection_info = get_object_or_404(ConnectingDB, id=db_id)
    temp_db_settings = {
        'dbname': connection_info.name_db,
        'user': connection_info.user_db,
        'password': connection_info.get_decrypted_password(),
        'host': connection_info.host_db,
        'port': connection_info.port_db,
    }
    search_query = request.GET.get('search', '').strip()
    users_data = []
    try:
        with psycopg2.connect(**temp_db_settings) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT usename FROM pg_catalog.pg_user;")
                all_users = sorted([user[0] for user in cursor.fetchall()])
                user_logs = {log.username: log for log in UserLog.objects.filter(username__in=all_users)}
                for username in all_users:
                    cursor.execute("""
                        SELECT COUNT(*)
                        FROM pg_user u
                        JOIN pg_auth_members m ON u.usesysid = m.member
                        JOIN pg_roles r ON m.roleid = r.oid
                        WHERE u.usename = %s;
                    """, (username,))
                    group_count = cursor.fetchone()[0]
                    log = user_logs.get(username)
                    user_data = {
                        "username": username,
                        "created_at": log.created_at if log else None,
                        "updated_at": log.updated_at if log else None,
                        "group_count": group_count,
                        "email": log.email if log else None,
                    }
                    if search_query:
                        found = False
                        for value in user_data.values():
                            if value is not None and search_query.lower() in str(value).lower():
                                found = True
                                break
                        if not found:
                            continue
                    users_data.append(user_data)
        paginator = Paginator(users_data, pagination_size)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
    except Exception as e:
        message = user_error()
        messages.error(request, f"{message}: {str(e)}")
        create_audit_log(user_requester, 'info', 'create', user_requester, f"{message}: {str(e)}", database_name=connection_info.name_db)
        page_obj = Paginator([], pagination_size).get_page(1)
    return render(request, 'users/user_list.html', {
        'page_obj': page_obj,
        'db_id': db_id,
    })


@login_required
def user_create(request, db_id):
    """Создание пользователя"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    connection_info = get_object_or_404(ConnectingDB, id=db_id)
    temp_db_settings = {
        'dbname': connection_info.name_db,
        'user': connection_info.user_db,
        'password': connection_info.get_decrypted_password(),
        'host': connection_info.host_db,
        'port': connection_info.port_db,
    }
    send_email = SettingsProject.objects.first().send_email if SettingsProject.objects.exists() else False
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            email = form.cleaned_data.get('email', None)
            password = form.cleaned_data['password']
            can_create_db = form.cleaned_data['can_create_db']
            is_superuser = form.cleaned_data['is_superuser']
            inherit = form.cleaned_data['inherit']
            create_role = form.cleaned_data['create_role']
            login = form.cleaned_data.get('login', True)
            replication = form.cleaned_data['replication']
            bypass_rls = form.cleaned_data['bypass_rls']
            try:
                conn = psycopg2.connect(**temp_db_settings)
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", [username])
                if cursor.fetchone():
                    message = create_user_messages_error(username)
                    messages.error(request, message)
                    create_audit_log(user_requester, 'create', 'user', user_requester, message, database_name=connection_info.name_db)
                    return render(request, 'users/user_create.html', {'form': form, 'db_id': db_id})
                if email and UserLog.objects.filter(email=email).exists():
                    message = create_user_messages_error_email(username, email)
                    messages.error(request, message)
                    create_audit_log(user_requester, 'create', 'user', user_requester, message, database_name=connection_info.name_db)
                    return render(request, 'users/user_create.html', {'form': form, 'db_id': db_id})
                privileges = ' '.join([
                    'CREATEDB' if can_create_db else 'NOCREATEDB',
                    'SUPERUSER' if is_superuser else 'NOSUPERUSER',
                    'INHERIT' if inherit else 'NOINHERIT',
                    'CREATEROLE' if create_role else 'NOCREATEROLE',
                    'LOGIN' if login else 'NOLOGIN',
                    'REPLICATION' if replication else 'NOREPLICATION',
                    'BYPASSRLS' if bypass_rls else 'NOBYPASSRLS'
                ])
                cursor.execute(f"CREATE USER {username} WITH PASSWORD %s {privileges};", [password])
                conn.commit()
                UserLog.objects.create(
                    username=username,
                    email=email,
                    can_create_db=can_create_db,
                    is_superuser=is_superuser,
                    inherit=inherit,
                    create_role=create_role,
                    login=login,
                    replication=replication,
                    bypass_rls=bypass_rls
                )
                message = create_user_messages_success(username)
                messages.success(request, message)
                create_audit_log(user_requester, 'create', 'user', user_requester, message, database_name=connection_info.name_db)
                if email and send_email:
                    try:
                        subject = "Ваш аккаунт создан"
                        html_message = render_to_string('send_email/send_user_create.html', {
                            'username': username,
                            'password': password,
                            'can_create_db': can_create_db,
                            'is_superuser': is_superuser,
                            'inherit': inherit,
                            'create_role': create_role,
                            'login': login,
                            'replication': replication,
                            'bypass_rls': bypass_rls
                        })
                        email_message = EmailMultiAlternatives(subject, "", settings.EMAIL_HOST_USER, [email])
                        email_message.attach_alternative(html_message, "text/html")
                        email_message.send()
                        message = create_user_messages_email(username, email, can_create_db, is_superuser, inherit, create_role, login, replication, bypass_rls)
                        messages.success(request, message)
                        create_audit_log(user_requester, 'create', 'user', user_requester, message, database_name=connection_info.name_db)
                    except Exception as email_error:
                        message = create_user_messages_email_error(username)
                        messages.error(request, f"{message}: {str(email_error)}")
                        create_audit_log(user_requester, 'create', 'user', user_requester, f"{message}: {str(email_error)}", database_name=connection_info.name_db)
                cursor.close()
                conn.close()
                return redirect('user_list', db_id=db_id)
            except Exception as e:
                message = create_user_error(username)
                messages.error(request, f"{message}: {str(e)}")
                create_audit_log(user_requester, 'error', 'user', user_requester, f"{message}: {str(e)}", database_name=connection_info.name_db)
                return render(request, 'users/user_create.html', {'form': form, 'db_id': db_id})
    else:
        form = UserCreateForm()
    return render(request, 'users/user_create.html', {
        'form': form,
        'db_id': db_id
    })


@login_required
def user_info(request, db_id, username):
    """Информация о пользователе"""
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
        conn = psycopg2.connect(**temp_db_settings)
        cursor = conn.cursor()
    except Exception as e:
        message = user_info_all_error()
        messages.error(request, f"{message}: {str(e)}")
        create_audit_log(user_requester, 'info', 'user', user_requester, f"{message}: {str(e)}", database_name=connection_info.name_db)
        return redirect('user_list', db_id=db_id)
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", [username])
    user_exists = cursor.fetchone()
    if not user_exists:
        cursor.close()
        conn.close()
        message = user_info_error(username)
        messages.success(request, message)
        create_audit_log(user_requester, 'info', 'user', user_requester, message, database_name=connection_info.name_db)
        return redirect('user_list', db_id=db_id)
    cursor.execute("""
        SELECT 
            r.rolname,         -- Имя роли
            r.oid,             -- ID пользователя
            r.rolcreatedb,     -- Может ли создавать БД
            r.rolsuper,        -- Суперпользователь
            r.rolinherit,      -- Наследование
            r.rolcreaterole,   -- Может создавать роли
            r.rolcanlogin,     -- Может входить в систему
            r.rolreplication,  -- Право репликации
            r.rolbypassrls,    -- Игнорирует RLS
            r.rolpassword      -- Хеш пароля (если установлен)
        FROM pg_roles r
        WHERE r.rolname = %s;
    """, [username])
    user_info = cursor.fetchone()
    cursor.execute("""
        SELECT r.rolname 
        FROM pg_roles r
        JOIN pg_auth_members m ON r.oid = m.roleid
        JOIN pg_roles u ON u.oid = m.member
        WHERE u.rolname = %s;
    """, [username])
    groups = cursor.fetchall()
    user_log = UserLog.objects.filter(username=username).first()
    if user_info:
        group_list = [group[0] for group in groups]
        user_data = {
            'username': user_info[0],
            'user_id': user_info[1],
            'can_create_db': user_info[2],
            'is_superuser': user_info[3],
            'inherit': user_info[4],
            'create_role': user_info[5],
            'login': user_info[6],
            'replication': user_info[7],
            'bypass_rls': user_info[8],
            'password_hash': user_info[9],
            'groups': group_list,
            'group_count': len(group_list),
            'email': user_log.email if user_log else None,
            'created_at': user_log.created_at if user_log else None,
            'updated_at': user_log.updated_at if user_log else None,
        }
    else:
        user_data = None
        message = user_info_error(username)
        messages.success(request, message)
        create_audit_log(user_requester, 'info', 'user', user_requester, message, database_name=connection_info.name_db)
    cursor.close()
    conn.close()
    return render(request, 'users/user_info.html', {
        'user_data': user_data,
        'db_id': db_id
    })


@login_required
def user_edit(request, db_id, username):
    """Редактирование пользователя"""
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
        conn = psycopg2.connect(**temp_db_settings)
        cursor = conn.cursor()
    except Exception as e:
        message = user_info_all_error()
        messages.error(request, f"{message}: {str(e)}")
        create_audit_log(user_requester, 'update', 'user', user_requester, f"{message}: {str(e)}", database_name=connection_info.name_db)
        return redirect('user_list', db_id=db_id)
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", [username])
    user_exists = cursor.fetchone()
    if not user_exists:
        message = edit_user_messages_db_error(username)
        messages.success(request, message)
        create_audit_log(user_requester, 'update', 'user', user_requester, message, database_name=connection_info.name_db)
    user_log = UserLog.objects.filter(username=username).first()
    user_email = user_log.email if user_log else ""
    cursor.execute("""
        SELECT rolcreatedb, rolsuper, rolinherit, rolcreaterole, 
               rolcanlogin, rolreplication, rolbypassrls
        FROM pg_roles 
        WHERE rolname = %s;
    """, [username])
    result = cursor.fetchone()
    role_permissions = {
        'can_create_db': result[0],
        'is_superuser': result[1],
        'inherit': result[2],
        'create_role': result[3],
        'login': result[4],
        'replication': result[5],
        'bypass_rls': result[6]
    } if result else {key: False for key in [
        'can_create_db', 'is_superuser', 'inherit',
        'create_role', 'login', 'replication', 'bypass_rls'
    ]}
    cursor.execute("""
        SELECT r.rolname
        FROM pg_user u
        JOIN pg_auth_members m ON u.usesysid = m.member
        JOIN pg_roles r ON m.roleid = r.oid
        WHERE u.usename = %s;
    """, [username])
    current_groups = {group[0] for group in cursor.fetchall()}
    cursor.execute("""
        SELECT rolname
        FROM pg_roles
        WHERE rolcanlogin = FALSE AND rolname NOT LIKE 'pg_%';
    """)
    all_groups = {group[0] for group in cursor.fetchall()}
    available_groups = all_groups - current_groups
    if request.method == "POST":
        new_email = request.POST.get('email', '')
        if user_log:
            user_log.email = new_email
            user_log.save()
        role_permissions = {
            'can_create_db': 'can_create_db' in request.POST,
            'is_superuser': 'is_superuser' in request.POST,
            'inherit': 'inherit' in request.POST,
            'create_role': 'create_role' in request.POST,
            'login': 'login' in request.POST,
            'replication': 'replication' in request.POST,
            'bypass_rls': 'bypass_rls' in request.POST
        }
        cursor.execute(f"""
            ALTER ROLE {username}
            {'CREATEDB' if role_permissions['can_create_db'] else 'NOCREATEDB'}
            {'SUPERUSER' if role_permissions['is_superuser'] else 'NOSUPERUSER'}
            {'INHERIT' if role_permissions['inherit'] else 'NOINHERIT'}
            {'CREATEROLE' if role_permissions['create_role'] else 'NOCREATEROLE'}
            {'LOGIN' if role_permissions['login'] else 'NOLOGIN'}
            {'REPLICATION' if role_permissions['replication'] else 'NOREPLICATION'}
            {'BYPASSRLS' if role_permissions['bypass_rls'] else 'NOBYPASSRLS'};
        """)
        conn.commit()
        selected_groups = {g.strip() for g in request.POST.getlist('selected_groups') if g.strip()}
        deleted_groups = current_groups - selected_groups
        new_groups = selected_groups - current_groups
        for groupname in deleted_groups:
            if groupname.strip():
                cursor.execute(f"REVOKE {groupname} FROM {username};")
                message = edit_user_messages_delete_group_success(username, groupname)
                messages.success(request, message)
                create_audit_log(user_requester, 'delete', 'user', user_requester, message, database_name=connection_info.name_db)
        for groupname in new_groups:
            if groupname.strip():
                cursor.execute(f"GRANT {groupname} TO {username};")
                message = edit_user_messages_add_group_success(username, groupname)
                messages.success(request, message)
                create_audit_log(user_requester, 'create', 'user', user_requester, message, database_name=connection_info.name_db)
        conn.commit()
        cursor.close()
        conn.close()
        message = edit_user_messages_success(username)
        messages.success(request, message)
        create_audit_log(user_requester, 'update', 'user', user_requester, message, database_name=connection_info.name_db)
        return redirect('user_list', db_id=db_id)
    cursor.close()
    conn.close()
    return render(request, 'users/user_edit.html', {
        'db_id': db_id,
        'username': username,
        'role_permissions': role_permissions,
        'user_groups': sorted(current_groups),
        'available_groups': sorted(available_groups),
        'user_email': user_email
    })


@login_required
def user_delete(request, db_id, username):
    """Удаление пользователя"""
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
        conn = psycopg2.connect(**temp_db_settings)
        cursor = conn.cursor()
    except Exception as e:
        message = user_info_all_error()
        messages.error(request, f"{message}: {str(e)}")
        create_audit_log(user_requester, 'delete', 'user', user_requester, f"{message}: {str(e)}", database_name=connection_info.name_db)
        return redirect('user_list', db_id=db_id)
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", [username])
    user_exists = cursor.fetchone()
    if not user_exists:
        cursor.close()
        conn.close()
        message = user_info_error(username)
        messages.error(request, message)
        create_audit_log(user_requester, 'delete', 'user', user_requester, message, database_name=connection_info.name_db)
        return redirect('user_list', db_id=db_id)
    user_log = UserLog.objects.filter(username=username).first()
    user_email = user_log.email if user_log else None
    try:
        cursor.execute(f"REASSIGN OWNED BY {username} TO {connection_info.user_db};")
        cursor.execute(f"DROP OWNED BY {username};")
        cursor.execute(f"DROP USER IF EXISTS {username};")
        conn.commit()
        if user_log:
            user_log.delete()
            message = delete_user_messages_success(username)
            messages.success(request, message)
            create_audit_log(user_requester, 'delete', 'user', user_requester, message, database_name=connection_info.name_db)
        send_email = SettingsProject.objects.first().send_email if SettingsProject.objects.exists() else False
        if user_email and send_email:
            subject = "Ваш аккаунт был удален"
            html_message = render_to_string('send_email/send_user_delete.html', {'username': username})
            email_message = EmailMultiAlternatives(subject, "", settings.EMAIL_HOST_USER, [user_email])
            email_message.attach_alternative(html_message, "text/html")
            email_message.send()
            message = delete_user_messages_email(username, send_email)
            messages.success(request, message)
            create_audit_log(user_requester, 'delete', 'user', user_requester, message, database_name=connection_info.name_db)
    except Exception as e:
        conn.rollback()
        message = delete_user_messages_error(username)
        messages.success(request, message)
        create_audit_log(user_requester, 'delete', 'user', user_requester, f"{message}: {str(e)}", database_name=connection_info.name_db)
    finally:
        cursor.close()
        conn.close()
    return redirect('user_list', db_id=db_id)
