# qr_app/urls.py

from django.urls import path
from . import views
from .views import ActivityHistoryView

app_name = 'qr_app'

urlpatterns = [
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('protected-media/<int:photo_id>/', views.serve_protected_media, name='serve_protected_media'),
    path('test500/', views.test_500_error_view, name='test_500'),

    # Шаблоны
    path('templates/', views.TemplateListView.as_view(), name='template_list'),
    path('templates/new/', views.TemplateCreateView.as_view(), name='template_create'),
    path('templates/<int:pk>/', views.TemplateDetailView.as_view(), name='template_detail'),
    path('templates/<int:pk>/delete/', views.TemplateDeleteView.as_view(), name='template_delete'),
    path('templates/<int:template_pk>/equipment/new/', views.EquipmentCreateFromTemplateView.as_view(),
         name='equipment_create_from_template'),
    path('templates/<int:pk>/reorder-fields/', views.TemplateReorderFieldsView.as_view(),
         name='template_reorder_fields'),
    path('templates/<int:pk>/rename-field/', views.TemplateRenameFieldView.as_view(), name='template_rename_field'),

    # Оборудование
    path('equipment/', views.EquipmentListView.as_view(), name='equipment_list'),
    path('equipment/<int:pk>/', views.EquipmentDetailView.as_view(), name='equipment_detail'),
    path('equipment/<int:pk>/edit/', views.EquipmentUpdateView.as_view(), name='equipment_update'),
    path('equipment/<int:pk>/delete/', views.EquipmentDeleteView.as_view(), name='equipment_delete'),
    path('equipment/qr/<int:equipment_id>/', views.generate_qr_code, name='generate_qr_code'),

    # Команда и настройки
    path('team/', views.TeamManageView.as_view(), name='manage_team'),
    path('team/member/<int:pk>/delete/', views.MemberDeleteView.as_view(), name='member_delete'),
    path('settings/', views.CompanySettingsView.as_view(), name='company_settings'),
    path('activity/', ActivityHistoryView.as_view(), name='activity_history'),

    # Подписка
    path('subscription/', views.SubscriptionManageView.as_view(), name='subscription_manage'),
    path('subscription/select/', views.SubscriptionSelectView.as_view(), name='subscription_select'),
    path('subscription/activate/', views.SubscriptionActivateView.as_view(), name='subscription_activate'),
    path('subscription/toggle-renew/', views.ToggleAutoRenewView.as_view(), name='subscription_toggle_renew'),
    path('subscription/cancel/', views.CancelSubscriptionView.as_view(), name='subscription_cancel'),
    path('subscription/result/', views.PaymentResultView.as_view(), name='payment_result'),

]

