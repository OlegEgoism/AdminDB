from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from db_crp.views import home, register, logout_view
from db_crp.api_views import RegisterAPIView, login_api, logout_api
from db_crp.views_setting import settings_info, audit_log, audit_log_export, session_list, logout_user, settings_project, admin_info, admin_edit, admin_delete
from db_crp.views_group import group_list, group_create, group_edit, group_delete, group_info, groups_edit_privileges_tables
from db_crp.views_user import user_list, user_create, user_info, user_edit, user_delete
from db_crp.views_database import database_list, tables_list, database_connect, database_edit, database_delete, sync_users_and_groups
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
    openapi.Info(
        title="Snippets API",
        default_version='v1',
        description="Test description",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@snippets.local"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)


swagger_urlpatterns = [
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),

    path('api/register/', RegisterAPIView.as_view(), name='api_register'),

    path('api/login/', login_api, name='api-login'),
    path('api/logout/', logout_api, name='api-logout'),


]

urlpatterns = swagger_urlpatterns + [
    path('admin/', admin.site.urls),  # Админка
    path('', home, name='home'),  # Главная
    path('register/', register, name='register'),  # Регистрация пользователя
    path('login/', auth_views.LoginView.as_view(), name='login'),  # Вход пользователя
    path('logout/', logout_view, name='logout'),  # Выход пользователя

    path('audit_log/', audit_log, name='audit_log'),  # Аудит приложения
    path('audit_log/export/', audit_log_export, name='audit_log_export'),  # Аудит приложения экспорт в Excel

    path("settings_info/", settings_info, name="settings_info"),  # Настройки
    path("settings_project/", settings_project, name="settings_project"),  # Настройки проекта
    path("session_list/", session_list, name="session_list"),  # Список сессий пользователей
    path("sessions/logout_user/<str:session_id>/", logout_user, name="logout_user"),  # Деактивация сессии пользователя

    path('admin_info/', admin_info, name='admin_info'),  # Информация об администраторах
    path('admin_edit/<int:admin_id>/', admin_edit, name='admin_edit'),  # Редактирование информация об администраторах
    path('admin_delete/<int:admin_id>/', admin_delete, name='admin_delete'),  # Удаление администратора

    path('group_list/<int:db_id>/', group_list, name='group_list'),  # Список групп
    path('group_create/<int:db_id>/', group_create, name='group_create'),  # Создание группы
    path('group_info/<int:db_id>/<str:group_name>/', group_info, name='group_info'),  # Пользователи в группе
    path('group_edit/<int:db_id>/<str:group_name>/', group_edit, name='group_edit'),  # Редактирование группы
    path('group_delete/<int:db_id>/<str:group_name>/', group_delete, name='group_delete'),  # Удаление группы
    path('groups_edit_privileges_tables/<int:db_id>/<str:group_name>/', groups_edit_privileges_tables, name='groups_edit_privileges_tables'),  # Редактирование привилегий доступа для каждой таблицы

    path('user_list/<int:db_id>/', user_list, name='user_list'),  # Список пользователей
    path('user_create/<int:db_id>/', user_create, name='user_create'),  # Создать пользователя
    path('user_info/<int:db_id>/<str:username>/', user_info, name='user_info'),  # Информация о пользователе
    path('user_edit/<int:db_id>/<str:username>/', user_edit, name='user_edit'),  # Редактирование пользователя
    path('user_delete/<int:db_id>/<str:username>/', user_delete, name='user_delete'),  # Удаление пользователя

    path('database_list/', database_list, name='database_list'),  # Список баз данных
    path('tables_list/<int:db_id>/', tables_list, name='tables_list'),  # Список таблиц в выбранной базе данных
    path('database_connect/', database_connect, name='database_connect'),  # Подключение к базе данных
    path('database_edit/<int:db_id>/', database_edit, name='database_edit'),  # Редактирование подключения к базе данных
    path('database_delete/<int:db_id>/', database_delete, name='database_delete'),  # Удалить подключения к базе данных

    path("sync_users_groups/<int:db_id>/", sync_users_and_groups, name="sync_users_groups"),  # Синхронизация пользователей и групп из базы данных

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
