# project_qr/urls.py
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

from project_qr import settings
from qr_app import views as qr_app_views
from qr_app.views import LandingPageView, yookassa_webhook_view
from django_otp.admin import OTPAdminSite

admin.site.__class__ = OTPAdminSite

urlpatterns = [
    path('super-secret-control-panel/', admin.site.urls),
    path('yookassa/webhook/', yookassa_webhook_view, name='yookassa_webhook_global'),

    # --- ГЛОБАЛЬНЫЕ URL ---
    # --- ИЗМЕНЕНИЕ: Заменяем LoginView на наш новый редиректор ---
    path('', LandingPageView.as_view(), name='landing_page'),

    path('register/', qr_app_views.register_view, name='register'),
    path('login/', qr_app_views.LoginView.as_view(
        template_name='registration/login.html',
        redirect_authenticated_user=True
    ), name='login'),
    path('logout/', qr_app_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('invitations/accept/<str:token>/', qr_app_views.accept_invitation_view, name='accept_invitation'),

    # --- НОВЫЙ URL ДЛЯ ВЫБОРА КОМПАНИИ ПОСЛЕ ЛОГИНА ---
    path('select-company/', qr_app_views.select_company_view, name='select_company'),

    # --- URL-ы, СПЕЦИФИЧНЫЕ ДЛЯ КОМПАНИИ ---
    path('<slug:company_slug>/', include('qr_app.urls', namespace='qr_app')),

]
handler500 = 'qr_app.views.custom_server_error_view'

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
