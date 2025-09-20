"""
URL configuration for ozontelemetry project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from django.urls import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.contrib.auth import views as auth_views
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from telemetry.views import (
    TelemetryViewSet, TelemetryEventViewSet, DeviceStatusViewSet, OutletViewSet, MachineViewSet,
    iot_ingest, export_data, flush_all_data, handshake, events, devices_list_page,
    outlets_page, machines_page, device_bind, device_unbind, devices_data_api, machine_delete,
    test_devices_page, test_outlets_page, test_machines_page, test_stats_api, test_stats_page, test_stats_options, test_stats_export_csv
)

def custom_logout(request):
    """Custom logout view that just redirects without showing a page"""
    logout(request)
    return redirect('/accounts/login/')

router = DefaultRouter()
router.register(r'telemetry', TelemetryViewSet, basename='telemetry')
router.register(r'events', TelemetryEventViewSet, basename='events')
router.register(r'devices', DeviceStatusViewSet, basename='devices')
router.register(r'outlets', OutletViewSet, basename='outlets')
router.register(r'machines', MachineViewSet, basename='machines')

urlpatterns = [
    path('', devices_list_page, name='home'),
    path('admin/', admin.site.urls),
    # Auth
    path('accounts/login/', auth_views.LoginView.as_view(template_name='telemetry/login.html'), name='login'),
    path('accounts/logout/', custom_logout, name='logout'),
    # HTML management pages
    path('outlets/', outlets_page, name='outlets'),
    path('machines/', machines_page, name='machines'),
    path('machines/delete/', machine_delete, name='machine_delete'),
    path('devices/bind/', device_bind, name='device_bind'),
    path('devices/unbind/', device_unbind, name='device_unbind'),
    # Testing UI routes (duplicate interfaces)
    path('test/devices/', test_devices_page, name='test_devices'),
    path('test/outlets/', test_outlets_page, name='test_outlets'),
    path('test/machines/', test_machines_page, name='test_machines'),
    path('test/stats/', test_stats_page, name='test_stats_page'),
    path('api/test/stats/', test_stats_api, name='test_stats_api'),
    path('api/test/stats-options/', test_stats_options, name='test_stats_options'),
    path('api/test/stats-export.csv', test_stats_export_csv, name='test_stats_export'),
    # Real-time data API
    path('api/devices-data/', devices_data_api, name='devices_data_api'),
    # New device endpoints (avoid conflict with router '/api/events/')
    path('api/handshake/', handshake),
    path('api/device/events/', events),
    # Router APIs
    path('api/', include(router.urls)),
    # Legacy and utilities
    path('api/iot/', iot_ingest),  # legacy
    path('api/export/', export_data),
    path('api/flush/', flush_all_data),
]

