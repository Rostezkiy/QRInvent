# qr_app/context_processors.py
from .models import Company

def current_company(request):
    # --- НАЧАЛО ИЗМЕНЕНИЙ ---
    # Добавляем проверку, что request.resolver_match вообще существует.
    # Это защищает от ошибок при рендеринге страниц 500/404/403.
    if request.resolver_match and 'company_slug' in request.resolver_match.kwargs:
        company_slug = request.resolver_match.kwargs['company_slug']
        try:
            # Используем .get() вместо прямого доступа к self.company,
            # чтобы избежать лишних запросов, если компания уже была загружена.
            if not hasattr(request, '_cached_company'):
                 request._cached_company = Company.objects.get(slug=company_slug)
            return {'company': request._cached_company}
        except Company.DoesNotExist:
            # Если slug неверный, просто возвращаем пустой словарь.
            # Логика прав доступа во View все равно вернет 404.
            return {}
    # --- КОНЕЦ ИЗМЕНЕНИЙ ---
    return {}