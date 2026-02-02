# qr_app/models.py
import uuid
from pathlib import Path

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import UniqueConstraint
from django.utils import timezone
from slugify import slugify


class User(AbstractUser):
    """Кастомная модель пользователя с добавлением роли."""

    class Role(models.TextChoices):
        ADMIN = 'admin', 'Администратор'
        TECHNICIAN = 'technician', 'Техник'

    first_name = None
    last_name = None
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.TECHNICIAN)

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN


class SubscriptionPlan(models.Model):
    """Модель тарифных планов."""
    name = models.CharField(max_length=100, unique=True, verbose_name="Название тарифа")
    description = models.TextField(verbose_name="Описание для клиента", blank=True)

    price_monthly = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name="Цена в месяц (₽)")
    price_annually = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name="Цена в год (₽)")

    max_equipment = models.PositiveIntegerField(default=10, verbose_name="Лимит оборудования")
    max_users = models.PositiveIntegerField(default=3, verbose_name="Лимит сотрудников")

    def __str__(self):
        return self.name


class Company(models.Model):
    """Модель компании, к которой привязаны пользователи и оборудование."""
    name = models.CharField(max_length=255, verbose_name="Название компании")
    slug = models.SlugField(max_length=255, unique=True, blank=True,
                            help_text="Уникальный идентификатор для URL. Генерируется автоматически.")
    logo = models.ImageField(upload_to='logos/', null=True, blank=True, verbose_name="Логотип")
    subscription_plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Тарифный план"
    )
    subscription_expires_on = models.DateField(
        null=True, blank=True,
        verbose_name="Подписка истекает"
    )
    auto_renew = models.BooleanField(default=False, verbose_name="Автопродление")

    yookassa_payment_method_id = models.CharField(
        max_length=255, null=True, blank=True,
        verbose_name="ID сохраненного способа оплаты YooKassa"
    )
    members = models.ManyToManyField(User, through='Membership', related_name='companies')

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Company.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def has_active_subscription(self):
        """Проверяет, есть ли у компании активная, не истекшая подписка."""
        return (
                self.subscription_plan is not None and
                self.subscription_expires_on is not None and
                self.subscription_expires_on >= timezone.now().date()
        )

    def __str__(self):
        return self.name


class Membership(models.Model):
    """Промежуточная модель для связи Пользователя и Компании."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    date_joined = models.DateField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'company')


class Invitation(models.Model):
    """Модель для хранения приглашений в компанию."""
    email = models.EmailField()
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Приглашение для {self.email} в {self.company.name}"


class EquipmentTemplate(models.Model):
    """Шаблон для создания единиц оборудования."""
    name = models.CharField(max_length=255, verbose_name="Название шаблона")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="templates")
    fields_schema = models.JSONField(default=list, verbose_name="Схема полей", blank=True)

    def add_field(self, field_name: str, field_type: str, field_purpose: str):
        """Добавляет новое поле в `fields_schema`."""
        if not isinstance(self.fields_schema, list):
            self.fields_schema = []

        field_id = f"field_{uuid.uuid4().hex[:8]}"
        new_field = {
            'id': field_id,
            'name': field_name,
            'type': field_type,
            'purpose': field_purpose
        }
        self.fields_schema.append(new_field)
        self.save()
        return new_field

    def delete_field(self, field_id: str) -> bool:
        """
        Удаляет поле из `fields_schema` по его ID.
        Возвращает True в случае успеха, False если поле не найдено.
        """
        if not isinstance(self.fields_schema, list):
            return False

        initial_length = len(self.fields_schema)
        self.fields_schema = [f for f in self.fields_schema if f.get('id') != field_id]
        field_was_deleted = len(self.fields_schema) < initial_length

        if field_was_deleted:
            self.save()

        return field_was_deleted

    def reorder_fields(self, ordered_ids: list, purpose: str):
        """
        Изменяет порядок полей в 'fields_schema' на основе заданного списка ID
        для определенной цели ('static' или 'checklist').
        """
        static_fields = [f for f in self.fields_schema if f.get('purpose', 'static') == 'static']
        checklist_fields = [f for f in self.fields_schema if f.get('purpose') == 'checklist']
        schema_lookup = {field['id']: field for field in self.fields_schema}
        reordered_group = [schema_lookup[field_id] for field_id in ordered_ids if field_id in schema_lookup]

        if purpose == 'static':
            self.fields_schema = reordered_group + checklist_fields
        else:
            self.fields_schema = static_fields + reordered_group
        self.save()

    def rename_field(self, field_id: str, new_name: str) -> bool:
        """
        Находит поле по ID и изменяет его 'name'.
        Возвращает True в случае успеха, False если поле не найдено.
        """
        field_found = False
        for field in self.fields_schema:
            if field.get('id') == field_id:
                field['name'] = new_name
                field_found = True
                break
        if field_found:
            self.save()
        return field_found

    def __str__(self):
        return self.name


class Equipment(models.Model):
    """Конкретная единица оборудования."""
    name = models.CharField(max_length=255, verbose_name="Название оборудования")
    slug = models.SlugField(max_length=255, allow_unicode=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="equipment")
    template = models.ForeignKey(EquipmentTemplate, on_delete=models.CASCADE, verbose_name="Шаблон")
    created_at = models.DateTimeField(auto_now_add=True)
    static_data = models.JSONField(
        default=dict, blank=True,
        verbose_name="Статические данные (параметры)"
    )
    current_checklist_state = models.JSONField(
        default=dict, blank=True,
        verbose_name="Текущее состояние по чек-листу"
    )

    def save(self, *args, **kwargs):
        if not self.pk:
            base_slug = slugify(self.name, allow_unicode=True)
            slug = base_slug
            counter = 1
            while Equipment.objects.filter(company=self.company, slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['company', 'slug'], name='unique_slug_per_company')
        ]

    def __str__(self):
        return self.name


class ServiceRecord(models.Model):
    """Запись в журнале обслуживания."""
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="records")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Автор")
    created_at = models.DateTimeField(auto_now_add=True)
    checklist_data = models.JSONField(
        default=dict, blank=True,
        verbose_name="Данные чек-листа"
    )

    class Meta:
        ordering = ['-created_at']


def company_service_photo_path(instance, filename):
    """
    Генерирует уникальный путь для фотографии обслуживания.
    Формат: service_photos/<company_slug>/<uuid>.<extension>
    """
    extension = Path(filename).suffix
    unique_filename = f"{uuid.uuid4().hex}{extension}"
    company_slug = instance.record.equipment.company.slug
    return f"service_photos/{company_slug}/{unique_filename}"


class ServiceRecordPhoto(models.Model):
    """Фотография, прикрепленная к записи об обслуживании."""
    record = models.ForeignKey(ServiceRecord, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to=company_service_photo_path, verbose_name="Фотография")

    def __str__(self):
        return f"Фото для записи #{self.record.id}"


class Payment(models.Model):
    """Модель для хранения информации о платежах через YooKassa."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    yookassa_payment_id = models.CharField(max_length=255, null=True, blank=True, unique=True, db_index=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='payments')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сумма")
    duration_days = models.PositiveIntegerField(default=30, verbose_name="Длительность подписки (дни)")
    status = models.CharField(max_length=50, default='pending', verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(null=True, blank=True, verbose_name="Метаданные от YooKassa")

    def __str__(self):
        return f"Платеж {self.id} на сумму {self.amount} для {self.company.name}"