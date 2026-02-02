# qr_app/management/commands/process_renewals.py

import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings
from yookassa import Configuration, Payment as YooKassaPayment

from qr_app.models import Company, Payment

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Обрабатывает автоматическое продление подписок, которые истекают завтра.'

    def handle(self, *args, **options):
        self.stdout.write("Начинаем процесс продления подписок...")

        Configuration.account_id = settings.YOOKASSA_SHOP_ID
        Configuration.secret_key = settings.YOOKASSA_SECRET_KEY

        tomorrow = date.today() + timedelta(days=1)

        companies_to_renew = Company.objects.filter(
            subscription_expires_on=tomorrow,
            auto_renew=True,
            subscription_plan__isnull=False,
            yookassa_payment_method_id__isnull=False
        ).exclude(yookassa_payment_method_id='')

        if not companies_to_renew.exists():
            self.stdout.write("Нет компаний для продления сегодня.")
            return

        self.stdout.write(f"Найдено {companies_to_renew.count()} компаний для продления.")

        for company in companies_to_renew:
            try:
                # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: НАХОДИМ ПОСЛЕДНИЙ УСПЕШНЫЙ ПЛАТЕЖ ---
                last_successful_payment = Payment.objects.filter(
                    company=company,
                    status='succeeded'
                ).latest('created_at')

                # --- ИСПОЛЬЗУЕМ ДАННЫЕ ИЗ НЕГО, А НЕ ЖЕСТКО ЗАДАННЫЕ ЗНАЧЕНИЯ ---
                amount_to_charge = last_successful_payment.amount
                duration_days = last_successful_payment.duration_days
                plan = last_successful_payment.plan

                if not plan:
                    raise ValueError("У последнего платежа не указан тарифный план.")

                self.stdout.write(
                    f"Пытаемся продлить '{company.name}' на {duration_days} дней за {amount_to_charge} RUB..."
                )

                with transaction.atomic():
                    # 1. Создаем новый локальный платеж
                    local_payment = Payment.objects.create(
                        company=company,
                        plan=plan,
                        amount=amount_to_charge,
                        duration_days=duration_days,
                        status='pending'
                    )

                    # 2. Создаем автоплатеж в YooKassa
                    idempotence_key = str(local_payment.id)
                    yookassa_payment = YooKassaPayment.create({
                        "amount": {
                            "value": str(amount_to_charge),
                            "currency": "RUB"
                        },
                        "capture": True,
                        "payment_method_id": company.yookassa_payment_method_id,
                        "description": f"Автопродление подписки '{plan.name}' ({duration_days} дней) для {company.name}",
                        "metadata": {
                            "local_payment_id": str(local_payment.id)
                        }
                    }, idempotence_key)

                    # 3. Сохраняем ID платежа
                    local_payment.yookassa_payment_id = yookassa_payment.id
                    local_payment.save()

                    self.stdout.write(self.style.SUCCESS(
                        f"Успешно создан автоплатеж для '{company.name}'. Payment ID: {yookassa_payment.id}"
                    ))

            except Payment.DoesNotExist:
                logger.error(f"Не найден последний успешный платеж для компании ID {company.id}, продление отменено.")
                self.stderr.write(f"Не найден платеж для '{company.name}', отключаем автопродление.")
                company.auto_renew = False
                company.save()

            except Exception as e:
                logger.error(f"Ошибка при создании автоплатежа для компании ID {company.id}: {e}")
                self.stderr.write(f"Ошибка для компании '{company.name}': {e}. Отключаем автопродление.")
                company.auto_renew = False
                company.save()

        self.stdout.write("Процесс продления завершен.")

# 0 3 * * * /path/to/your/project/venv/bin/python /path/to/your/project/manage.py process_renewals >> /path/to/your/logs/cron.log 2>&1

# /path/to/your/project/venv/bin/python — обязательно укажите полный путь к Python вашего виртуального окружения.
# /path/to/your/project/manage.py — полный путь к manage.py вашего проекта.
# >> ... 2>&1 — эта часть перенаправляет все выводы (включая ошибки) в лог-файл, чтобы вы могли отслеживать работу скрипта.