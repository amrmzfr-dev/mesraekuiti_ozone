from django.db import models

class Device(models.Model):
    """Registered hardware device (ESP32)."""
    mac = models.CharField(max_length=32, unique=True, db_index=True)
    device_id = models.CharField(max_length=128, unique=True, db_index=True)
    token = models.CharField(max_length=128, unique=True)  # bearer token for auth
    assigned = models.BooleanField(default=False)
    firmware = models.CharField(max_length=50, null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen", "device_id"]

    def __str__(self) -> str:
        return f"{self.device_id} ({self.mac})"


class TelemetryEvent(models.Model):
    EVENT_BASIC = "BASIC"
    EVENT_STANDARD = "STANDARD"
    EVENT_PREMIUM = "PREMIUM"
    EVENT_STATUS = "status"
    EVENT_CHOICES = [
        (EVENT_BASIC, "BASIC"),
        (EVENT_STANDARD, "STANDARD"),
        (EVENT_PREMIUM, "PREMIUM"),
        (EVENT_STATUS, "Status Update"),
    ]

    device_id = models.CharField(max_length=128, db_index=True)
    # Legacy fields (kept for compatibility)
    event_type = models.CharField(max_length=16, choices=EVENT_CHOICES)
    count_basic = models.IntegerField(null=True, blank=True)
    count_standard = models.IntegerField(null=True, blank=True)
    count_premium = models.IntegerField(null=True, blank=True)
    occurred_at = models.DateTimeField(db_index=True)
    device_timestamp = models.CharField(max_length=25, null=True, blank=True, help_text="Timestamp from ESP32 device")
    wifi_status = models.BooleanField(null=True, blank=True, help_text="WiFi connection status")
    payload = models.JSONField(null=True, blank=True)

    # New fields for current firmware protocol (idempotent ingest)
    event_id = models.CharField(max_length=128, unique=True, null=True, blank=True, db_index=True)
    event = models.CharField(max_length=32, null=True, blank=True, help_text="e.g., 'treatment'")
    treatment = models.CharField(max_length=16, null=True, blank=True, help_text="BASIC|STANDARD|PREMIUM")
    counter = models.IntegerField(null=True, blank=True, help_text="Counter value at press time")

    class Meta:
        ordering = ["-occurred_at", "-id"]

    def __str__(self) -> str:
        return f"{self.device_id} {self.event or self.event_type} @ {self.occurred_at.isoformat()}"


class DeviceStatus(models.Model):
    """Track current status of each device"""
    device_id = models.CharField(max_length=128, unique=True, db_index=True)
    last_seen = models.DateTimeField(auto_now=True)
    wifi_connected = models.BooleanField(default=False)
    rtc_available = models.BooleanField(default=False)
    sd_card_available = models.BooleanField(default=False)
    current_count_basic = models.IntegerField(default=0)
    current_count_standard = models.IntegerField(default=0)
    current_count_premium = models.IntegerField(default=0)
    uptime_seconds = models.IntegerField(null=True, blank=True)
    device_timestamp = models.CharField(max_length=25, null=True, blank=True)
    
    class Meta:
        ordering = ["-last_seen"]
    
    def __str__(self) -> str:
        return f"{self.device_id} - Last seen: {self.last_seen}"
    
    def get_accumulated_basic_count(self):
        """Get accumulated basic count from database events"""
        from django.db.models import Count
        return TelemetryEvent.objects.filter(
            device_id=self.device_id,
            event_type='BASIC'
        ).count()
    
    def get_accumulated_standard_count(self):
        """Get accumulated standard count from database events"""
        from django.db.models import Count
        return TelemetryEvent.objects.filter(
            device_id=self.device_id,
            event_type='STANDARD'
        ).count()
    
    def get_accumulated_premium_count(self):
        """Get accumulated premium count from database events"""
        from django.db.models import Count
        return TelemetryEvent.objects.filter(
            device_id=self.device_id,
            event_type='PREMIUM'
        ).count()
    
    def update_accumulated_counts(self):
        """Update the current counts with accumulated values from database"""
        self.current_count_basic = self.get_accumulated_basic_count()
        self.current_count_standard = self.get_accumulated_standard_count()
        self.current_count_premium = self.get_accumulated_premium_count()
        self.save()


class UsageStatistics(models.Model):
    """Daily usage statistics for analytics"""
    device_id = models.CharField(max_length=128, db_index=True)
    date = models.DateField(db_index=True)
    basic_count = models.IntegerField(default=0)
    standard_count = models.IntegerField(default=0)
    premium_count = models.IntegerField(default=0)
    total_events = models.IntegerField(default=0)
    first_event = models.DateTimeField(null=True, blank=True)
    last_event = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['device_id', 'date']
        ordering = ["-date", "-device_id"]

    def __str__(self) -> str:
        return f"{self.device_id} - {self.date}: {self.total_events} events"


class Outlet(models.Model):
    """Outlet/Location where machines are installed"""
    name = models.CharField(max_length=200, unique=True)
    location = models.CharField(max_length=300, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    contact_person = models.CharField(max_length=100, null=True, blank=True)
    contact_phone = models.CharField(max_length=20, null=True, blank=True)
    # Additional owner-maintained metrics (optional)
    total_sva = models.IntegerField(null=True, blank=True, help_text="Total Service Advisors")
    average_intage_services = models.IntegerField(null=True, blank=True, help_text="Average intage services")
    number_of_machines = models.IntegerField(null=True, blank=True, help_text="Number of machines at outlet")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["name"]
    
    def __str__(self) -> str:
        return f"{self.name} ({self.location or 'No location'})"


class Machine(models.Model):
    """Machine registered to an outlet - can have multiple devices over time"""
    outlet = models.ForeignKey(Outlet, on_delete=models.CASCADE, related_name='machines', null=True, blank=True)
    name = models.CharField(max_length=200, null=True, blank=True)
    machine_type = models.CharField(max_length=50, default='Ozone Generator')
    is_active = models.BooleanField(default=True)
    installed_date = models.DateField(null=True, blank=True)
    last_maintenance = models.DateField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["outlet__name", "name"]
    
    def __str__(self) -> str:
        outlet_name = self.outlet.name if self.outlet else 'No outlet'
        return f"{self.name or f'Machine-{self.id}'} @ {outlet_name}"
    
    @property
    def current_device(self):
        """Get the currently active device for this machine"""
        return self.devices.filter(is_active=True).first()
    
    @property
    def current_device_id(self):
        """Get the device_id of the currently active device"""
        current = self.current_device
        return current.device_id if current else None


class MachineDevice(models.Model):
    """ESP32 assigned to a machine. Exactly one can be active at a time.

    History is preserved by marking previous bindings inactive with a
    timestamp in `deactivated_date`. This allows a machine to show all
    previously connected ESP32 identifiers while enforcing a single
    active binding currently.
    """
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name='devices')
    device_id = models.CharField(max_length=128, db_index=True)
    is_active = models.BooleanField(default=True)
    assigned_date = models.DateTimeField(auto_now_add=True)
    deactivated_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    
    class Meta:
        ordering = ["-is_active", "-assigned_date"]
        unique_together = ['machine', 'device_id']  # Same device can't be assigned to same machine twice
    
    def __str__(self) -> str:
        status = "Active" if self.is_active else "Inactive"
        return f"{self.device_id} ({status}) - {self.machine.name}"
    
    def deactivate(self):
        """Deactivate this device"""
        from django.utils import timezone
        self.is_active = False
        self.deactivated_date = timezone.now()
        self.save()