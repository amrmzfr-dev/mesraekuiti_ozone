from rest_framework import serializers
from .models import TelemetryRecord, TelemetryEvent, DeviceStatus, UsageStatistics, Outlet, Machine, MachineDevice


class TelemetryRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelemetryRecord
        fields = [
            "id",
            "device_id",
            "temperature_c",
            "humidity_percent",
            "pressure_hpa",
            "voltage_v",
            "rssi_dbm",
            "payload",
            "created_at",
        ]


class TelemetryEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelemetryEvent
        fields = [
            "id",
            "device_id",
            "event_type",
            "count_basic",
            "count_standard",
            "count_premium",
            "occurred_at",
            "device_timestamp",
            "wifi_status",
            "payload",
        ]


class DeviceStatusSerializer(serializers.ModelSerializer):
    # Override the count fields to return accumulated values
    current_count_basic = serializers.SerializerMethodField()
    current_count_standard = serializers.SerializerMethodField()
    current_count_premium = serializers.SerializerMethodField()
    
    class Meta:
        model = DeviceStatus
        fields = [
            "device_id",
            "last_seen",
            "wifi_connected",
            "rtc_available",
            "sd_card_available",
            "current_count_basic",
            "current_count_standard",
            "current_count_premium",
            "uptime_seconds",
            "device_timestamp",
        ]
    
    def get_current_count_basic(self, obj):
        return obj.get_accumulated_basic_count()
    
    def get_current_count_standard(self, obj):
        return obj.get_accumulated_standard_count()
    
    def get_current_count_premium(self, obj):
        return obj.get_accumulated_premium_count()


class UsageStatisticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageStatistics
        fields = [
            "device_id",
            "date",
            "basic_count",
            "standard_count",
            "premium_count",
            "total_events",
            "first_event",
            "last_event",
        ]


class OutletSerializer(serializers.ModelSerializer):
    machine_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Outlet
        fields = [
            "id",
            "name",
            "location",
            "address",
            "contact_person",
            "contact_phone",
            "is_active",
            "created_at",
            "updated_at",
            "machine_count",
        ]
    
    def get_machine_count(self, obj):
        return obj.machines.filter(is_active=True).count()


class MachineDeviceSerializer(serializers.ModelSerializer):
    device_status = serializers.SerializerMethodField()
    
    class Meta:
        model = MachineDevice
        fields = [
            "id",
            "device_id",
            "is_active",
            "assigned_date",
            "deactivated_date",
            "notes",
            "device_status"
        ]
    
    def get_device_status(self, obj):
        """Get device status for this device"""
        try:
            device_status = DeviceStatus.objects.get(device_id=obj.device_id)
            return DeviceStatusSerializer(device_status).data
        except DeviceStatus.DoesNotExist:
            return None


class MachineSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)
    outlet_location = serializers.CharField(source='outlet.location', read_only=True)
    current_device_id = serializers.ReadOnlyField()
    devices = MachineDeviceSerializer(many=True, read_only=True)
    current_device = serializers.SerializerMethodField()
    device_status = serializers.SerializerMethodField()
    
    class Meta:
        model = Machine
        fields = [
            "id",
            "outlet",
            "outlet_name",
            "outlet_location",
            "name",
            "machine_type",
            "is_active",
            "installed_date",
            "last_maintenance",
            "notes",
            "created_at",
            "updated_at",
            "current_device_id",
            "devices",
            "current_device",
            "device_status"
        ]
    
    def get_current_device(self, obj):
        """Get the currently active device"""
        current = obj.current_device
        if current:
            return MachineDeviceSerializer(current).data
        return None
    
    def get_device_status(self, obj):
        """Get device status for the currently active device"""
        current = obj.current_device
        if current:
            try:
                device_status = DeviceStatus.objects.get(device_id=current.device_id)
                return DeviceStatusSerializer(device_status).data
            except DeviceStatus.DoesNotExist:
                return None
        return None

