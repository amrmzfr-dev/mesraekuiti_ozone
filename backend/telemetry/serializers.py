from rest_framework import serializers
from .models import TelemetryEvent, DeviceStatus, UsageStatistics, Outlet, Machine, MachineDevice, Device


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
    machines = serializers.SerializerMethodField()
    total_treatments = serializers.SerializerMethodField()
    
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
            "machines",
            "total_treatments",
        ]
    
    def get_machine_count(self, obj):
        return obj.machines.filter(is_active=True).count()

    def get_machines(self, obj):
        from .serializers import MachineSerializer
        qs = obj.machines.select_related('outlet').all()
        return MachineSerializer(qs, many=True).data

    def get_total_treatments(self, obj):
        from .models import TelemetryEvent
        # Sum BASIC/STANDARD/PREMIUM counts for machines under this outlet
        device_ids = list(obj.machines.values_list('devices__device_id', flat=True))
        device_ids = [d for d in device_ids if d]
        if not device_ids:
            return {"basic": 0, "standard": 0, "premium": 0, "total": 0}
        basic = TelemetryEvent.objects.filter(device_id__in=device_ids, event_type='BASIC').count()
        standard = TelemetryEvent.objects.filter(device_id__in=device_ids, event_type='STANDARD').count()
        premium = TelemetryEvent.objects.filter(device_id__in=device_ids, event_type='PREMIUM').count()
        return {"basic": basic, "standard": standard, "premium": premium, "total": basic+standard+premium}


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


class DeviceSerializer(serializers.ModelSerializer):
    bound_machine = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = [
            'mac', 'device_id', 'assigned', 'firmware', 'last_seen', 'notes', 'bound_machine'
        ]

    def get_bound_machine(self, obj):
        mapping = MachineDevice.objects.filter(device_id=obj.device_id, is_active=True).select_related('machine').first()
        if mapping:
            return {
                'id': mapping.machine.id,
                'name': mapping.machine.name,
                'outlet': mapping.machine.outlet_id,
                'outlet_name': mapping.machine.outlet.name if mapping.machine.outlet else None,
            }
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

