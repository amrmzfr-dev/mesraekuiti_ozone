from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    ROLE_ADMIN = 'admin'
    ROLE_P2 = 'p2'
    ROLE_DMM = 'dmm'
    ROLE_DEALER = 'dealer'
    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Admin'),
        (ROLE_P2, 'P2 (Perodua HQ)'),
        (ROLE_DMM, 'DMM (Perodua Dealer)'),
        (ROLE_DEALER, 'Dealer (Non-Perodua)'),
    ]

    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_DEALER)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class Outlet(models.Model):
    # Primary key as requested: outlet_id auto by the system
    outlet_id = models.AutoField(primary_key=True)

    # Business fields
    outlet_name = models.CharField(max_length=200)
    region = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Geographical region for reporting"
    )
    pic_sm = models.CharField(max_length=100, blank=True, null=True, help_text="Person in charge (SM)")
    sm_number = models.CharField(max_length=30, blank=True, null=True, help_text="SM phone number")
    total_sva = models.IntegerField(default=0, help_text="Total Service Advisors")
    avg_intake_service = models.IntegerField(default=0)
    num_machines = models.IntegerField(default=0, help_text="Number of machines at this outlet")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["outlet_name"]

    def __str__(self) -> str:
        return f"{self.outlet_name} (#{self.outlet_id})"


class Device(models.Model):
    mac = models.CharField(max_length=17, unique=True, help_text="MAC address of the ESP32 device", default="00:00:00:00:00:00")
    device_id = models.CharField(max_length=100, unique=True, help_text="Unique device identifier")
    firmware = models.CharField(max_length=50, blank=True, null=True, help_text="Firmware version")
    token = models.CharField(max_length=128, blank=True, null=True, help_text="Authentication token")
    assigned = models.BooleanField(default=False, help_text="Whether device is assigned to a machine")
    last_seen = models.DateTimeField(blank=True, null=True, help_text="Last time device was seen online")
    notes = models.TextField(blank=True, null=True, help_text="Additional notes about the device")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-last_seen', 'device_id']

    def __str__(self):
        return f"{self.device_id} ({self.mac})"


class Machine(models.Model):
    # Custom AutoField primary key, to mirror Outlet.outlet_id naming
    machine_id = models.AutoField(primary_key=True)
    machine_code = models.CharField(max_length=255)

    outlet = models.ForeignKey(
        Outlet,
        related_name='machines',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    device = models.OneToOneField(
        Device,
        related_name='machine',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Only one device (ESP32) can be bound at a time"
    )

    installed_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    @property
    def name(self) -> str:
        # Backward-compatible alias used by older code/templates
        return self.machine_code

    def __str__(self):
        outlet_name = self.outlet.outlet_name if self.outlet else "No outlet"
        return f"{self.machine_code} - {outlet_name}"


class DeviceStatus(models.Model):
    """Real-time status of ESP32 devices"""
    device_id = models.CharField(max_length=100, unique=True)
    wifi_connected = models.BooleanField(default=False)
    rtc_available = models.BooleanField(default=False)
    sd_card_available = models.BooleanField(default=False)
    current_count_basic = models.IntegerField(default=0)
    current_count_standard = models.IntegerField(default=0)
    current_count_premium = models.IntegerField(default=0)
    uptime_seconds = models.IntegerField(default=0)
    device_timestamp = models.CharField(max_length=50, blank=True, null=True)
    last_seen = models.DateTimeField(auto_now=True)
    last_poll = models.DateTimeField(null=True, blank=True, help_text="Last time ESP32 polled for commands")

    class Meta:
        ordering = ['-last_seen']

    def __str__(self):
        return f"Status: {self.device_id}"

    def get_accumulated_basic_count(self):
        """Get accumulated basic treatment count from events"""
        return TelemetryEvent.objects.filter(
            device_id=self.device_id,
            event_type='BASIC'
        ).count()

    def get_accumulated_standard_count(self):
        """Get accumulated standard treatment count from events"""
        return TelemetryEvent.objects.filter(
            device_id=self.device_id,
            event_type='STANDARD'
        ).count()

    def get_accumulated_premium_count(self):
        """Get accumulated premium treatment count from events"""
        return TelemetryEvent.objects.filter(
            device_id=self.device_id,
            event_type='PREMIUM'
        ).count()


class TelemetryEvent(models.Model):
    """Individual treatment events from ESP32 devices"""
    EVENT_CHOICES = [
        ('BASIC', 'Basic Treatment'),
        ('STANDARD', 'Standard Treatment'),
        ('PREMIUM', 'Premium Treatment'),
        ('status', 'Status Update'),
    ]

    device_id = models.CharField(max_length=100)
    event_id = models.CharField(max_length=100, unique=True, blank=True, null=True)
    event = models.CharField(max_length=50, default='treatment')
    treatment = models.CharField(max_length=20, blank=True, null=True)
    counter = models.IntegerField(blank=True, null=True)
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES, default='status')
    count_basic = models.IntegerField(blank=True, null=True)
    count_standard = models.IntegerField(blank=True, null=True)
    count_premium = models.IntegerField(blank=True, null=True)
    occurred_at = models.DateTimeField(auto_now_add=True)
    device_timestamp = models.CharField(max_length=50, blank=True, null=True)
    wifi_status = models.BooleanField(default=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-occurred_at']

    def __str__(self):
        return f"{self.device_id}: {self.event_type} at {self.occurred_at}"


class UsageStatistics(models.Model):
    """Daily usage statistics aggregated by device and outlet"""
    device_id = models.CharField(max_length=100)
    outlet_id = models.ForeignKey(Outlet, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField()
    basic_count = models.IntegerField(default=0)
    standard_count = models.IntegerField(default=0)
    premium_count = models.IntegerField(default=0)
    total_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['device_id', 'date']
        ordering = ['-date', 'device_id']

    def __str__(self):
        return f"{self.device_id} - {self.date}: {self.total_count} treatments"


class Command(models.Model):
    """Commands sent from backend to ESP32 devices"""
    
    COMMAND_TYPES = [
        ('RESET_COUNTERS', 'Reset Counters'),
        ('CLEAR_MEMORY', 'Clear Memory'),
        ('CLEAR_QUEUE', 'Clear Queue'),
        ('REBOOT_DEVICE', 'Reboot Device'),
        ('UPDATE_SETTINGS', 'Update Settings'),
        ('GET_STATUS', 'Get Status'),
        ('SYNC_TIME', 'Sync Time'),
        ('UPDATE_FIRMWARE', 'Update Firmware'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('executed', 'Executed'),
        ('failed', 'Failed'),
        ('timeout', 'Timeout'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    # Command identification
    command_id = models.CharField(max_length=100, unique=True, help_text="Unique command identifier")
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='commands')
    command_type = models.CharField(max_length=20, choices=COMMAND_TYPES)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    
    # Command data
    payload = models.JSONField(default=dict, blank=True, help_text="Command parameters/data")
    description = models.TextField(blank=True, help_text="Human-readable description")
    
    # Status tracking
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    
    # Response tracking
    response_data = models.JSONField(default=dict, blank=True, help_text="ESP32 response data")
    error_message = models.TextField(blank=True, help_text="Error message if failed")
    retry_count = models.IntegerField(default=0, help_text="Number of retry attempts")
    
    # Metadata
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Command expiration time")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['device', 'status']),
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.command_type} for {self.device.device_id} ({self.status})"
    
    def is_expired(self):
        """Check if command has expired"""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    def can_retry(self, max_retries=3):
        """Check if command can be retried"""
        return self.retry_count < max_retries and self.status in ['failed', 'timeout']


