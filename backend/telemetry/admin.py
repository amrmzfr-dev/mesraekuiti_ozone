from django.contrib import admin
from .models import (
    TelemetryEvent,
    DeviceStatus,
    UsageStatistics,
    Outlet,
    Machine,
    MachineDevice,
)


@admin.register(TelemetryEvent)
class TelemetryEventAdmin(admin.ModelAdmin):
    list_display = ("device_id", "event_type", "occurred_at")
    search_fields = ("device_id", "event_type")
    list_filter = ("event_type",)


@admin.register(DeviceStatus)
class DeviceStatusAdmin(admin.ModelAdmin):
    list_display = ("device_id", "last_seen", "wifi_connected")
    search_fields = ("device_id",)
    list_filter = ("wifi_connected",)


@admin.register(UsageStatistics)
class UsageStatisticsAdmin(admin.ModelAdmin):
    list_display = ("device_id", "date", "total_events")
    search_fields = ("device_id",)
    list_filter = ("date",)


@admin.register(Outlet)
class OutletAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "is_active")
    search_fields = ("name", "location")
    list_filter = ("is_active",)


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ("name", "outlet", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active", "outlet")


@admin.register(MachineDevice)
class MachineDeviceAdmin(admin.ModelAdmin):
    list_display = ("device_id", "machine", "is_active")
    search_fields = ("device_id",)
    list_filter = ("is_active",)

