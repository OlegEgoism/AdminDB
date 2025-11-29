from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from .models import CustomUser, ConnectingDB, SettingsProject


class CustomUserRegistrationForm(UserCreationForm):
    """Регистрация администратора"""
    phone_number = forms.CharField(max_length=15, help_text="Формат с кодом телефона")
    photo = forms.ImageField(required=False)

    class Meta:
        model = CustomUser
        fields = "username", "email", "phone_number", "photo", "password1", "password2"

    def clean_email(self):
        """Проверка уникальности email"""
        email = self.cleaned_data.get("email")
        if email == None or email == "":
            raise forms.ValidationError("Почта обязательна для заполнения.")

        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("Почта уже используется другим администратором.")
        return email


class UserCreateForm(forms.Form):
    """Создания пользователя"""
    username = forms.CharField(label="Логин", max_length=150)
    email = forms.EmailField(label="Почта")
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput)
    can_create_db = forms.BooleanField(label="Может создавать БД", required=False)
    is_superuser = forms.BooleanField(label="Суперпользователь", required=False)
    inherit = forms.BooleanField(label="Наследование", required=False)
    create_role = forms.BooleanField(label="Право создания роли", required=False)
    login = forms.BooleanField(label="Право входа", required=False, initial=True)
    replication = forms.BooleanField(label="Право репликации", required=False)
    bypass_rls = forms.BooleanField(label="Bypass RLS", required=False)


class UserEditForm(forms.Form):
    """Редактирование пользователя"""
    email = forms.EmailField(label="Почта", required=False)
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput, required=False)
    can_create_db = forms.BooleanField(label="Может создавать БД", required=False)
    is_superuser = forms.BooleanField(label="Суперпользователь", required=False)
    inherit = forms.BooleanField(label="Наследование", required=False)
    create_role = forms.BooleanField(label="Право создания роли", required=False)
    login = forms.BooleanField(label="Право входа", required=False)
    replication = forms.BooleanField(label="Право репликации", required=False)
    bypass_rls = forms.BooleanField(label="Bypass RLS", required=False)


class GroupEditForm(forms.Form):
    """Редактирование группы"""
    groupname = forms.CharField(label="Название", max_length=150)


class CreateGroupForm(forms.Form):
    """Создание группы"""
    groupname = forms.CharField(label="Название", max_length=150)


class DatabaseConnectForm(forms.ModelForm):
    """Подключение к базе данных"""

    class Meta:
        model = ConnectingDB
        fields = ["name_db", "user_db", "password_db", "host_db", "port_db"]
        labels = {
            "name_db": "Название базы данных",
            "user_db": "Пользователь",
            "password_db": "Пароль",
            "host_db": "Хост",
            "port_db": "Порт",
        }
        widgets = {
            "password_db": forms.PasswordInput(),
        }


class SettingsProjectForm(forms.ModelForm):
    """Настройки проекта"""
    pagination_size = models.IntegerField(
        verbose_name="Размер пагинации на странице",
        default=20,
        validators=[MinValueValidator(1), MaxValueValidator(200)]
    )
    send_email = models.BooleanField(verbose_name="Отправка сообщений на почту", default=True)

    class Meta:
        model = SettingsProject
        fields = "pagination_size", "send_email"


class CustomUserForm(forms.ModelForm):
    """Редактирование администратора"""
    class Meta:
        model = CustomUser
        fields = "phone_number", "email", "is_active", "is_superuser"
