"""
URL configuration for ozontelemetry project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from telemetry import views as tv
from telemetry.api import ingest, commands

urlpatterns = [
    path('admin/', admin.site.urls),
path('', tv.dashboard, name='root'),
path('dashboard/', tv.dashboard, name='dashboard'),
path('outlets/', tv.outlets_page, name='outlets_page'),
path('outlets/create/', tv.outlets_create, name='outlets_create'),
path('machines/', tv.machines_page, name='machines_page'),
path('machines/create/', tv.machines_create, name='machines_create'),
path('machines/<int:machine_id>/assign/', tv.machine_assign, name='machine_assign'),
path('machines/<int:machine_id>/unassign/', tv.machine_unassign, name='machine_unassign'),
path('machines/<int:machine_id>/delete/', tv.machine_delete, name='machine_delete'),
path('machines/<int:machine_id>/logs/', tv.machine_treatment_logs, name='machine_treatment_logs'),
path('api/machines/<int:machine_id>/logs/', tv.machine_logs_api, name='machine_logs_api'),
path('outlets/<int:outlet_id>/manage/', tv.outlet_manage, name='outlet_manage'),
path('outlets/<int:outlet_id>/assign/', tv.outlet_assign_machine, name='outlet_assign_machine'),
    # Devices pages
    path('devices/', tv.devices_page, name='devices_page'),
    path('devices/<str:device_id>/assign/', tv.device_assign, name='device_assign'),
    path('devices/<str:device_id>/unassign/', tv.device_unassign, name='device_unassign'),
    path('devices/<str:device_id>/commands/', tv.device_commands, name='device_commands'),
    path('devices/<str:device_id>/commands/create/', tv.create_command, name='create_command'),
    path('devices/<str:device_id>/', tv.device_detail, name='device_detail'),
    # Auth pages (HTMX)
    path('login/', tv.login_page, name='login_page'),
    path('login/submit/', tv.login_submit, name='login_submit'),
    path('register/', tv.register_page, name='register_page'),
    path('register/submit/', tv.register_submit, name='register_submit'),
    
    # API endpoints for ESP32 devices
    path('api/handshake/', ingest.handshake, name='handshake'),
    path('api/events/', ingest.events, name='events'),
    path('api/device/events/', ingest.events, name='device_events'),  # ESP32 uses this URL
    path('api/ingest/', ingest.iot_ingest, name='iot_ingest'),
    path('api/devices/', ingest.devices_data_api, name='devices_api'),
    path('api/devices/online/', ingest.devices_online_api, name='devices_online_api'),
    path('api/machines/unregistered/', ingest.machines_unregistered_api, name='machines_unregistered_api'),
    path('api/bind/', ingest.bind_device_to_machine, name='bind_device'),
    path('api/export/', ingest.export_data, name='export_data'),
    path('api/flush/', ingest.flush_all_data, name='flush_data'),
    path('api/flush-except-admin/', ingest.flush_all_but_admin, name='flush_except_admin'),
    
    # Command API endpoints
    path('api/device/<str:device_id>/commands/', commands.get_device_commands, name='get_device_commands'),
    path('api/device/<str:device_id>/commands/<str:command_id>/', commands.report_command_result, name='report_command_result'),
    path('api/device/<str:device_id>/commands/create/', commands.create_device_command, name='create_device_command'),
    path('api/device/<str:device_id>/commands/status/', commands.get_command_status, name='get_command_status'),
    path('api/commands/<str:command_id>/retry/', commands.retry_command, name='retry_command'),
    path('api/commands/bulk/', commands.bulk_create_commands, name='bulk_create_commands'),
]
