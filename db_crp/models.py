import base64

from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone
from django.utils.timezone import now


class DT(models.Model):
    created_at = models.DateTimeField(verbose_name="Дата создания", default=timezone.now)
    updated_at = models.DateTimeField(verbose_name="Дата изменения", auto_now=True)

    class Meta:
        abstract = True


class CustomUser(AbstractUser):
    """Администраторы"""
    photo = models.ImageField(verbose_name="Фото", upload_to='user_photo/', default='user_photo/default.png', blank=True, null=True)
    phone_number = models.CharField(verbose_name="Телефон", max_length=15, blank=True, null=True)

    def __str__(self):
        return self.username

    class Meta:
        verbose_name = "Администратор"
        verbose_name_plural = "Администраторы"


class GroupLog(DT):
    """Группы в базе данных"""
    groupinfo = models.CharField(verbose_name="Описание группы", max_length=200, blank=True, null=True)
    groupname = models.CharField(verbose_name="Имя группы", max_length=100, unique=True)

    def __str__(self):
        return self.groupname

    class Meta:
        verbose_name = "- Группа в базе данных"
        verbose_name_plural = "- Группы в базе данных"


class UserLog(DT):
    """Пользователи в базе данных"""
    username = models.CharField(verbose_name="Имя пользователя", max_length=150, unique=True)
    email = models.EmailField(verbose_name="Почта", blank=True, null=True, unique=True)
    can_create_db = models.BooleanField(verbose_name="Может создавать БД", default=False)
    is_superuser = models.BooleanField(verbose_name="Суперпользователь", default=False)
    inherit = models.BooleanField(verbose_name="Наследование", default=False)
    create_role = models.BooleanField(verbose_name="Право создания роли", default=False)
    login = models.BooleanField(verbose_name="Право входа", default=True)
    replication = models.BooleanField(verbose_name="Право репликации", default=False)
    bypass_rls = models.BooleanField(verbose_name="Bypass RLS", default=False)

    def __str__(self):
        return self.username

    class Meta:
        verbose_name = "- Пользователь в базе данных"
        verbose_name_plural = "- Пользователи в базе данных"


class Audit(models.Model):
    """Журнал действий"""
    ACTION_TYPES = [
        ('create', 'Создание'),
        ('update', 'Обновление'),
        ('delete', 'Удаление'),
        ('register', 'Регистрация'),
        ('download', 'Скачивание'),
        ('info', 'Информация'),
    ]
    ENTITY_TYPES = [
        ('user', 'Пользователь'),
        ('group', 'Группа'),
        ('database', 'База данных'),
        ('other', 'Другое'),
        ('session', 'Сессия'),
        ('settings', 'Настройки'),
    ]
    username = models.CharField(verbose_name="Имя пользователя", max_length=150)
    action_type = models.CharField(verbose_name="Тип действия", max_length=10, choices=ACTION_TYPES)
    entity_type = models.CharField(verbose_name="Тип объекта", max_length=10, choices=ENTITY_TYPES)
    entity_name = models.CharField(verbose_name="Имя объекта", max_length=150, blank=True, null=True)
    timestamp = models.DateTimeField(verbose_name="Дата и время", default=now)
    details = models.TextField(verbose_name="Подробности", blank=True, null=True)

    def __str__(self):
        return f"{self.timestamp} - {self.username} {self.get_action_type_display()} {self.get_entity_type_display()} '{self.entity_name}'"

    class Meta:
        verbose_name = "Журнал действий"
        verbose_name_plural = "Журнал действий"


class ConnectingDB(DT):
    """Подключение к базе данных"""
    info_db = models.CharField(verbose_name="Название подключения", max_length=100, unique=True)
    name_db = models.CharField(verbose_name="Название базы данных", max_length=150, unique=True)
    user_db = models.CharField(verbose_name="Пользователь", max_length=150)
    password_db = models.CharField(verbose_name="Пароль", max_length=150)
    host_db = models.CharField(verbose_name="Хост", max_length=150)
    port_db = models.CharField(verbose_name="Порт", max_length=150)

    def __str__(self):
        return self.name_db

    def save(self, *args, **kwargs):
        """При сохранении шифруем пароль"""
        if self.password_db:
            self.password_db = base64.b64encode(self.password_db.encode()).decode()
        super().save(*args, **kwargs)

    def get_decrypted_password(self):
        """Расшифровка пароля"""
        try:
            return base64.b64decode(self.password_db).decode()
        except Exception:
            return self.password_db

    def __str__(self):
        return self.name_db

    class Meta:
        verbose_name = "Подключение к базе данных"
        verbose_name_plural = "Подключение к базе данных"


class SettingsProject(DT):
    """Настройка проекта"""
    pagination_size = models.IntegerField(verbose_name="Размер пагинации на странице", default=20, validators=[MinValueValidator(1), MaxValueValidator(500)])
    send_email = models.BooleanField(verbose_name="Отправка сообщений на почту", default=True)

    def __str__(self):
        return f'{self.pagination_size}'

    class Meta:
        verbose_name = "Настройка проекта"
        verbose_name_plural = "Настройка проекта"
