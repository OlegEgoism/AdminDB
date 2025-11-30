from django.contrib.auth import get_user_model
from rest_framework import serializers


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
