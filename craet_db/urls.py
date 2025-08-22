"""
URL configuration for craet_db project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from db_crp.views import home, register, logout_view, get_windows_user
from db_crp.views_group import group_list, group_create, group_edit, group_delete, group_info, groups_edit_privileges, groups_edit_privileges_tables
from db_crp.views_setting import settings_info, audit_log, export_audit_log, session_list, logout_user, settings_project
from db_crp.views_user import user_list, user_create, user_info, user_edit, user_delete
from db_crp.views_database import database_list, tables_list, database_connect, database_edit, database_delete


urlpatterns = [
    path('admin/', admin.site.urls),  # Админка
    path('', home, name='home'),  # Главная
    path('register/', register, name='register'),  # Регистрация пользователя
    path('login/', auth_views.LoginView.as_view(), name='login'),  # Вход пользователя
    path('logout/', logout_view, name='logout'),  # Выход пользователя

    path("settings_info/", settings_info, name="settings_info"),  # Настройки
    path('audit_log/', audit_log, name='audit_log'),  # Аудит приложения
    path('settings/export/', export_audit_log, name='export_audit_log'),  # Экспорт данных журнала аудита в Excel
    path("sessions/", session_list, name="session_list"),  # Список сессий пользователей
    path("sessions/logout/<str:session_id>/", logout_user, name="logout_user"),  # Деактивация сессии пользователя
    path("settings_project/", settings_project, name="settings_project"),  # Настройки проекта


    path('group_list/', group_list, name='group_list'),  # Список групп
    path('group_create/', group_create, name='group_create'),  # Создание группы
    path('groups_edit/<str:group_name>/', group_edit, name='group_edit'),  # Редактирование группы
    path('groups_edit_privileges/<str:group_name>/', groups_edit_privileges, name='groups_edit_privileges'),  # Редактирование привилегий доступа
    path('groups_edit_privileges_tables/<str:group_name>/<int:db_id>/', groups_edit_privileges_tables, name='groups_edit_privileges_tables'),  # Редактирование привилегий доступа для каждой таблицы
    path('group_delete/<str:group_name>/', group_delete, name='group_delete'),  # Удаление группы
    path('group_info/<str:group_name>/', group_info, name='group_info'),  # Пользователи в группе

    path('user_list/', user_list, name='user_list'),  # Список пользователей
    path('user_create/', user_create, name='user_create'),  # Создать пользователя
    path('user_info/<str:username>/', user_info, name='user_info'),  # Информация о пользователе
    path('user_edit/<str:username>/', user_edit, name='user_edit'),  # Редактирование пользователя
    path('user_delete/<str:username>/', user_delete, name='user_delete'),  # Удаление пользователя

    path('database_list/', database_list, name='database_list'),  # Список баз данных
    path('tables_list/<int:db_id>/', tables_list, name='tables_list'),  # Список таблиц в выбранной базе данных
    path('database_connect/', database_connect, name='database_connect'),  # Подключение к базе данных
    path('database_edit/<int:db_id>/', database_edit, name='database_edit'),  # Редактирование подключения к базе данных
    path('database_delete/<int:db_id>/', database_delete, name='database_delete'),  # Удалить подключения к базе данных

    path('get_windows_user/', get_windows_user, name='get_windows_user'),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
