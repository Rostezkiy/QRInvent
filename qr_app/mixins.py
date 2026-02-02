# qr_app/mixins.py

from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse  # <-- ДОБАВЛЕН ИМПОРТ
from django.contrib import messages  # <--- ДОБАВЬТЕ ЭТУ СТРОКУ
from .models import Membership, Company


class CompanyRequiredMixin:
    """
    Миксин для View, работающих в контексте определенной компании.
    1. Находит компанию по 'company_slug' из URL.
    2. Проверяет, является ли текущий пользователь ее сотрудником.
    3. Сохраняет объект компании в self.company для использования в View.
    """
    company = None

    def dispatch(self, request, *args, **kwargs):
        company_slug = kwargs.get('company_slug')
        # Находим компанию по slug или возвращаем 404
        self.company = get_object_or_404(Company, slug=company_slug)

        # Проверяем, состоит ли пользователь в этой компании
        if not request.user.is_authenticated or not Membership.objects.filter(user=request.user,
                                                                              company=self.company).exists():
            # Если нет - доступ запрещен
            raise PermissionDenied("Вы не состоите в этой компании.")

        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(AccessMixin):
    """
    Миксин, который проверяет, что пользователь имеет роль 'admin'.
    Предполагается, что он используется ПОСЛЕ CompanyRequiredMixin.
    """

    def dispatch(self, request, *args, **kwargs):
        # Используем свойство is_admin из вашей кастомной модели User
        if not request.user.is_admin:
            raise PermissionDenied("У вас нет прав администратора для выполнения этого действия.")
        return super().dispatch(request, *args, **kwargs)


class CompanyQuerysetMixin:
    """
    Автоматически фильтрует queryset по текущей компании (self.company).
    Требует, чтобы модель имела поле 'company'.
    Используется вместе с CompanyRequiredMixin.
    """

    def get_queryset(self):
        # Убедимся, что self.model определен
        if self.model is None:
            raise ImproperlyConfigured(f"{self.__class__.__name__} is missing a model.")

        return self.model.objects.filter(company=self.company)


class SuccessURLForCompanyMixin:
    """
    Предоставляет метод для генерации URL для редиректа с company_slug.
    """
    list_view_name = None  # Например, 'qr_app:template_list'

    def get_success_url(self):
        if not self.list_view_name:
            raise NotImplementedError("Необходимо определить атрибут 'list_view_name' в классе представления.")
        return reverse(self.list_view_name, kwargs={'company_slug': self.company.slug})


class ActiveSubscriptionRequiredMixin:
    """
    Миксин, который проверяет, активна ли подписка у компании.
    Предполагается, что он используется ПОСЛЕ CompanyRequiredMixin.
    Перенаправляет на страницу выбора тарифа, если подписка неактивна.
    """

    def dispatch(self, request, *args, **kwargs):
        # self.company должен быть уже установлен миксином CompanyRequiredMixin
        if not self.company.has_active_subscription:
            messages.warning(self.request,
                             "Ваша подписка неактивна. Пожалуйста, выберите тариф, чтобы продолжить работу.")

            # Строим URL для редиректа с текущим company_slug
            subscription_url = reverse('qr_app:subscription_select', kwargs={'company_slug': self.company.slug})
            return redirect(subscription_url)

        return super().dispatch(request, *args, **kwargs)
