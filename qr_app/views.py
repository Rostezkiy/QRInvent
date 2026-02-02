# qr_app/views.py
import base64
import hashlib
import hmac
import ipaddress
import secrets
from datetime import date, timedelta
from io import BytesIO
import json
import logging
import uuid
from itertools import chain
from operator import attrgetter

from django.views.decorators.csrf import csrf_exempt
from yookassa import Configuration, Payment as YooKassaPayment
import qrcode
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import ProtectedError, Count, Value, CharField, F
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.text import slugify
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from django.views.generic.edit import FormMixin

from project_qr import settings
from .forms import (
    UserRegistrationForm, EquipmentTemplateForm, InvitationForm,
    InvitedUserRegistrationForm, StaticDataForm, DynamicChecklistForm,
    CompanySettingsForm
)
from .mixins import (
    CompanyRequiredMixin, AdminRequiredMixin, CompanyQuerysetMixin,
    SuccessURLForCompanyMixin, ActiveSubscriptionRequiredMixin
)
from .models import (
    Company, SubscriptionPlan, Membership, User, EquipmentTemplate,
    Equipment, Invitation, ServiceRecord, ServiceRecordPhoto, Payment
)
from . import services

# Инициализация логгера для этого файла
logger = logging.getLogger(__name__)


# --- Аутентификация и Регистрация ---
def register_view(request):
    if request.user.is_authenticated:
        messages.info(request, "Вы уже вошли в систему.")
        return redirect('select_company')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save(commit=False)
                user.username = form.cleaned_data['email']
                user.role = User.Role.ADMIN
                user.set_password(form.cleaned_data['password'])
                user.save()

                company = Company.objects.create(name=form.cleaned_data['company_name'])
                Membership.objects.create(user=user, company=company)

                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                logger.info(
                    f"Новый пользователь и компания зарегистрированы. User ID: {user.id}, Company ID: {company.id}")
                return redirect('select_company')
        else:
            logger.warning(f"Ошибка регистрации нового пользователя. Ошибки формы: {form.errors.as_json()}")
    else:
        form = UserRegistrationForm()
    return render(request, 'registration/register.html', {'form': form})


# --- Дашборд ---
class DashboardView(CompanyRequiredMixin, ActiveSubscriptionRequiredMixin, View):
    """Отображает дашборд в зависимости от роли пользователя."""

    def get(self, request, *args, **kwargs):
        context = {'company': self.company}

        if request.user.is_admin:
            recent_records = ServiceRecord.objects.filter(
                equipment__company=self.company
            ).select_related('equipment', 'author').order_by('-created_at')[:5]

            recent_equipment = Equipment.objects.filter(
                company=self.company
            ).select_related('template').order_by('-created_at')[:5]

            for item in recent_records: item.type = 'record'
            for item in recent_equipment: item.type = 'equipment'

            activity_list = sorted(
                chain(recent_records, recent_equipment),
                key=attrgetter('created_at'),
                reverse=True
            )[:5]

            context.update({
                'equipment_count': self.company.equipment.count(),
                'user_count': self.company.members.count(),
                'activity_list': activity_list,
            })
            return render(request, 'dashboards/admin_dashboard.html', context)

        recent_records = ServiceRecord.objects.filter(
            equipment__company=self.company, author=request.user
        ).select_related('equipment').order_by('-created_at')[:5]

        equipment_list = Equipment.objects.filter(company=self.company).order_by('name')

        context.update({
            'recent_records': recent_records,
            'equipment_list': equipment_list,
        })
        return render(request, 'dashboards/technician_dashboard.html', context)


# --- Управление Шаблонами ---
class TemplateListView(CompanyRequiredMixin, ActiveSubscriptionRequiredMixin, AdminRequiredMixin, ListView):
    model = EquipmentTemplate
    template_name = 'templates/template_list.html'
    context_object_name = 'templates'

    def get_queryset(self):
        return EquipmentTemplate.objects.filter(
            company=self.company
        ).annotate(equipment_count=Count('equipment'))


class TemplateCreateView(CompanyRequiredMixin, AdminRequiredMixin, ActiveSubscriptionRequiredMixin,
                         SuccessURLForCompanyMixin, SuccessMessageMixin, CreateView):
    model = EquipmentTemplate
    form_class = EquipmentTemplateForm
    template_name = 'templates/template_form.html'
    success_message = "Шаблон успешно создан!"
    list_view_name = 'qr_app:template_list'

    def form_valid(self, form):
        form.instance.company = self.company
        response = super().form_valid(form)
        logger.info(
            f"User ID: {self.request.user.id} создал новый шаблон ID: {self.object.id} для компании '{self.company.slug}'")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Создание нового шаблона"
        return context


class TemplateDeleteView(CompanyRequiredMixin, ActiveSubscriptionRequiredMixin, AdminRequiredMixin,
                         CompanyQuerysetMixin, SuccessURLForCompanyMixin, DeleteView):
    model = EquipmentTemplate
    template_name = 'templates/template_confirm_delete.html'
    list_view_name = 'qr_app:template_list'

    def post(self, request, *args, **kwargs):
        template_id = self.get_object().id
        try:
            response = super().post(request, *args, **kwargs)
            logger.info(f"User ID: {request.user.id} удалил шаблон ID: {template_id} из компании '{self.company.slug}'")
            messages.success(request, "Шаблон успешно удален.")
            return response
        except ProtectedError:
            logger.warning(
                f"User ID: {request.user.id} не смог удалить защищенный шаблон ID: {template_id} в компании '{self.company.slug}'")
            messages.error(request,
                           "Невозможно удалить шаблон, так как существуют единицы оборудования, использующие его.")
            return redirect('qr_app:template_list', company_slug=self.kwargs['company_slug'])


class TemplateDetailView(CompanyRequiredMixin, ActiveSubscriptionRequiredMixin, AdminRequiredMixin,
                         CompanyQuerysetMixin, DetailView):
    model = EquipmentTemplate
    template_name = 'templates/template_detail.html'
    context_object_name = 'template'

    def post(self, request, *args, **kwargs):
        """
        Обрабатывает POST-запросы:
        - JSON для переименования шаблона.
        - Form-data для добавления/удаления полей.
        """
        template = self.get_object()

        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                action = data.get('action')
                if action == 'rename_template':
                    new_name = data.get('new_name', '').strip()
                    if not new_name:
                        return JsonResponse({'status': 'error', 'message': 'Название не может быть пустым.'}, status=400)
                    template.name = new_name
                    template.save()
                    logger.info(f"Шаблон ID {template.id} переименован в '{new_name}' пользователем {request.user.id}")
                    return JsonResponse({'status': 'ok', 'new_name': template.name})
                return JsonResponse({'status': 'error', 'message': 'Неизвестное AJAX действие'}, status=400)
            except json.JSONDecodeError:
                return JsonResponse({'status': 'error', 'message': 'Некорректный JSON.'}, status=400)
        else:
            action = request.POST.get('action')
            if action == 'add_field':
                field_name = request.POST.get('field_name', '').strip()
                field_type = request.POST.get('field_type')
                field_purpose = request.POST.get('field_purpose', 'static')
                if field_name and field_type:
                    template.add_field(field_name, field_type, field_purpose)
                    logger.info(f"User ID: {request.user.id} добавил поле '{field_name}' в шаблон ID: {template.id}")
                    messages.success(request, f"Поле '{field_name}' добавлено.")
                return redirect('qr_app:template_detail', company_slug=self.company.slug, pk=template.pk)

            if action == 'delete_field':
                field_id = request.POST.get('field_id')
                if field_id and template.delete_field(field_id):
                    logger.info(f"User ID: {request.user.id} удалил поле ID: {field_id} из шаблона ID: {template.id}")
                    return JsonResponse({'status': 'ok'})
                return JsonResponse({'status': 'error', 'message': 'Field not found or missing ID'}, status=400)

            return redirect('qr_app:template_detail', company_slug=self.company.slug, pk=template.pk)


# --- Управление Оборудованием ---
class EquipmentListView(CompanyRequiredMixin, ActiveSubscriptionRequiredMixin, CompanyQuerysetMixin, ListView):
    model = Equipment
    template_name = 'equipment/equipment_list.html'
    context_object_name = 'equipment_list'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['equipment_count'] = self.company.equipment.count()
        context['equipment_limit'] = self.company.subscription_plan.max_equipment
        return context


class EquipmentCreateFromTemplateView(CompanyRequiredMixin, ActiveSubscriptionRequiredMixin, AdminRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        if self.company.equipment.count() >= self.company.subscription_plan.max_equipment:
            logger.warning(
                f"Компания '{self.company.slug}' достигла лимита оборудования ({self.company.subscription_plan.max_equipment}). User ID: {request.user.id} не смог открыть форму создания.")
            messages.error(request, "Достигнут лимит на количество оборудования. Удалите старое или смените тариф.")
            return redirect('qr_app:equipment_list', company_slug=self.company.slug)

        template = get_object_or_404(EquipmentTemplate, pk=kwargs.get('template_pk'), company=self.company)
        static_schema = [f for f in template.fields_schema if f.get('purpose', 'static') == 'static']
        form = StaticDataForm(schema=static_schema)
        return render(request, 'equipment/equipment_static_form.html', {'form': form, 'template': template})

    def post(self, request, *args, **kwargs):
        if self.company.equipment.count() >= self.company.subscription_plan.max_equipment:
            logger.error(
                f"Компания '{self.company.slug}' достигла лимита оборудования. Попытка создания оборудования User ID: {request.user.id} была заблокирована.")
            messages.error(request, "Достигнут лимит на количество оборудования.")
            return redirect('qr_app:equipment_list', company_slug=self.company.slug)

        template = get_object_or_404(EquipmentTemplate, pk=kwargs.get('template_pk'), company=self.company)
        static_schema = [f for f in template.fields_schema if f.get('purpose', 'static') == 'static']
        form = StaticDataForm(request.POST, schema=static_schema)

        if form.is_valid():
            static_data = {key: (value.isoformat() if isinstance(value, date) else value) for key, value in
                           form.cleaned_data.items() if key != 'name'}
            equipment = Equipment.objects.create(
                company=self.company,
                template=template,
                name=form.cleaned_data['name'],
                static_data=static_data
            )
            logger.info(
                f"User ID: {request.user.id} создал оборудование ID: {equipment.id} для компании '{self.company.slug}'")
            messages.success(request, "Оборудование успешно добавлено.")
            return redirect('qr_app:equipment_list', company_slug=self.company.slug)

        logger.warning(
            f"User ID: {request.user.id} не смог создать оборудование. Ошибки формы: {form.errors.as_json()}")
        return render(request, 'equipment/equipment_static_form.html', {'form': form, 'template': template})


class EquipmentUpdateView(CompanyRequiredMixin, ActiveSubscriptionRequiredMixin, AdminRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        pk = kwargs.get('pk')
        equipment = get_object_or_404(Equipment, pk=pk, company=self.company)
        static_schema = [f for f in equipment.template.fields_schema if f.get('purpose', 'static') == 'static']
        initial_data = {'name': equipment.name, **(equipment.static_data or {})}
        form = StaticDataForm(schema=static_schema, initial=initial_data)
        return render(request, 'equipment/equipment_static_form.html',
                      {'form': form, 'template': equipment.template, 'page_title': 'Редактирование оборудования'})

    def post(self, request, *args, **kwargs):
        pk = kwargs.get('pk')
        equipment = get_object_or_404(Equipment, pk=pk, company=self.company)
        static_schema = [f for f in equipment.template.fields_schema if f.get('purpose', 'static') == 'static']
        form = StaticDataForm(request.POST, schema=static_schema)

        if form.is_valid():
            equipment.name = form.cleaned_data['name']
            equipment.static_data = {key: (value.isoformat() if isinstance(value, date) else value) for key, value in
                                     form.cleaned_data.items() if key != 'name'}
            equipment.slug = slugify(equipment.name, allow_unicode=True)
            equipment.save()
            logger.info(
                f"User ID: {request.user.id} обновил оборудование ID: {equipment.id} в компании '{self.company.slug}'")
            messages.success(request, "Оборудование успешно обновлено.")
            return redirect('qr_app:equipment_detail', company_slug=self.company.slug, pk=equipment.pk)

        logger.warning(
            f"User ID: {request.user.id} не смог обновить оборудование ID: {equipment.id}. Ошибки формы: {form.errors.as_json()}")
        return render(request, 'equipment/equipment_static_form.html',
                      {'form': form, 'template': equipment.template, 'page_title': 'Редактирование оборудования'})


class EquipmentDeleteView(CompanyRequiredMixin, AdminRequiredMixin, CompanyQuerysetMixin, SuccessURLForCompanyMixin,
                          DeleteView):
    model = Equipment
    template_name = 'equipment/equipment_confirm_delete.html'
    success_message = "Оборудование успешно удалено."
    list_view_name = 'qr_app:equipment_list'

    def form_valid(self, form):
        equipment_id = self.get_object().id
        messages.success(self.request, self.success_message)
        response = super().form_valid(form)
        logger.info(
            f"User ID: {self.request.user.id} удалил оборудование ID: {equipment_id} из компании '{self.company.slug}'")
        return response


class EquipmentDetailView(CompanyRequiredMixin, ActiveSubscriptionRequiredMixin, CompanyQuerysetMixin, DetailView):
    model = Equipment
    template_name = 'equipment/equipment_detail.html'
    context_object_name = 'equipment'

    def get_queryset(self):
        return Equipment.objects.filter(company=self.company).prefetch_related('records__author')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        equipment = self.get_object()
        checklist_schema = [f for f in equipment.template.fields_schema if f.get('purpose') == 'checklist']
        initial_data = equipment.current_checklist_state or {}
        context['checklist_form'] = DynamicChecklistForm(schema=checklist_schema, initial=initial_data)
        return context

    def post(self, request, *args, **kwargs):
        equipment = self.get_object()
        checklist_schema = [f for f in equipment.template.fields_schema if f.get('purpose') == 'checklist']
        form = DynamicChecklistForm(request.POST, request.FILES, schema=checklist_schema)

        if form.is_valid():
            record = services.create_service_record_from_checklist(
                equipment=equipment,
                user=request.user,
                form_data=form.cleaned_data,
                uploaded_files=request.FILES.getlist('images')
            )
            logger.info(
                f"User ID: {request.user.id} добавил сервисную запись ID: {record.id} для оборудования ID: {equipment.id} в компании '{self.company.slug}'")
            messages.success(request, "Запись в журнал успешно добавлена.")
        else:
            logger.error(
                f"User ID: {request.user.id} не смог добавить запись для оборудования ID: {equipment.id}. Ошибки формы: {form.errors.as_json()}")
            messages.error(request, "Ошибка в заполнении формы.")
            context = self.get_context_data(object=equipment)
            context['checklist_form'] = form
            return self.render_to_response(context)

        return redirect('qr_app:equipment_detail', company_slug=self.company.slug, pk=equipment.pk)


@login_required
def generate_qr_code(request, company_slug, equipment_id):
    if not request.user.companies.filter(slug=company_slug).exists():
        logger.error(
            f"User ID: {request.user.id} пытался сгенерировать QR для оборудования ID: {equipment_id} без доступа к компании '{company_slug}'")
        raise PermissionDenied

    equipment = get_object_or_404(Equipment, id=equipment_id, company__slug=company_slug)
    url = request.build_absolute_uri(
        reverse('qr_app:equipment_detail', kwargs={'company_slug': company_slug, 'pk': equipment.pk}))
    img = qrcode.make(url)
    buffer = BytesIO()
    img.save(buffer, "PNG")
    logger.info(
        f"User ID: {request.user.id} сгенерировал QR-код для оборудования ID: {equipment.id} в компании '{company_slug}'")
    return HttpResponse(buffer.getvalue(), content_type="image/png")


# --- Управление Командой ---
class TeamManageView(CompanyRequiredMixin, ActiveSubscriptionRequiredMixin, AdminRequiredMixin,
                     SuccessURLForCompanyMixin, FormMixin, ListView):
    template_name = 'team/manage_team.html'
    context_object_name = 'members'
    form_class = InvitationForm
    list_view_name = 'qr_app:manage_team'

    def get_queryset(self):
        return self.company.members.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user_limit'] = self.company.subscription_plan.max_users
        context['current_user_count'] = self.company.members.count()
        context['pending_invites_count'] = Invitation.objects.filter(company=self.company).count()
        context['invitations'] = Invitation.objects.filter(company=self.company)
        return context

    def form_valid(self, form):
        current_users = self.company.members.count()
        pending_invites = Invitation.objects.filter(company=self.company).count()
        if current_users + pending_invites >= self.company.subscription_plan.max_users:
            logger.error(
                f"User ID: {self.request.user.id} не смог отправить приглашение. Достигнут лимит пользователей в компании '{self.company.slug}'")
            messages.error(self.request, "Достигнут лимит на количество сотрудников. Приглашение не было отправлено.")
            return self.form_invalid(form)

        email = form.cleaned_data['email']
        if self.company.members.filter(email=email).exists():
            messages.error(self.request, f"Пользователь с email {email} уже в вашей команде.")
            return self.form_invalid(form)

        invitation = form.save(commit=False)
        invitation.company = self.company
        invitation.token = secrets.token_urlsafe(32)
        invitation.save()
        logger.info(f"User ID: {self.request.user.id} создал приглашение для {email} в компанию '{self.company.slug}'")

        invite_url = self.request.build_absolute_uri(reverse('accept_invitation', kwargs={'token': invitation.token}))
        messages.success(self.request, format_html(
            'Приглашение успешно создано! Ссылка для регистрации: <br>'
            '<input type="text" value="{}" class="w-full p-1 border rounded bg-gray-100" readonly onclick="this.select();">',
            invite_url
        ))
        return redirect(self.get_success_url())

    def post(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            logger.warning(
                f"User ID: {request.user.id} не смог отправить приглашение. Ошибки формы: {form.errors.as_json()}")
            return self.form_invalid(form)


def accept_invitation_view(request, token):
    invitation = get_object_or_404(Invitation, token=token)
    email, company = invitation.email, invitation.company
    if invitation.created_at < timezone.now() - timedelta(days=7):
        invitation.delete()
        messages.error(request, "Срок действия этого приглашения истек.")
        return redirect('register')
    if existing_user := User.objects.filter(email=email).first():
        Membership.objects.get_or_create(user=existing_user, company=company)
        invitation.delete()
        logger.info(
            f"Существующий пользователь User ID: {existing_user.id} принял приглашение в компанию '{company.slug}'")
        messages.success(request, f"Вы были успешно добавлены в компанию {company.name}.")
        return redirect('login')

    if request.method == 'POST':
        form = InvitedUserRegistrationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = User.objects.create_user(
                    username=email, email=email,
                    password=form.cleaned_data['password'],
                    role=User.Role.TECHNICIAN
                )
                Membership.objects.create(user=user, company=company)
                invitation.delete()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            logger.info(
                f"Новый пользователь User ID: {user.id} зарегистрировался и принял приглашение в компанию '{company.slug}'")
            return redirect('select_company')
        else:
            logger.warning(
                f"Ошибка регистрации по приглашению для email {email}. Ошибки формы: {form.errors.as_json()}")
    else:
        form = InvitedUserRegistrationForm()

    return render(request, 'invitations/accept_invitation.html', {'form': form, 'email': email, 'company': company})


class MemberDeleteView(CompanyRequiredMixin, AdminRequiredMixin, CompanyQuerysetMixin, SuccessURLForCompanyMixin,
                       DeleteView):
    model = User
    template_name = 'team/member_confirm_delete.html'
    success_message = "Сотрудник успешно удален из компании."
    list_view_name = 'qr_app:manage_team'

    def get_queryset(self):
        return self.company.members.all()

    def dispatch(self, request, *args, **kwargs):
        member_pk_to_delete = kwargs.get('pk')
        if str(member_pk_to_delete) == str(request.user.pk):
            logger.error(
                f"User ID: {request.user.id} пытался удалить самого себя (URL PK: {member_pk_to_delete}). Доступ запрещен.")
            return HttpResponseForbidden("Вы не можете удалить самого себя.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        member_to_delete = self.get_object()
        membership = Membership.objects.get(user=member_to_delete, company=self.company)
        membership.delete()
        logger.info(
            f"User ID: {self.request.user.id} удалил участника ID: {member_to_delete.id} из компании '{self.company.slug}'")
        messages.success(self.request, self.success_message)
        return redirect(self.get_success_url())


# --- Настройки и Подписка ---
class CompanySettingsView(CompanyRequiredMixin, AdminRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Company
    form_class = CompanySettingsForm
    template_name = 'settings/company_settings.html'
    success_message = "Настройки компании успешно обновлены."

    def get_object(self, queryset=None):
        return self.company

    def get_success_url(self):
        return reverse('qr_app:company_settings', kwargs={'company_slug': self.company.slug})

    def form_valid(self, form):
        response = super().form_valid(form)
        logger.info(f"User ID: {self.request.user.id} обновил настройки компании '{self.company.slug}'")
        return response


class SubscriptionManageView(CompanyRequiredMixin, AdminRequiredMixin, DetailView):
    model = Company
    template_name = 'settings/subscription_manage.html'
    context_object_name = 'company'

    def get_object(self, queryset=None):
        return self.company

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['equipment_usage'] = self.company.equipment.count()
        context['user_usage'] = self.company.members.count()
        return context


class SubscriptionSelectView(CompanyRequiredMixin, AdminRequiredMixin, ListView):
    model = SubscriptionPlan
    template_name = 'settings/subscription_select.html'
    context_object_name = 'plans'

    def get_queryset(self):
        return SubscriptionPlan.objects.all().order_by('price_monthly')


class SubscriptionActivateView(CompanyRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        plan_id = request.POST.get('plan_id')
        plan = get_object_or_404(SubscriptionPlan, id=plan_id)

        is_free_plan = plan.price_monthly == 0 and plan.price_annually == 0

        if is_free_plan:
            services.activate_free_plan(self.company, plan)
            logger.info(f"Для компании '{self.company.slug}' активирован бесплатный тариф '{plan.name}'. User ID: {request.user.id}")
            messages.success(request, f"Бесплатный тариф '{plan.name}' успешно активирован!")
            return redirect('qr_app:subscription_manage', company_slug=self.company.slug)
        else:
            period = request.POST.get('period')
            try:
                confirmation_url = services.create_yookassa_payment(self.company, plan, period, request)
                return redirect(confirmation_url)
            except ValueError as e:
                messages.error(request, str(e))
                return redirect('qr_app:subscription_select', company_slug=self.company.slug)
            except Exception as e:
                logger.error(f"Ошибка при создании платежа YooKassa для компании '{self.company.slug}': {e}", exc_info=True)
                messages.error(request, "Произошла ошибка при создании платежа. Попробуйте позже.")
                return redirect('qr_app:subscription_select', company_slug=self.company.slug)


class CancelSubscriptionView(CompanyRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        self.company.auto_renew = False
        self.company.save()
        logger.info(f"User ID: {request.user.id} отключил автопродление для компании '{self.company.slug}'")
        messages.success(request, "Автопродление подписки отменено. Доступ сохранится до конца оплаченного периода.")
        return redirect('qr_app:subscription_manage', company_slug=self.company.slug)


# --- Выбор компании и AJAX ---
@login_required
def select_company_view(request):
    memberships = Membership.objects.filter(user=request.user).select_related('company')
    if not memberships.exists():
        messages.info(request, "Вы пока не состоите ни в одной компании.")
        return redirect('register')
    if memberships.count() == 1:
        return redirect('qr_app:dashboard', company_slug=memberships.first().company.slug)
    return render(request, 'registration/select_company.html', {'memberships': memberships})


class TemplateReorderFieldsView(CompanyRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            template = get_object_or_404(EquipmentTemplate, pk=kwargs.get('pk'), company=self.company)
            data = json.loads(request.body)
            ordered_ids = data.get('ordered_ids')
            purpose = data.get('purpose')
            if not isinstance(ordered_ids, list) or purpose not in ['static', 'checklist']:
                logger.error(f"Неверный AJAX-запрос на reorder_fields от User ID: {request.user.id}. Данные: {data}")
                return JsonResponse({'status': 'error', 'message': 'Неверные данные.'}, status=400)
            template.reorder_fields(ordered_ids, purpose)
            logger.info(f"User ID: {request.user.id} изменил порядок полей ('{purpose}') для шаблона ID: {template.id}")
            return JsonResponse({'status': 'ok', 'message': 'Порядок полей сохранен.'})
        except json.JSONDecodeError:
            logger.error(f"Ошибка декодирования JSON в reorder_fields от User ID: {request.user.id}. Тело запроса: {request.body}")
            return JsonResponse({'status': 'error', 'message': 'Неверный формат JSON.'}, status=400)
        except Exception as e:
            logger.critical(f"Критическая ошибка в TemplateReorderFieldsView: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': f'Внутренняя ошибка сервера: {e}'}, status=500)


class TemplateRenameFieldView(CompanyRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            template = get_object_or_404(EquipmentTemplate, pk=kwargs.get('pk'), company=self.company)
            data = json.loads(request.body)
            field_id = data.get('field_id')
            new_name = data.get('new_name', '').strip()
            if not field_id or not new_name:
                logger.error(f"Неверный AJAX-запрос на rename_field от User ID: {request.user.id}. Данные: {data}")
                return JsonResponse({'status': 'error', 'message': 'Неверные данные.'}, status=400)
            success = template.rename_field(field_id, new_name)
            if success:
                logger.info(f"User ID: {request.user.id} переименовал поле ID: {field_id} в '{new_name}' для шаблона ID: {template.id}")
                return JsonResponse({'status': 'ok', 'message': 'Поле переименовано.'})
            else:
                logger.error(f"User ID: {request.user.id} пытался переименовать несуществующее поле ID: {field_id} в шаблоне ID: {template.id}")
                return JsonResponse({'status': 'error', 'message': 'Поле с таким ID не найдено.'}, status=404)
        except json.JSONDecodeError:
            logger.error(f"Ошибка декодирования JSON в rename_field от User ID: {request.user.id}. Тело запроса: {request.body}")
            return JsonResponse({'status': 'error', 'message': 'Неверный формат JSON.'}, status=400)
        except Exception as e:
            logger.critical(f"Критическая ошибка в TemplateRenameFieldView: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': f'Внутренняя ошибка сервера: {e}'}, status=500)


@login_required
def serve_protected_media(request, company_slug, photo_id):
    photo = get_object_or_404(
        ServiceRecordPhoto.objects.select_related('record__equipment__company'),
        pk=photo_id
    )
    user_companies = request.user.companies.all()
    if photo.record.equipment.company not in user_companies:
        logger.warning(
            f"ОТКАЗ В ДОСТУПЕ: User ID: {request.user.id} пытался получить доступ к фото ID: {photo_id}, которое ему не принадлежит.")
        return HttpResponseForbidden("У вас нет доступа к этому файлу.")
    if not settings.DEBUG:
        response = HttpResponse()
        response['X-Accel-Redirect'] = f'/protected_media{photo.image.url}'
        del response['Content-Type']
        return response
    else:
        return redirect(photo.image.url)


# --- Системные View ---
def home_redirect_view(request):
    if request.user.is_authenticated:
        return redirect('select_company')
    return redirect('login')


def custom_server_error_view(request, template_name='500.html'):
    error_id = uuid.uuid4()
    logger.critical(f"Server Error (500), Error ID: {error_id}", exc_info=True)
    return render(request, template_name, {'error_id': error_id}, status=500)


def test_500_error_view(request, company_slug):
    raise Exception("Это тестовая 500 ошибка для проверки обработчика.")


class LandingPageView(TemplateView):
    template_name = 'landing_page.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['plans'] = SubscriptionPlan.objects.all().order_by('price_monthly')
        context['is_user_authenticated'] = self.request.user.is_authenticated
        return context


class ActivityHistoryView(CompanyRequiredMixin, AdminRequiredMixin, ListView):
    """Отображает полную, постраничную историю активности в компании."""
    template_name = 'dashboards/activity_list.html'
    context_object_name = 'activity_page'
    paginate_by = 10

    def get_queryset(self):
        """
        Создает единый, отсортированный QuerySet для всех типов активности,
        используя UNION на уровне базы данных для максимальной производительности.
        """
        service_records_qs = ServiceRecord.objects.filter(
            equipment__company=self.company
        ).annotate(
            item_type=Value('record', output_field=CharField()),
            title=F('equipment__name'),
            object_pk=F('equipment__pk'),
            object_slug=F('equipment__slug')
        ).values(
            'created_at', 'item_type', 'title',
            'author__username', 'object_pk', 'object_slug'
        )

        equipment_qs = Equipment.objects.filter(
            company=self.company
        ).annotate(
            item_type=Value('equipment', output_field=CharField()),
            title=F('name'),
            author__username=Value('', output_field=CharField()),
            object_pk=F('pk'),
            object_slug=F('slug')
        ).values(
            'created_at', 'item_type', 'title',
            'author__username', 'object_pk', 'object_slug'
        )

        activity_queryset = service_records_qs.union(equipment_qs).order_by('-created_at')
        return activity_queryset


@csrf_exempt
def yookassa_webhook_view(request):
    """Безопасный обработчик уведомлений от YooKassa."""
    YOOKASSA_IPS = [
        ipaddress.ip_network('185.71.76.0/27'), ipaddress.ip_network('185.71.77.0/27'),
        ipaddress.ip_network('77.75.153.0/25'), ipaddress.ip_network('77.75.154.128/25'),
        ipaddress.ip_network('2a02:5180::/32'), ipaddress.ip_address('77.75.156.11'),
        ipaddress.ip_address('77.75.156.35'),
    ]
    client_ip_str = request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR')
    if not client_ip_str:
        logger.warning("YooKassa Webhook: Не удалось определить IP-адрес запроса.")
        return HttpResponseForbidden("IP address not identified.")
    try:
        client_ip = ipaddress.ip_address(client_ip_str)
        if not any(client_ip in network for network in YOOKASSA_IPS):
            logger.error(f"YooKassa Webhook: ЗАПРОС С НЕДОВЕРЕННОГО IP: {client_ip}")
            return HttpResponseForbidden("Untrusted IP address.")
        logger.info(f"YooKassa Webhook: Проверка IP пройдена. Запрос с доверенного IP: {client_ip}")
    except ValueError:
        logger.warning(f"YooKassa Webhook: Получен некорректный IP-адрес: {client_ip_str}")
        return HttpResponseForbidden("Invalid IP address format.")

    try:
        event_json = json.loads(request.body)
        notification_object = event_json.get('object')
    except (json.JSONDecodeError, AttributeError):
        logger.error("YooKassa Webhook: Invalid JSON или тело запроса.")
        return HttpResponse(status=400)

    if not notification_object:
        return HttpResponse(status=200)

    local_payment_id = notification_object.get('metadata', {}).get('local_payment_id')
    yookassa_payment_id = notification_object.get('id')
    if not local_payment_id:
        return HttpResponse(status=200)

    try:
        payment = Payment.objects.get(id=local_payment_id)
    except Payment.DoesNotExist:
        logger.error(f"YooKassa Webhook: Payment с ID {local_payment_id} не найден.")
        return HttpResponse(status=200)

    try:
        Configuration.account_id = settings.YOOKASSA_SHOP_ID
        Configuration.secret_key = settings.YOOKASSA_SECRET_KEY
        payment_info = YooKassaPayment.find_one(yookassa_payment_id)
        actual_status = payment_info.status
    except Exception as e:
        logger.error(f"Не удалось получить статус платежа {yookassa_payment_id} от API YooKassa: {e}")
        return HttpResponse(status=500)

    if actual_status == 'succeeded' and payment.status != 'succeeded':
        services.process_successful_payment(payment, payment_info)
        logger.info(f"Подписка для компании '{payment.company.slug}' успешно активирована/продлена. Платеж: {payment.id}")
    elif payment.status != actual_status:
        payment.status = actual_status
        payment.save()
        logger.info(f"Статус платежа {payment.id} обновлен на '{actual_status}'.")

    return HttpResponse(status=200)


class PaymentResultView(CompanyRequiredMixin, AdminRequiredMixin, TemplateView):
    template_name = 'settings/payment_result.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['company'] = self.company
        messages.info(self.request, "Платеж обрабатывается. Статус подписки обновится в течение минуты.")
        return context


class ToggleAutoRenewView(CompanyRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        self.company.auto_renew = not self.company.auto_renew
        self.company.save()
        status = "включено" if self.company.auto_renew else "отключено"
        logger.info(f"User ID: {request.user.id} изменил статус автопродления на '{status}' для компании '{self.company.slug}'")
        messages.success(request, f"Автопродление успешно {status}.")
        return redirect('qr_app:subscription_manage', company_slug=self.company.slug)