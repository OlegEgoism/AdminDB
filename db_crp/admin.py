from django.contrib import admin
from django.utils.safestring import mark_safe

from db_crp.models import CustomUser, GroupLog, UserLog, Audit, ConnectingDB, SettingsProject


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    """Администратор"""
    fieldsets = (
        ('ЛИЧНЫЕ ДАННЫЕ', {
            'fields': ('username', 'preview_photo', 'photo', 'email', 'phone_number', 'last_login', 'date_joined',)},),
        ('РАЗРЕШЕНИЯ', {
            'classes': ('collapse',),
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions',)}),
    )
    list_display = 'username', 'preview_photo', 'email', 'phone_number', 'last_login', 'is_active', 'is_staff',
    list_filter = 'is_staff', 'is_active', 'last_login', 'date_joined',
    list_editable = 'is_active',
    search_fields = 'username', 'email', 'phone_number',
    search_help_text = 'Поиск по имени пользователя, адресу электронной почты и номеру телефона'
    readonly_fields = 'last_login', 'date_joined', 'preview_photo',
    date_hierarchy = 'date_joined'
    list_per_page = 20

    def preview_photo(self, obj):
        if obj.photo:
            return mark_safe(f'<img src="{obj.photo.url}" width="80" height="80" style="border-radius: 20%;" />')
        else:
            return 'Нет фотографии'

    preview_photo.short_description = 'Фотография'

    def save_model(self, request, obj, form, change):
        """Проверка, есть ли еще один пользователь с таким же адресом электронной почты"""
        if obj.email:
            if CustomUser.objects.filter(email=obj.email).exclude(pk=obj.pk).exists():
                self.message_user(request, "Этот адрес электронной почты уже связан с другим аккаунтом", level='ERROR')
                return
        super().save_model(request, obj, form, change)


@admin.register(GroupLog)
class GroupLogAdmin(admin.ModelAdmin):
    """Группы в базе данных"""
    list_display = 'groupname', 'created_at', 'updated_at'
    search_fields = 'groupname',
    search_help_text = 'Поиск по имени группы'
    date_hierarchy = 'created_at'
    list_filter = 'created_at', 'updated_at'
    list_per_page = 20


@admin.register(UserLog)
class UserLogAdmin(admin.ModelAdmin):
    """Пользователи в базе данных"""
    list_display = 'username', 'email', 'can_create_db', 'is_superuser', 'inherit', 'create_role', 'login', 'replication', 'bypass_rls', 'created_at', 'updated_at'
    readonly_fields = 'username', 'email', 'can_create_db', 'is_superuser', 'inherit', 'create_role', 'login', 'replication', 'bypass_rls', 'created_at', 'updated_at'
    search_fields = 'username', 'email',
    search_help_text = 'Поиск по имени пользователя и почте'
    date_hierarchy = 'created_at'
    list_filter = 'created_at', 'updated_at', 'can_create_db', 'is_superuser', 'inherit', 'create_role', 'login', 'replication', 'bypass_rls',
    list_per_page = 20


@admin.register(Audit)
class AuditAdmin(admin.ModelAdmin):
    """Группы в базе данных"""
    list_display = 'username', 'action_type', 'entity_type', 'details', 'timestamp'
    readonly_fields = 'username', 'action_type', 'entity_type', 'entity_name', 'timestamp', 'details'
    search_fields = 'username', 'details',
    search_help_text = 'Поиск по имени пользователя и информации из подробно'
    date_hierarchy = 'timestamp'
    list_filter = 'action_type', 'entity_type', 'username'
    list_per_page = 20


@admin.register(ConnectingDB)
class ConnectingDBAdmin(admin.ModelAdmin):
    """Подключение к базе данных"""
    list_display = 'name_db', 'user_db', 'host_db', 'port_db', 'created_at', 'updated_at'
    readonly_fields = 'created_at', 'updated_at'
    search_fields = 'name_db',
    search_help_text = 'Поиск по названию базы данных'
    date_hierarchy = 'created_at'
    list_filter = 'name_db', 'created_at',
    list_per_page = 20


@admin.register(SettingsProject)
class SettingsProjectAdmin(admin.ModelAdmin):
    """Настройка проекта"""
    list_display = 'pagination_size', 'send_email', 'created_at', 'updated_at',
    readonly_fields = 'created_at', 'updated_at'
    date_hierarchy = 'created_at'
    list_per_page = 20

    def has_add_permission(self, request):
        """Запрещает создание более одной записи"""
        return not SettingsProject.objects.exists()
