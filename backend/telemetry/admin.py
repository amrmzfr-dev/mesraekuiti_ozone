from django.contrib import admin
from .models import (
    TelemetryRecord,
    TelemetryEvent,
    DeviceStatus,
    UsageStatistics,
    Outlet,
    Machine,
    MachineDevice,
    Device,
)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("mac", "device_id", "assigned", "firmware", "last_seen")
    search_fields = ("mac", "device_id")
    list_filter = ("assigned",)


@admin.register(DeviceStatus)
class DeviceStatusAdmin(admin.ModelAdmin):
    list_display = ("device_id", "last_seen", "wifi_connected", "current_count_basic", "current_count_standard", "current_count_premium")
    search_fields = ("device_id",)
    list_filter = ("wifi_connected",)


@admin.register(TelemetryEvent)
class TelemetryEventAdmin(admin.ModelAdmin):
    list_display = ("device_id", "event_type", "event_id", "occurred_at")
    search_fields = ("device_id", "event_id")
    list_filter = ("event_type",)


@admin.register(TelemetryRecord)
class TelemetryRecordAdmin(admin.ModelAdmin):
    list_display = ("device_id", "created_at")
    search_fields = ("device_id",)


@admin.register(UsageStatistics)
class UsageStatisticsAdmin(admin.ModelAdmin):
    list_display = ("device_id", "date", "total_events", "basic_count", "standard_count", "premium_count")
    search_fields = ("device_id",)


@admin.register(Outlet)
class OutletAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active",)


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ("name", "outlet", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active", "outlet")


@admin.register(MachineDevice)
class MachineDeviceAdmin(admin.ModelAdmin):
    list_display = ("machine", "device_id", "is_active")
    search_fields = ("device_id",)
    list_filter = ("is_active",)

