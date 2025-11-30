from django.contrib.auth import get_user_model
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView
from django.contrib.auth import authenticate, login, logout
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from .audit_views import create_audit_log, user_register
from .serializers import CustomUserRegistrationSerializer

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
