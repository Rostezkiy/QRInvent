# qr_app/services.py

import json
from datetime import date
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from yookassa import Configuration, Payment as YooKassaPayment

from .models import (
    ServiceRecord, ServiceRecordPhoto, Payment, Company,
    SubscriptionPlan, Equipment
)


@transaction.atomic
def create_service_record_from_checklist(equipment: Equipment, user, form_data: dict, uploaded_files: list):
    """
    Сервисная функция для создания записи в журнале обслуживания.
    1. Создает объект ServiceRecord.
    2. Сохраняет связанные фотографии.
    3. Обновляет current_checklist_state у оборудования.

    Принимает:
    - equipment: объект Equipment
    - user: объект User
    - form_data: словарь cleaned_data из формы
    - uploaded_files: список загруженных файлов
    """

    # Отделяем данные для сохранения в JSON из словаря form_data
    checklist_values = {}
    for key, value in form_data.items():
        # Пропускаем поля, которые не относятся к данным чек-листа
        if key in ['images']:
            continue
        # Сериализуем дату в строку ISO
        if isinstance(value, date):
            checklist_values[key] = value.isoformat()
        else:
            checklist_values[key] = value

    # 1. Создаем запись в журнале
    record = ServiceRecord.objects.create(
        equipment=equipment,
        author=user,
        checklist_data=checklist_values
    )

    # 2. Сохраняем фотографии из uploaded_files
    for image_file in uploaded_files:
        ServiceRecordPhoto.objects.create(record=record, image=image_file)

    # 3. Обновляем "текущее состояние" оборудования
    equipment.current_checklist_state = checklist_values
    equipment.save(update_fields=['current_checklist_state'])

    return record


@transaction.atomic
def activate_free_plan(company: Company, plan: SubscriptionPlan) -> None:
    """Активирует бесплатный тарифный план для компании."""
    company.subscription_plan = plan
    # Триал-период для бесплатного плана, например, 14 дней.
    company.subscription_expires_on = timezone.now().date() + timezone.timedelta(days=14)
    company.auto_renew = False
    company.yookassa_payment_method_id = None
    company.save()


def create_yookassa_payment(company: Company, plan: SubscriptionPlan, period: str, request) -> str:
    """
    Создает локальный объект Payment и платеж в YooKassa.
    Возвращает URL для редиректа на страницу оплаты.
    """
    if period == 'monthly':
        amount = plan.price_monthly
        duration_days = 30
    elif period == 'annually':
        amount = plan.price_annually
        duration_days = 365
    else:
        raise ValueError("Неверный период оплаты. Допустимо 'monthly' или 'annually'.")

    local_payment = Payment.objects.create(
        company=company, plan=plan, amount=amount,
        duration_days=duration_days, status='pending'
    )

    Configuration.account_id = settings.YOOKASSA_SHOP_ID
    Configuration.secret_key = settings.YOOKASSA_SECRET_KEY

    idempotence_key = str(local_payment.id)
    return_url = request.build_absolute_uri(
        reverse('qr_app:payment_result', kwargs={'company_slug': company.slug})
    )

    yookassa_payment = YooKassaPayment.create({
        "amount": {"value": str(amount), "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "capture": True,
        "description": f"Оплата подписки '{plan.name}' для {company.name}",
        "metadata": {"local_payment_id": str(local_payment.id)},
        "save_payment_method": False
    }, idempotence_key)

    local_payment.yookassa_payment_id = yookassa_payment.id
    local_payment.save()

    return yookassa_payment.confirmation.confirmation_url


@transaction.atomic
def process_successful_payment(payment: Payment, payment_info: YooKassaPayment):
    """
    Обрабатывает успешный платеж: обновляет статус и активирует подписку.
    """
    payment.status = 'succeeded'
    payment.metadata = json.loads(payment_info.json())
    payment.save()

    company = payment.company
    company.subscription_plan = payment.plan

    if payment_info.payment_method and payment_info.payment_method.id:
        company.yookassa_payment_method_id = payment_info.payment_method.id
        company.auto_renew = True
    else:
        company.auto_renew = False

    start_date = timezone.now().date()
    if company.has_active_subscription and company.subscription_expires_on:
        start_date = company.subscription_expires_on

    company.subscription_expires_on = start_date + timezone.timedelta(days=payment.duration_days)
    company.save()