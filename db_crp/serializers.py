from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import ConnectingDB, GroupLog, SettingsProject, UserLog

CustomUser = get_user_model()


class CustomUserRegistrationSerializer(serializers.ModelSerializer):
    """Сериализатор регистрации администратора."""

    password1 = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUser
        fields = ["username", "email", "phone_number", "photo", "password1", "password2"]

    def validate_email(self, value):
        if not value:
            raise serializers.ValidationError("Почта обязательна для заполнения.")
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("Почта уже используется другим администратором.")
        return value

    def validate(self, attrs):
        password1 = attrs.get("password1")
        password2 = attrs.get("password2")
        if password1 != password2:
            raise serializers.ValidationError({"password2": "Пароли должны совпадать."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password1")
        validated_data.pop("password2", None)
        user = CustomUser(**validated_data)
        user.set_password(password)
        user.save()
        return user


class ConnectingDBSerializer(serializers.ModelSerializer):
    """Сериализатор подключения к базе данных."""

    decrypted_password = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ConnectingDB
        fields = [
            "id",
            "info_db",
            "name_db",
            "user_db",
            "password_db",
            "host_db",
            "port_db",
            "created_at",
            "updated_at",
            "decrypted_password",
        ]
        extra_kwargs = {
            "password_db": {"write_only": True},
        }

    def get_decrypted_password(self, obj):
        return obj.get_decrypted_password()


class GroupLogSerializer(serializers.ModelSerializer):
    """Сериализатор групп, выгруженных из базы данных."""

    class Meta:
        model = GroupLog
        fields = ["id", "groupname", "groupinfo", "created_at", "updated_at"]


class UserLogSerializer(serializers.ModelSerializer):
    """Сериализатор пользователей, выгруженных из базы данных."""

    class Meta:
        model = UserLog
        fields = [
            "id",
            "username",
            "email",
            "can_create_db",
            "is_superuser",
            "inherit",
            "create_role",
            "login",
            "replication",
            "bypass_rls",
            "created_at",
            "updated_at",
        ]


class SettingsProjectSerializer(serializers.ModelSerializer):
    """Сериализатор настроек проекта."""

    class Meta:
        model = SettingsProject
        fields = ["id", "pagination_size", "send_email", "created_at", "updated_at"]