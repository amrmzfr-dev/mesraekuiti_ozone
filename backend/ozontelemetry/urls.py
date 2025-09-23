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
from rest_framework.routers import DefaultRouter
from rest_framework.response import Response
from telemetry.views.viewsets import (
    TelemetryViewSet, TelemetryEventViewSet, DeviceStatusViewSet, OutletViewSet, MachineViewSet,
)
from telemetry.api.ingest import iot_ingest, export_data, flush_all_data, handshake, events, devices_data_api, devices_online_api, machines_unregistered_api, flush_all_but_admin
from telemetry.api.stats import test_stats_api, test_stats_options, test_stats_export_csv
from telemetry.auth_views import (
    api_login, api_logout, api_user_info, api_register, api_check_auth, api_csrf
)


router = DefaultRouter()
router.register(r'telemetry', TelemetryViewSet, basename='telemetry')
router.register(r'events', TelemetryEventViewSet, basename='events')
router.register(r'devices', DeviceStatusViewSet, basename='devices')
router.register(r'outlets', OutletViewSet, basename='outlets')
router.register(r'machines', MachineViewSet, basename='machines')

urlpatterns = [
    # Admin interface (keep for backend management)
    path('admin/', admin.site.urls),
    
    # API Authentication endpoints
    path('api/auth/login/', api_login, name='api_login'),
    path('api/auth/logout/', api_logout, name='api_logout'),
    path('api/auth/register/', api_register, name='api_register'),
    path('api/auth/user/', api_user_info, name='api_user_info'),
    path('api/auth/check/', api_check_auth, name='api_check_auth'),
    path('api/csrf/', api_csrf, name='api_csrf'),
    
    # Analytics and statistics APIs (pure API, no HTML pages)
    path('api/test/stats/', test_stats_api, name='test_stats_api'),
    path('api/test/stats-options/', test_stats_options, name='test_stats_options'),
    path('api/test/stats-export.csv', test_stats_export_csv, name='test_stats_export'),
    
    # Real-time data API
    path('api/devices-data/', devices_data_api, name='devices_data_api'),
    path('api/devices/online/', devices_online_api, name='devices_online_api'),
    path('api/machines/unregistered/', machines_unregistered_api, name='machines_unregistered_api'),
    
    # Device endpoints
    path('api/handshake/', handshake),
    path('api/device/events/', events),
    
    # Router APIs (CRUD operations)
    path('api/', include(router.urls)),
    
    # Legacy and utilities
    path('api/iot/', iot_ingest),  # legacy
    path('api/export/', export_data),
    path('api/flush/', flush_all_data),
    path('api/flush-except-admin/', flush_all_but_admin),
    
    # Root health/info endpoint
    path('', lambda request: JsonResponse({'message': 'Ozone Telemetry API Backend', 'admin': '/admin/'})),
]

# Force JSON errors instead of HTML
def _json_error_response(message, status_code):
    return JsonResponse({'detail': message}, status=status_code)

def json_404(request, exception):
    return _json_error_response('Not found', 404)

def json_500(request):
    return _json_error_response('Server error', 500)

# Register handlers
handler404 = 'ozontelemetry.urls.json_404'
handler500 = 'ozontelemetry.urls.json_500'

