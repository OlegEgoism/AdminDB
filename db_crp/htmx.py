from django.shortcuts import render


def is_htmx(request):
    """Проверяет, пришел ли запрос через HTMX."""
    return request.headers.get("HX-Request") == "true"


def render_htmx(request, template_name, context=None, *, partial_template=None):
    """Рендерит partial-шаблон для HTMX-запросов и полный шаблон для обычных."""
    context = context or {}
    if partial_template and is_htmx(request):
        return render(request, partial_template, context)
    return render(request, template_name, context)
