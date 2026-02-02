# qr_app/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
import json

from .models import (
    User, SubscriptionPlan, Company, Membership, Invitation,
    EquipmentTemplate, Equipment, ServiceRecord, ServiceRecordPhoto
)


# --- Улучшения для Владельца Сервиса ---

class SubscriptionStatusFilter(admin.SimpleListFilter):
    """
    Кастомный фильтр для компаний: с активной подпиской или просроченной.
    Это критически важно для управления клиентами.
    """
    title = 'Статус подписки'
    parameter_name = 'subscription_status'

    def lookups(self, request, model_admin):
        return (
            ('active', 'Активна'),
            ('expired', 'Просрочена или отсутствует'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'active':
            return queryset.filter(
                subscription_plan__isnull=False,
                subscription_expires_on__gte=timezone.now().date()
            )
        if self.value() == 'expired':
            return queryset.exclude(
                subscription_plan__isnull=False,
                subscription_expires_on__gte=timezone.now().date()
            )


# --- Настройка Админ-панели ---

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'role', 'date_joined', 'get_companies')
    list_filter = ('role', 'is_staff')
    search_fields = ('email',)

    @admin.display(description='Состоит в компаниях')
    def get_companies(self, obj):
        return ", ".join([c.name for c in obj.companies.all()])


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_monthly', 'price_annually', 'max_equipment', 'max_users')
    search_fields = ('name',)


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 1
    autocomplete_fields = ('user',)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'subscription_plan', 'subscription_expires_on', 'is_active_subscription')
    list_filter = (SubscriptionStatusFilter, 'subscription_plan',)  # Используем наш кастомный фильтр
    search_fields = ('name', 'slug')
    inlines = (MembershipInline,)
    readonly_fields = ('slug',)

    @admin.display(description='Подписка активна?', boolean=True)
    def is_active_subscription(self, obj):
        return obj.has_active_subscription


@admin.register(EquipmentTemplate)
class EquipmentTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_company_link')
    search_fields = ('name', 'company__name')
    readonly_fields = ('formatted_fields_schema',)

    @admin.display(description='Компания')
    def get_company_link(self, obj):
        link = reverse("admin:qr_app_company_change", args=[obj.company.id])
        return format_html('<a href="{}">{}</a>', link, obj.company.name)

    @admin.display(description='Схема полей (JSON)')
    def formatted_fields_schema(self, obj):
        # Отображаем JSON в читаемом виде для отладки
        formatted_json = json.dumps(obj.fields_schema, indent=2, ensure_ascii=False)
        return format_html('<pre><code>{}</code></pre>', formatted_json)


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_company_link', 'get_template_link', 'created_at')
    list_filter = ('company', 'template')
    search_fields = ('name', 'slug')
    readonly_fields = ('slug', 'created_at', 'formatted_static_data', 'formatted_checklist_state')

    @admin.display(description='Компания')
    def get_company_link(self, obj):
        link = reverse("admin:qr_app_company_change", args=[obj.company.id])
        return format_html('<a href="{}">{}</a>', link, obj.company.name)

    @admin.display(description='Шаблон')
    def get_template_link(self, obj):
        link = reverse("admin:qr_app_equipmenttemplate_change", args=[obj.template.id])
        return format_html('<a href="{}">{}</a>', link, obj.template.name)

    @admin.display(description='Статические данные (JSON)')
    def formatted_static_data(self, obj):
        formatted_json = json.dumps(obj.static_data, indent=2, ensure_ascii=False)
        return format_html('<pre><code>{}</code></pre>', formatted_json)

    @admin.display(description='Текущий чек-лист (JSON)')
    def formatted_checklist_state(self, obj):
        formatted_json = json.dumps(obj.current_checklist_state, indent=2, ensure_ascii=False)
        return format_html('<pre><code>{}</code></pre>', formatted_json)


# Остальные регистрации можно оставить как есть или убрать, если они не нужны для прямого редактирования
admin.site.register(Invitation)
admin.site.register(ServiceRecord)
admin.site.register(ServiceRecordPhoto)