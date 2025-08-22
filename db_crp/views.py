from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from .audit_views import user_register, create_audit_log
from .forms import CustomUserRegistrationForm
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import get_user_model

User = get_user_model()


def home(request):
    """Главная"""
    windows_user = getpass.getuser()  # Получаем имя пользователя Windows
    return render(request, 'home.html', {'windows_user': windows_user})


def register(request):
    """Регистрация пользователя"""
    user_requester = request.user.username if request.user.is_authenticated else "Аноним"
    if request.method == 'POST':
        form = CustomUserRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user)
            message = user_register(user.username, user.email, user.phone_number)
            messages.success(request, message)
            create_audit_log(user_requester, 'register', 'user', user.username, message)
            return redirect('home')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"Ошибка в поле {form.fields[field].label}: {error}")
    else:
        form = CustomUserRegistrationForm()
    return render(request, 'registration/register.html', {'form': form})


@login_required
def logout_view(request):
    """Выход пользователя"""
    logout(request)
    return redirect('home')



import os
import getpass
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

@login_required
def get_windows_user(request):
    username = getpass.getuser()  # Или os.getlogin()
    return JsonResponse({"username": username})
