import psycopg2
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from psycopg2 import sql
from rest_framework import permissions, status
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView
from django.contrib.auth import authenticate, login, logout
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from db_backends.greenplum.base import DatabaseWrapper
from .audit_views import (
    connect_data_base_success,
    create_audit_log,
    delete_data_base_success,
    sync_data_base_error,
    sync_data_base_success,
    user_register,
)
from .models import ConnectingDB, GroupLog, SettingsProject, UserLog
from .serializers import (
    ConnectingDBSerializer,
    CustomUserRegistrationSerializer,
    GroupLogSerializer,
    SettingsProjectSerializer,
    UserLogSerializer,
)
User = get_user_model()


class RegisterAPIView(APIView):
    """API методы регистрации пользователя для Swagger."""

    permission_classes = [permissions.AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    @swagger_auto_schema(
        operation_description="Регистрация нового пользователя.",
        request_body=CustomUserRegistrationSerializer,
        responses={
            201: openapi.Response(
                description="Пользователь успешно создан",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "username": openapi.Schema(type=openapi.TYPE_STRING),
                        "email": openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_EMAIL),
                        "phone_number": openapi.Schema(type=openapi.TYPE_STRING),
                        "message": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
            400: openapi.Response("Ошибки валидации"),
        },
    )
    def post(self, request):
        serializer = CustomUserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            login(request, user)
            message = user_register(user.username, user.email, user.phone_number)
            create_audit_log(
                request.user.username if request.user.is_authenticated else "Аноним",
                "register",
                "user",
                user.username,
                message,
            )
            return Response(
                {
                    "username": user.username,
                    "email": user.email,
                    "phone_number": user.phone_number,
                    "message": message,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method='post',
    operation_description="Аутентификация пользователя и создание сессии.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["username", "password"],
        properties={
            "username": openapi.Schema(type=openapi.TYPE_STRING, description="Имя пользователя"),
            "password": openapi.Schema(
                type=openapi.TYPE_STRING, format=openapi.FORMAT_PASSWORD, description="Пароль пользователя"
            ),
        },
    ),
    responses={
        status.HTTP_200_OK: openapi.Response(
            description="Успешный вход",
            examples={"application/json": {"detail": "Успешный вход.", "username": "admin"}},
        ),
        status.HTTP_400_BAD_REQUEST: openapi.Response(
            description="Не указаны учетные данные",
            examples={"application/json": {"detail": "Необходимо указать имя пользователя и пароль."}},
        ),
        status.HTTP_401_UNAUTHORIZED: openapi.Response(
            description="Неверные учетные данные",
            examples={"application/json": {"detail": "Неверные учетные данные."}},
        ),
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def login_api(request):
    """API вход пользователя."""

    username = request.data.get("username")
    password = request.data.get("password")

    if not username or not password:
        return Response(
            {"detail": "Необходимо указать имя пользователя и пароль."}, status=status.HTTP_400_BAD_REQUEST
        )

    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response({"detail": "Неверные учетные данные."}, status=status.HTTP_401_UNAUTHORIZED)

    login(request, user)
    return Response({"detail": "Успешный вход.", "username": user.username}, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method='post',
    operation_description="Завершение текущей пользовательской сессии.",
    responses={
        status.HTTP_200_OK: openapi.Response(
            description="Успешный выход",
            examples={"application/json": {"detail": "Успешный выход."}},
        ),
        status.HTTP_401_UNAUTHORIZED: openapi.Response(
            description="Пользователь не авторизован",
            examples={"application/json": {"detail": "Учетная запись не авторизована."}},
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_api(request):
    """API выход пользователя."""

    logout(request)
    return Response({"detail": "Успешный выход."}, status=status.HTTP_200_OK)


class DatabaseListAPI(APIView):
    """API для работы с подключениями к базам данных."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def _segments_info(connection_info):
        temp_db_settings = {
            "dbname": connection_info.name_db,
            "user": connection_info.user_db,
            "password": connection_info.get_decrypted_password(),
            "host": connection_info.host_db,
            "port": connection_info.port_db,
        }
        info = {
            "segments": [],
            "is_available": False,
            "primary_count": 0,
            "mirror_count": 0,
            "statuses": [],
            "modes": [],
            "error": None,
        }
        try:
            with psycopg2.connect(**temp_db_settings) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM pg_catalog.pg_class WHERE relname = 'gp_segment_configuration'
                        );
                        """
                    )
                    has_segments_view = cursor.fetchone()[0]
                    if not has_segments_view:
                        info["error"] = "Нет информации о сегментах"
                        return info

                    cursor.execute(
                        """
                        SELECT content, role, preferred_role, status, mode, hostname, address, port
                        FROM gp_segment_configuration
                        ORDER BY content, role;
                        """
                    )
                    rows = cursor.fetchall()
                    info["segments"] = [
                        {
                            "content": row[0],
                            "role": row[1],
                            "preferred_role": row[2],
                            "status": row[3],
                            "mode": row[4],
                            "hostname": row[5],
                            "address": row[6],
                            "port": row[7],
                        }
                        for row in rows
                    ]
                    info["primary_count"] = sum(1 for row in rows if row[1] == "p")
                    info["mirror_count"] = sum(1 for row in rows if row[1] == "m")
                    info["statuses"] = sorted({row[3] for row in rows if row[3]})
                    info["modes"] = sorted({row[4] for row in rows if row[4]})
                    info["is_available"] = True
        except Exception as exc:  # pragma: no cover - безопасное описание ошибки
            info["error"] = str(exc)
        return info

    @swagger_auto_schema(
        operation_description="Список подключений к базам данных с дополнительной информацией о сегментах.",
        manual_parameters=[
            openapi.Parameter(
                "search",
                openapi.IN_QUERY,
                description="Фильтр по названию базы данных",
                type=openapi.TYPE_STRING,
            )
        ],
        responses={
            status.HTTP_200_OK: openapi.Response(
                description="Успешный ответ",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "count": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "results": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(type=openapi.TYPE_OBJECT),
                        ),
                    },
                ),
            )
        },
    )
    def get(self, request):
        search_query = request.GET.get("search", "")
        qs = ConnectingDB.objects.all().order_by("name_db")
        if search_query:
            qs = qs.filter(Q(name_db__icontains=search_query) | Q(info_db__icontains=search_query))
        pagination_size = SettingsProject.objects.first().pagination_size if SettingsProject.objects.exists() else 20
        paginator_slice = qs[:pagination_size]
        serializer = ConnectingDBSerializer(paginator_slice, many=True)
        results = []
        for db_data, obj in zip(serializer.data, paginator_slice):
            db_data = dict(db_data)
            db_data["segments"] = self._segments_info(obj)
            results.append(db_data)
        return Response({"count": qs.count(), "results": results})

    @swagger_auto_schema(
        operation_description="Создание нового подключения к базе данных.",
        request_body=ConnectingDBSerializer,
        responses={
            status.HTTP_201_CREATED: ConnectingDBSerializer,
            status.HTTP_400_BAD_REQUEST: "Ошибки валидации",
        },
    )
    def post(self, request):
        serializer = ConnectingDBSerializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            message = connect_data_base_success(
                instance.name_db, instance.user_db, instance.port_db, instance.host_db, instance.info_db
            )
            create_audit_log(
                request.user.username if request.user.is_authenticated else "Аноним",
                "create",
                "database",
                instance.name_db,
                message,
                database_name=instance.name_db,
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DatabaseDetailAPI(APIView):
    """Получение и изменение конкретного подключения к базе данных."""

    permission_classes = [IsAuthenticated]

    def _get_object(self, db_id):
        return get_object_or_404(ConnectingDB, id=db_id)

    @swagger_auto_schema(
        operation_description="Получить информацию о подключении к базе данных.",
        responses={status.HTTP_200_OK: ConnectingDBSerializer},
    )
    def get(self, request, db_id):
        instance = self._get_object(db_id)
        serializer = ConnectingDBSerializer(instance)
        data = serializer.data
        data["segments"] = DatabaseListAPI._segments_info(instance)
        return Response(data)

    @swagger_auto_schema(
        operation_description="Обновить подключение к базе данных.",
        request_body=ConnectingDBSerializer,
        responses={status.HTTP_200_OK: ConnectingDBSerializer, status.HTTP_400_BAD_REQUEST: "Ошибки валидации"},
    )
    def put(self, request, db_id):
        instance = self._get_object(db_id)
        serializer = ConnectingDBSerializer(instance, data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            message = connect_data_base_success(
                instance.name_db, instance.user_db, instance.port_db, instance.host_db, instance.info_db
            )
            create_audit_log(
                request.user.username if request.user.is_authenticated else "Аноним",
                "update",
                "database",
                instance.name_db,
                message,
                database_name=instance.name_db,
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Частичное обновление подключения к базе данных.",
        request_body=ConnectingDBSerializer,
        responses={status.HTTP_200_OK: ConnectingDBSerializer, status.HTTP_400_BAD_REQUEST: "Ошибки валидации"},
    )
    def patch(self, request, db_id):
        instance = self._get_object(db_id)
        serializer = ConnectingDBSerializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            message = connect_data_base_success(
                instance.name_db, instance.user_db, instance.port_db, instance.host_db, instance.info_db
            )
            create_audit_log(
                request.user.username if request.user.is_authenticated else "Аноним",
                "update",
                "database",
                instance.name_db,
                message,
                database_name=instance.name_db,
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Удалить подключение к базе данных.",
        responses={status.HTTP_204_NO_CONTENT: "Успешное удаление"},
    )
    def delete(self, request, db_id):
        instance = self._get_object(db_id)
        name_db = instance.name_db
        instance.delete()
        message = delete_data_base_success(name_db, instance.user_db, instance.port_db, instance.host_db, instance.info_db)
        create_audit_log(
            request.user.username if request.user.is_authenticated else "Аноним",
            "delete",
            "database",
            name_db,
            message,
            database_name=name_db,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class TablesListAPI(APIView):
    """Получение информации о таблицах в выбранной базе данных."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Информация о таблицах в базе данных (схема, размер, владелец).",
        responses={status.HTTP_200_OK: "Таблицы успешно получены", status.HTTP_404_NOT_FOUND: "База не найдена"},
    )
    def get(self, request, db_id):
        connection_info = get_object_or_404(ConnectingDB, id=db_id)
        db_settings = settings.DATABASES.get("default", {})
        temp_db_settings = {
            "ENGINE": "db_backends.greenplum",
            "NAME": connection_info.name_db,
            "USER": connection_info.user_db,
            "PASSWORD": connection_info.get_decrypted_password(),
            "HOST": connection_info.host_db,
            "PORT": connection_info.port_db,
            "ATOMIC_REQUESTS": db_settings.get("ATOMIC_REQUESTS"),
            "CONN_HEALTH_CHECKS": db_settings.get("CONN_HEALTH_CHECKS"),
            "CONN_MAX_AGE": db_settings.get("CONN_MAX_AGE"),
            "AUTOCOMMIT": db_settings.get("AUTOCOMMIT"),
            "OPTIONS": db_settings.get("OPTIONS"),
            "TIME_ZONE": db_settings.get("TIME_ZONE"),
        }

        tables_info = []
        db_size = "Неизвестно"

        try:
            temp_connection = DatabaseWrapper(temp_db_settings, alias="temp_connection")
            temp_connection.connect()
            with temp_connection.cursor() as cursor:
                cursor.execute(
                    """
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
                    """
                )
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

                cursor.execute(f"SELECT pg_size_pretty(pg_database_size('{connection_info.name_db}'));")
                db_size = cursor.fetchone()[0]
        except Exception as exc:
            create_audit_log(
                request.user.username if request.user.is_authenticated else "Аноним",
                "error",
                "database",
                connection_info.name_db,
                f"Ошибка при загрузке таблиц: {exc}",
                database_name=connection_info.name_db,
            )
            return Response(
                {"detail": f"Ошибка при загрузке таблиц: {exc}"}, status=status.HTTP_400_BAD_REQUEST
            )
        finally:
            if "temp_connection" in locals():
                temp_connection.close()

        schemas = sorted({t["schema"] for t in tables_info})
        owners = sorted({t["owner"] for t in tables_info if t["owner"]})
        return Response(
            {
                "db_name": connection_info.name_db,
                "db_id": db_id,
                "db_size": db_size,
                "tables": tables_info,
                "schemas": schemas,
                "owners": owners,
            }
        )


class TemporaryTableDeleteAPI(APIView):
    """Удаление временной таблицы через API."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Удалить временную таблицу из базы данных.",
        responses={status.HTTP_200_OK: "Таблица удалена", status.HTTP_400_BAD_REQUEST: "Ошибка при удалении"},
    )
    def delete(self, request, db_id, schema_name, table_name):
        user_requester = request.user.username if request.user.is_authenticated else "Аноним"
        connection_info = get_object_or_404(ConnectingDB, id=db_id)
        temp_db_settings = {
            "dbname": connection_info.name_db,
            "user": connection_info.user_db,
            "password": connection_info.get_decrypted_password(),
            "host": connection_info.host_db,
            "port": connection_info.port_db,
        }
        try:
            with psycopg2.connect(**temp_db_settings) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
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
                        """,
                        (schema_name, table_name),
                    )
                    row = cursor.fetchone()
                    if row is None or (isinstance(row, tuple) and len(row) == 0):
                        message = f"Таблица {schema_name}.{table_name} не найдена"
                        create_audit_log(
                            user_requester,
                            "error",
                            "table",
                            f"{schema_name}.{table_name}",
                            message,
                            database_name=connection_info.name_db,
                        )
                        return Response({"detail": message}, status=status.HTTP_404_NOT_FOUND)

                    (_, _, _, persist_temp, schema_temp, name_tmp, name_temp) = row
                    is_temp = persist_temp or schema_temp or name_tmp or name_temp
                    if not is_temp:
                        message = "Можно удалять только временные таблицы"
                        create_audit_log(
                            user_requester,
                            "error",
                            "table",
                            f"{schema_name}.{table_name}",
                            message,
                            database_name=connection_info.name_db,
                        )
                        return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)

                    cursor.execute(
                        sql.SQL("DROP TABLE IF EXISTS {}.{};").format(
                            sql.Identifier(schema_name), sql.Identifier(table_name)
                        )
                    )
                    success_message = f"Временная таблица {schema_name}.{table_name} успешно удалена"
                    create_audit_log(
                        user_requester,
                        "delete",
                        "table",
                        f"{schema_name}.{table_name}",
                        success_message,
                        database_name=connection_info.name_db,
                    )
                    return Response({"detail": success_message})
        except Exception as exc:
            message = f"Ошибка при удалении таблицы {schema_name}.{table_name}: {exc}"
            create_audit_log(
                user_requester,
                "error",
                "table",
                f"{schema_name}.{table_name}",
                message,
                database_name=connection_info.name_db,
            )
            return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)


class SyncUsersAndGroupsAPI(APIView):
    """Синхронизация пользователей и групп из базы данных."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Синхронизировать пользователей и группы из выбранной базы данных.",
        responses={status.HTTP_200_OK: "Синхронизация завершена", status.HTTP_400_BAD_REQUEST: "Ошибка"},
    )
    def post(self, request, db_id):
        user_requester = request.user.username if request.user.is_authenticated else "Аноним"
        connection_info = get_object_or_404(ConnectingDB, id=db_id)
        temp_db_settings = {
            "dbname": connection_info.name_db,
            "user": connection_info.user_db,
            "password": connection_info.get_decrypted_password(),
            "host": connection_info.host_db,
            "port": connection_info.port_db,
        }
        conn = None
        cursor = None
        try:
            conn = psycopg2.connect(**temp_db_settings)
            cursor = conn.cursor()
            existing_users = set(UserLog.objects.values_list("username", flat=True))
            existing_groups = set(GroupLog.objects.values_list("groupname", flat=True))

            cursor.execute(
                """
                SELECT
                    rolname, rolcreatedb, rolsuper, rolinherit,
                    rolcreaterole, rolcanlogin, rolreplication, rolbypassrls
                FROM pg_catalog.pg_roles;
                """
            )
            users = cursor.fetchall()
            new_users = []
            for user in users:
                (username, can_create_db, is_superuser, inherit, create_role, login, replication, bypass_rls) = user
                if username not in existing_users:
                    new_users.append(
                        UserLog(
                            username=username,
                            can_create_db=can_create_db,
                            is_superuser=is_superuser,
                            inherit=inherit,
                            create_role=create_role,
                            login=login,
                            replication=replication,
                            bypass_rls=bypass_rls,
                        )
                    )
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

            message = sync_data_base_success(temp_db_settings["dbname"])
            create_audit_log(
                user_requester,
                "info",
                "database",
                user_requester,
                message,
                database_name=connection_info.name_db,
            )
            return Response({"detail": message})
        except Exception as exc:
            message = sync_data_base_error(temp_db_settings["dbname"])
            create_audit_log(
                user_requester,
                "error",
                "database",
                user_requester,
                f"{message}: {exc}",
                database_name=connection_info.name_db,
            )
            return Response({"detail": f"{message}: {exc}"}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            if cursor is not None:
                cursor.close()
            if conn is not None:
                conn.close()


class SettingsProjectAPI(APIView):
    """Получение и изменение настроек проекта."""

    permission_classes = [IsAuthenticated]

    def _get_settings(self):
        instance = SettingsProject.objects.first()
        if instance is None:
            instance = SettingsProject.objects.create()
        return instance

    @swagger_auto_schema(
        operation_description="Получить текущие настройки проекта.",
        responses={status.HTTP_200_OK: SettingsProjectSerializer},
    )
    def get(self, request):
        instance = self._get_settings()
        serializer = SettingsProjectSerializer(instance)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Изменить настройки проекта.",
        request_body=SettingsProjectSerializer,
        responses={status.HTTP_200_OK: SettingsProjectSerializer, status.HTTP_400_BAD_REQUEST: "Ошибки валидации"},
    )
    def put(self, request):
        instance = self._get_settings()
        serializer = SettingsProjectSerializer(instance, data=request.data)
        if serializer.is_valid():
            serializer.save()
            create_audit_log(
                request.user.username if request.user.is_authenticated else "Аноним",
                "update",
                "settings",
                "settings",
                "Изменение настроек проекта через API",
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserLogAPI(APIView):
    """Список сохраненных пользователей базы данных."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Получить список пользователей, синхронизированных из базы данных.",
        responses={status.HTTP_200_OK: UserLogSerializer(many=True)},
    )
    def get(self, request):
        users = UserLog.objects.all().order_by("username")
        return Response(UserLogSerializer(users, many=True).data)


class GroupLogAPI(APIView):
    """Список сохраненных групп базы данных."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Получить список групп, синхронизированных из базы данных.",
        responses={status.HTTP_200_OK: GroupLogSerializer(many=True)},
    )
    def get(self, request):
        groups = GroupLog.objects.all().order_by("groupname")
        return Response(GroupLogSerializer(groups, many=True).data)