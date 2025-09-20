from rest_framework import viewsets, mixins, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes
from django.utils import timezone
from django.db.models import Sum, Count, Q, Min, Max
from django.db.models.functions import TruncDate, TruncHour, TruncMinute, TruncMonth
from datetime import datetime, timedelta
from .models import TelemetryEvent, DeviceStatus, UsageStatistics, Outlet, Machine, MachineDevice, Device
from .serializers import TelemetryEventSerializer, DeviceStatusSerializer, UsageStatisticsSerializer, OutletSerializer, MachineSerializer
from django.db import transaction
import secrets
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.utils.dateparse import parse_date


class TelemetryViewSet(mixins.ListModelMixin,
                       mixins.RetrieveModelMixin,
                       viewsets.GenericViewSet):
    queryset = DeviceStatus.objects.all().order_by('-last_seen')
    serializer_class = DeviceStatusSerializer
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=["get"], url_path="latest")
    def latest(self, request):
        device_id = request.query_params.get("device_id")
        qs = self.get_queryset()
        if device_id:
            qs = qs.filter(device_id=device_id)
        status_obj = qs.first()
        if not status_obj:
            return Response({}, status=200)
        return Response(self.get_serializer(status_obj).data)

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        device_id = request.query_params.get("device_id")
        qs = self.get_queryset()
        if device_id:
            qs = qs.filter(device_id=device_id)
        record = TelemetryEvent.objects.filter(device_id=device_id).order_by('-occurred_at').first()
        if not record:
            return Response({"device_id": device_id, "latest": None}, status=200)
        # Extract ESP32-style fields if present
        payload = record.payload or {}
        data = {
            "device_id": record.device_id,
            "mode": payload.get("mode"),
            "counts": {
                "basic": payload.get("count1"),
                "standard": payload.get("count2"),
                "premium": payload.get("count3"),
            },
            "on_time": {
                "basic": payload.get("type1"),
                "standard": payload.get("type2"),
                "premium": payload.get("type3"),
            },
            "created_at": record.occurred_at,
        }
        return Response(data)


@api_view(["POST"]) 
@permission_classes([permissions.AllowAny])
def iot_ingest(request):
    """Accept ESP32 form-urlencoded payload and update DeviceStatus and events only.

    Expected fields:
      - mode: "status" or one of BASIC|STANDARD|PREMIUM
      - macaddr: device identifier
      - type1, type2, type3
      - count1, count2, count3
      - timestamp: ESP32 device timestamp (optional)
    """
    mode = request.data.get("mode")
    macaddr = request.data.get("macaddr")
    type1 = request.data.get("type1")
    type2 = request.data.get("type2")
    type3 = request.data.get("type3")
    count1 = request.data.get("count1")
    count2 = request.data.get("count2")
    count3 = request.data.get("count3")
    device_timestamp = request.data.get("timestamp")
    rtc_available_raw = request.data.get("rtc_available", None)
    sd_available_raw = request.data.get("sd_available", None)
    rtc_available = None if rtc_available_raw is None else str(rtc_available_raw).lower() == "true"
    sd_available = None if sd_available_raw is None else str(sd_available_raw).lower() == "true"

    if not macaddr:
        return Response({"detail": "macaddr required"}, status=status.HTTP_400_BAD_REQUEST)

    # Parse device timestamp if provided
    occurred_at = timezone.now()
    if device_timestamp:
        parsed = _parse_device_timestamp(device_timestamp)
        if parsed:
            occurred_at = parsed

    # Create or update device status
    device_status, created = DeviceStatus.objects.get_or_create(
        device_id=str(macaddr),
        defaults={
            'wifi_connected': True,
            'rtc_available': bool(rtc_available) if rtc_available is not None else False,
            'sd_card_available': bool(sd_available) if sd_available is not None else False,
            'current_count_basic': _safe_number(count1) or 0,
            'current_count_standard': _safe_number(count2) or 0,
            'current_count_premium': _safe_number(count3) or 0,
            'device_timestamp': device_timestamp,
        }
    )
    
    if not created:
        device_status.wifi_connected = True
        if rtc_available is not None:
            device_status.rtc_available = rtc_available
        if sd_available is not None:
            device_status.sd_card_available = sd_available
        device_status.current_count_basic = _safe_number(count1) or 0
        device_status.current_count_standard = _safe_number(count2) or 0
        device_status.current_count_premium = _safe_number(count3) or 0
        device_status.device_timestamp = device_timestamp
        device_status.save()

    # Determine event type (status = heartbeat)
    event_type = mode if mode in {"BASIC", "STANDARD", "PREMIUM", "status"} else "status"

    # Persist events only for real triggers (exclude heartbeat "status")
    if event_type != "status":
        TelemetryEvent.objects.create(
            device_id=str(macaddr),
            event_type=event_type,
            count_basic=_safe_number(count1),
            count_standard=_safe_number(count2),
            count_premium=_safe_number(count3),
            occurred_at=occurred_at,
            device_timestamp=device_timestamp,
            wifi_status=True,
            payload={
                "type1": _safe_number(type1),
                "type2": _safe_number(type2),
                "type3": _safe_number(type3),
            },
        )

        _update_daily_statistics(str(macaddr), event_type, occurred_at)

    return Response({"status": "ok"})


def _parse_device_timestamp(value):
    """Parse ESP32 device timestamp format: '2024-01-15 14:30:25'"""
    try:
        if not value:
            return None
        # ESP32 format: "2024-01-15 14:30:25" - Now synced with NTP (Kuala Lumpur time)
        dt = datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
        return timezone.make_aware(dt)
    except Exception:
        return None

def _parse_timestamp(value):
    try:
        # epoch seconds
        if str(value).isdigit():
            return timezone.datetime.fromtimestamp(int(value), tz=timezone.utc)
        # ISO 8601
        from django.utils.dateparse import parse_datetime
        dt = parse_datetime(str(value))
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def _update_daily_statistics(device_id, event_type, occurred_at):
    """Update daily usage statistics"""
    try:
        date = occurred_at.date()
        stats, created = UsageStatistics.objects.get_or_create(
            device_id=device_id,
            date=date,
            defaults={
                'first_event': occurred_at,
                'last_event': occurred_at,
            }
        )
        
        if not created:
            if not stats.first_event or occurred_at < stats.first_event:
                stats.first_event = occurred_at
            if not stats.last_event or occurred_at > stats.last_event:
                stats.last_event = occurred_at
        
        # Update counts based on event type
        if event_type == "BASIC":
            stats.basic_count += 1
        elif event_type == "STANDARD":
            stats.standard_count += 1
        elif event_type == "PREMIUM":
            stats.premium_count += 1
        
        stats.total_events += 1
        stats.save()
    except Exception as e:
        print(f"Error updating daily statistics: {e}")


class TelemetryEventViewSet(mixins.ListModelMixin,
                            mixins.RetrieveModelMixin,
                            viewsets.GenericViewSet):
    queryset = TelemetryEvent.objects.all()
    serializer_class = TelemetryEventSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device_id")
        days = self.request.query_params.get("days")
        exclude_status = self.request.query_params.get("exclude_status")
        
        if device_id:
            qs = qs.filter(device_id=device_id)
            
        if days:
            from datetime import timedelta
            from django.utils import timezone
            days_int = int(days)
            qs = qs.filter(occurred_at__gte=timezone.now() - timedelta(days=days_int))
            
        if exclude_status:
            qs = qs.exclude(event_type='status')
            
        return qs.order_by('-occurred_at')

    @action(detail=False, methods=["get"], url_path="analytics")
    def analytics(self, request):
        """Get usage analytics for a device"""
        device_id = request.query_params.get("device_id")
        days = int(request.query_params.get("days", 7))
        
        if not device_id:
            return Response({"detail": "device_id required"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Use consistent time range for both queries
        end_datetime = timezone.now()
        start_datetime = end_datetime - timedelta(days=days)
        
        # Convert to dates for UsageStatistics (daily aggregated data)
        end_date = end_datetime.date()
        start_date = start_datetime.date()
        
        # Get daily statistics
        daily_stats = UsageStatistics.objects.filter(
            device_id=device_id,
            date__gte=start_date,
            date__lte=end_date
        ).order_by('date')
        
        # Get recent events (exclude heartbeats/status) - use same time range
        recent_events = TelemetryEvent.objects.filter(
            device_id=device_id,
            occurred_at__gte=start_datetime,
            occurred_at__lte=end_datetime
        ).exclude(event_type='status').order_by('-occurred_at')[:50]
        
        # Calculate totals from UsageStatistics (daily aggregated data)
        total_events = daily_stats.aggregate(
            total=Sum('total_events'),
            basic=Sum('basic_count'),
            standard=Sum('standard_count'),
            premium=Sum('premium_count')
        )
        
        # Also calculate totals from individual events for comparison
        event_totals = recent_events.aggregate(
            total_events=Count('id'),
            basic_events=Count('id', filter=Q(event_type='BASIC')),
            standard_events=Count('id', filter=Q(event_type='STANDARD')),
            premium_events=Count('id', filter=Q(event_type='PREMIUM'))
        )
        
        data = {
            "device_id": device_id,
            "period": {
                "start_date": start_datetime.isoformat(),
                "end_date": end_datetime.isoformat(),
                "days": days
            },
            "totals": {
                "total": event_totals['total_events'] or 0,
                "basic": event_totals['basic_events'] or 0,
                "standard": event_totals['standard_events'] or 0,
                "premium": event_totals['premium_events'] or 0
            },
            "daily_stats": UsageStatisticsSerializer(daily_stats, many=True).data,
            "recent_events": TelemetryEventSerializer(recent_events, many=True).data
        }
        
        return Response(data)


class DeviceStatusViewSet(mixins.ListModelMixin,
                         mixins.RetrieveModelMixin,
                         viewsets.GenericViewSet):
    queryset = DeviceStatus.objects.all()
    serializer_class = DeviceStatusSerializer
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=["get"], url_path="online")
    def online_devices(self, request):
        """Get list of online devices"""
        recent_threshold = timezone.now() - timedelta(minutes=5)
        online_devices = self.get_queryset().filter(last_seen__gte=recent_threshold)
        return Response(DeviceStatusSerializer(online_devices, many=True).data)

    @action(detail=False, methods=["get"], url_path="all")
    def all_devices(self, request):
        """Get list of all devices (online and offline)"""
        all_devices = self.get_queryset().order_by('-last_seen')
        return Response(DeviceStatusSerializer(all_devices, many=True).data)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def export_data(request):
    """Export telemetry data as CSV"""
    device_id = request.query_params.get("device_id")
    days = int(request.query_params.get("days", 30))
    
    if not device_id:
        return Response({"detail": "device_id required"}, status=status.HTTP_400_BAD_REQUEST)
    
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)
    
    events = TelemetryEvent.objects.filter(
        device_id=device_id,
        occurred_at__gte=start_date,
        occurred_at__lte=end_date
    ).order_by('occurred_at')
    
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="telemetry_{device_id}_{start_date.date()}_to_{end_date.date()}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Timestamp', 'Device Timestamp', 'Event Type', 'Basic Count', 'Standard Count', 'Premium Count', 'WiFi Status'])
    
    for event in events:
        writer.writerow([
            event.occurred_at.isoformat(),
            event.device_timestamp or '',
            event.event_type,
            event.count_basic or 0,
            event.count_standard or 0,
            event.count_premium or 0,
            'Connected' if event.wifi_status else 'Disconnected'
        ])
    
    return response


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def flush_all_data(request):
    """Dangerous: wipe all telemetry tables. Intended for admin/testing via UI button.

    Deletes TelemetryEvent, UsageStatistics, and DeviceStatus.
    """
    try:
        with transaction.atomic():
            TelemetryEvent.objects.all().delete()
            UsageStatistics.objects.all().delete()
            DeviceStatus.objects.all().delete()
        return Response({"status": "flushed"})
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _safe_number(value):
    try:
        if value is None:
            return None
        # try int first, then float
        iv = int(str(value))
        return iv
    except Exception:
        try:
            fv = float(str(value))
            return fv
        except Exception:
            return None


class OutletViewSet(viewsets.ModelViewSet):
    """CRUD operations for Outlets"""
    queryset = Outlet.objects.all()
    serializer_class = OutletSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        qs = super().get_queryset()
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == 'true')
        return qs


class MachineViewSet(viewsets.ModelViewSet):
    """CRUD operations for Machines"""
    queryset = Machine.objects.select_related('outlet').all()
    serializer_class = MachineSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        qs = super().get_queryset()
        outlet_id = self.request.query_params.get('outlet_id')
        is_active = self.request.query_params.get('is_active')
        device_id = self.request.query_params.get('device_id')
        
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == 'true')
        if device_id:
            # Filter by current device_id
            qs = qs.filter(devices__device_id=device_id, devices__is_active=True)
        return qs
    
    @action(detail=False, methods=["get"], url_path="unregistered")
    def unregistered_devices(self, request):
        """Get devices that have telemetry data but are not registered as machines"""
        registered_device_ids = set(MachineDevice.objects.values_list('device_id', flat=True))
        unregistered_devices = DeviceStatus.objects.exclude(device_id__in=registered_device_ids)
        return Response(DeviceStatusSerializer(unregistered_devices, many=True).data)
    
    @action(detail=False, methods=["post"], url_path="register")
    def register_device(self, request):
        """Register a device as a machine to an outlet"""
        device_id = request.data.get('device_id')
        outlet_id = request.data.get('outlet_id')
        name = request.data.get('name', '')
        
        if not device_id or not outlet_id:
            return Response({"detail": "device_id and outlet_id required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            outlet = Outlet.objects.get(id=outlet_id)
        except Outlet.DoesNotExist:
            return Response({"detail": "Outlet not found"}, status=status.HTTP_404_NOT_FOUND)
        
        if MachineDevice.objects.filter(device_id=device_id, is_active=True).exists():
            return Response({"detail": "Device already registered"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Create machine
        machine = Machine.objects.create(
            outlet=outlet,
            name=name or f"Machine {device_id[-6:]}"
        )
        
        # Create machine device relationship
        MachineDevice.objects.create(
            machine=machine,
            device_id=device_id,
            is_active=True
        )
        
        return Response(MachineSerializer(machine).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def handshake(request):
    """Device handshake to obtain device_id and token after admin assignment.

    Request JSON: { mac: string, firmware: string }
    Response JSON: { device_id, token, assigned }
    """
    mac = (request.data.get("mac") or "").strip()
    firmware = (request.data.get("firmware") or "").strip()
    if not mac:
        return Response({"detail": "mac required"}, status=status.HTTP_400_BAD_REQUEST)

    device = Device.objects.filter(mac=mac).first()
    if not device:
        # Create stub, not assigned yet; admin must assign device_id later
        device = Device.objects.create(
            mac=mac, device_id=f"pending-{mac[-6:]}", token=secrets.token_urlsafe(24), assigned=False, firmware=firmware
        )
    else:
        # Update firmware and last_seen
        device.firmware = firmware or device.firmware
        device.last_seen = timezone.now()
        device.save()

    # Ensure a DeviceStatus row exists and mark device as seen online now
    ds, _ = DeviceStatus.objects.get_or_create(device_id=device.device_id)
    ds.wifi_connected = True
    ds.last_seen = timezone.now()
    ds.device_timestamp = None
    ds.save()

    return Response({
        "device_id": device.device_id,
        "token": device.token,
        "assigned": device.assigned,
    })


def _auth_device(request):
    """Extract and validate bearer token; return Device or None."""
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    return Device.objects.filter(token=token, assigned=True).first()


@api_view(["POST"]) 
@permission_classes([permissions.AllowAny])
def events(request):
    """Ingest idempotent treatment events from device.

    JSON body:
      { device_id, firmware, event_id, event: "treatment", treatment: "BASIC|STANDARD|PREMIUM", counter: int, ts: ISO8601 }

    Returns: { ack: true, event_id }
    """
    device = _auth_device(request)
    if not device:
        return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    data = request.data
    event_id = (data.get("event_id") or "").strip()
    event = (data.get("event") or "").strip()
    treatment = (data.get("treatment") or "").strip()
    counter = data.get("counter")
    ts = data.get("ts")

    if not event_id:
        return Response({"detail": "event_id required"}, status=status.HTTP_400_BAD_REQUEST)
    if event != "treatment" or treatment not in {"BASIC", "STANDARD", "PREMIUM"}:
        return Response({"detail": "invalid event/treatment"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        counter = int(counter)
    except Exception:
        return Response({"detail": "counter must be int"}, status=status.HTTP_400_BAD_REQUEST)

    # Idempotency: if already exists, ack
    existing = TelemetryEvent.objects.filter(event_id=event_id).first()
    if existing:
        return Response({"ack": True, "event_id": event_id})

    occurred_at = _parse_timestamp(ts) or timezone.now()

    # Persist event
    TelemetryEvent.objects.create(
        device_id=device.device_id,
        event_id=event_id,
        event=event,
        treatment=treatment,
        counter=counter,
        occurred_at=occurred_at,
        event_type=treatment,  # for legacy compatibility
        count_basic=None,
        count_standard=None,
        count_premium=None,
        device_timestamp=ts,
        wifi_status=True,
        payload={},
    )

    # Update status
    ds, _ = DeviceStatus.objects.get_or_create(device_id=device.device_id)
    ds.wifi_connected = True
    ds.device_timestamp = ts
    ds.last_seen = timezone.now()
    if treatment == "BASIC":
        ds.current_count_basic = counter
    elif treatment == "STANDARD":
        ds.current_count_standard = counter
    elif treatment == "PREMIUM":
        ds.current_count_premium = counter
    ds.save()

    # Update daily stats
    _update_daily_statistics(device.device_id, treatment, occurred_at)

    return Response({"ack": True, "event_id": event_id})


# ---------------- Template Views (Django HTML) ----------------
@login_required(login_url='/accounts/login/')
def devices_list_page(request):
    """Render a simple page listing registered devices with last seen info."""
    devices = Device.objects.all().order_by('-last_seen', 'device_id')
    # Build a lightweight context for template consumption
    context_devices = []
    # Map device_id -> DeviceStatus for quick lookup
    status_map = {ds.device_id: ds for ds in DeviceStatus.objects.all()}
    for d in devices:
        ds = status_map.get(d.device_id)
        context_devices.append({
            'device_id': d.device_id,
            'mac': d.mac,
            'assigned': d.assigned,
            'firmware': d.firmware,
            'last_seen': d.last_seen or (ds.last_seen if ds else None),
            'online': bool(ds and ds.last_seen and ds.last_seen >= timezone.now() - timedelta(minutes=5)),
            'counts': {
                'basic': getattr(ds, 'current_count_basic', None) if ds else None,
                'standard': getattr(ds, 'current_count_standard', None) if ds else None,
                'premium': getattr(ds, 'current_count_premium', None) if ds else None,
            }
        })
    return render(request, 'telemetry/devices_list.html', { 'devices': context_devices })


# ---------------- Testing UI (HTML under /test/*) ----------------
@login_required(login_url='/accounts/login/')
@require_GET
def test_devices_page(request):
    return devices_list_page(request)


@login_required(login_url='/accounts/login/')
@require_GET
def test_outlets_page(request):
    return outlets_page(request)


@login_required(login_url='/accounts/login/')
@require_GET
def test_machines_page(request):
    return machines_page(request)


@api_view(["GET"]) 
@permission_classes([permissions.IsAuthenticated])
def test_stats_api(request):
    """Aggregated usage stats for charts with filters and granularities.

    Query params:
      - outlet_id (optional)
      - machine_id (optional)
      - device_id (optional)
      - granularity: minute|hour|day (default day)
      - start, end: ISO date/time; fallback to 'days'
      - days: int (default 7)
    """
    outlet_id = request.query_params.get('outlet_id')
    machine_id = request.query_params.get('machine_id')
    device_id = request.query_params.get('device_id')
    # Support day and month granularities (default day)
    granularity = (request.query_params.get('granularity') or 'day').lower()
    cumulative = (request.query_params.get('cumulative') or 'false').lower() == 'true'
    ma_window = int(request.query_params.get('ma', 0))  # moving average window in buckets; 0=off
    days = int(request.query_params.get('days', 7))
    start_param = request.query_params.get('start')
    end_param = request.query_params.get('end')

    # Parse start/end in local timezone (Asia/Kuala_Lumpur) and snap to day bounds
    def _parse_local(dt_str):
        from django.utils.dateparse import parse_datetime
        dt = parse_datetime(dt_str)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt

    end_dt = timezone.now()
    if end_param:
        parsed_end = _parse_local(end_param)
        if parsed_end:
            end_dt = parsed_end
    start_dt = end_dt - timedelta(days=days-1)
    if start_param:
        parsed_start = _parse_local(start_param)
        if parsed_start:
            start_dt = parsed_start

    # Snap to local day boundaries for day granularity
    start_dt = start_dt.astimezone(timezone.get_current_timezone()).replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = end_dt.astimezone(timezone.get_current_timezone()).replace(hour=23, minute=59, second=59, microsecond=999000)

    # Determine device set based on filters
    device_ids = None
    if device_id:
        device_ids = [device_id]
    elif machine_id:
        device_ids = list(MachineDevice.objects.filter(machine_id=machine_id).values_list('device_id', flat=True).distinct())
    elif outlet_id:
        machine_ids = list(Machine.objects.filter(outlet_id=outlet_id).values_list('id', flat=True))
        device_ids = list(MachineDevice.objects.filter(machine_id__in=machine_ids).values_list('device_id', flat=True).distinct())

    # Build base queryset of events (exclude heartbeat/status)
    ev_qs = TelemetryEvent.objects.exclude(event_type='status').filter(
        occurred_at__gte=start_dt,
        occurred_at__lte=end_dt,
    )
    if device_ids is not None:
        ev_qs = ev_qs.filter(device_id__in=device_ids)

    # Choose truncation function
    if granularity == 'minute':
        trunc = TruncMinute('occurred_at')
        step = timedelta(minutes=1)
        label_fmt = '%Y-%m-%d %H:%M'
    elif granularity == 'hour':
        trunc = TruncHour('occurred_at')
        step = timedelta(hours=1)
        label_fmt = '%Y-%m-%d %H:00'
    elif granularity == 'month':
        trunc = TruncMonth('occurred_at')
        step = None  # handled below
        label_fmt = '%Y-%m'
    else:
        trunc = TruncDate('occurred_at')
        step = timedelta(days=1)
        label_fmt = '%Y-%m-%d'

    grouped = ev_qs.annotate(bucket=trunc).values('bucket').annotate(
        total=Count('id'),
        basic=Count('id', filter=Q(event_type='BASIC')),
        standard=Count('id', filter=Q(event_type='STANDARD')),
        premium=Count('id', filter=Q(event_type='PREMIUM')),
    ).order_by('bucket')

    # Build labels axis
    labels = []
    end_inclusive = end_dt
    if granularity == 'month':
        # Snap to first day of month
        cur = start_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        def add_month(d):
            y, m = d.year, d.month
            if m == 12:
                return d.replace(year=y+1, month=1)
            return d.replace(month=m+1)
        while cur <= end_inclusive:
            labels.append(cur.strftime(label_fmt))
            cur = add_month(cur)
    else:
        cur = start_dt
        while cur <= end_inclusive:
            labels.append(cur.strftime(label_fmt))
            cur += step

    # Map results
    result_map = {g['bucket'].strftime(label_fmt): g for g in grouped}
    series = {
        'basic': [],
        'standard': [],
        'premium': [],
        'total': [],
    }
    for label in labels:
        row = result_map.get(label)
        series['basic'].append((row or {}).get('basic', 0))
        series['standard'].append((row or {}).get('standard', 0))
        series['premium'].append((row or {}).get('premium', 0))
        series['total'].append((row or {}).get('total', 0))

    def _cumulative(arr):
        s = 0
        out = []
        for v in arr:
            s += int(v or 0)
            out.append(s)
        return out
    def _moving_average(arr, w):
        if w <= 1:
            return arr
        out = []
        from collections import deque
        q = deque()
        s = 0
        for v in arr:
            q.append(int(v or 0))
            s += int(v or 0)
            if len(q) > w:
                s -= q.popleft()
            out.append(round(s / len(q), 2))
        return out

    # Apply cumulative or moving average if requested
    if cumulative:
        for k in list(series.keys()):
            series[k] = _cumulative(series[k])
    if ma_window and ma_window > 1:
        for k in list(series.keys()):
            series[k] = _moving_average(series[k], ma_window)

    # Optional previous period comparison
    compare = (request.query_params.get('compare') or 'false').lower() == 'true'
    prev_series = None
    if compare:
        period_delta = end_dt - start_dt
        prev_end = start_dt - timedelta(seconds=1)
        prev_start = prev_end - period_delta

        prev_qs = TelemetryEvent.objects.exclude(event_type='status').filter(
            occurred_at__gte=prev_start,
            occurred_at__lte=prev_end,
        )
        if device_ids is not None:
            prev_qs = prev_qs.filter(device_id__in=device_ids)

        grouped_prev = prev_qs.annotate(bucket=trunc).values('bucket').annotate(
            total=Count('id'),
            basic=Count('id', filter=Q(event_type='BASIC')),
            standard=Count('id', filter=Q(event_type='STANDARD')),
            premium=Count('id', filter=Q(event_type='PREMIUM')),
        ).order_by('bucket')

        # Build prev labels axis to match length
        prev_labels = []
        cur_p = prev_start
        while len(prev_labels) < len(labels):
            prev_labels.append(cur_p.strftime(label_fmt))
            cur_p += step
        prev_map = {g['bucket'].strftime(label_fmt): g for g in grouped_prev}
        prev_series = {
            'basic': [],
            'standard': [],
            'premium': [],
            'total': [],
        }
        for lab in prev_labels:
            row = prev_map.get(lab)
            prev_series['basic'].append((row or {}).get('basic', 0))
            prev_series['standard'].append((row or {}).get('standard', 0))
            prev_series['premium'].append((row or {}).get('premium', 0))
            prev_series['total'].append((row or {}).get('total', 0))

    # KPIs
    import statistics
    kpi = {
        'total': sum(series['total']) if series['total'] else 0,
        'avg': round(statistics.mean(series['total']), 2) if series['total'] else 0,
        'min': min(series['total']) if series['total'] else 0,
        'max': max(series['total']) if series['total'] else 0,
        'prev_total': sum(prev_series['total']) if prev_series else None,
        'delta_pct': (round(((sum(series['total']) - sum(prev_series['total'])) / max(1, sum(prev_series['total'])))*100, 2) if prev_series and sum(prev_series['total']) else None)
    }

    return Response({'labels': labels, 'series': series, 'prev_series': prev_series, 'kpi': kpi})


@api_view(["GET"]) 
@permission_classes([permissions.IsAuthenticated])
def test_stats_export_csv(request):
    """Export the current filtered stats as CSV (labels + series)."""
    # Reuse the logic by calling test_stats_api with the underlying HttpRequest
    response = test_stats_api(request._request)
    data = response.data
    import csv
    from django.http import HttpResponse
    http = HttpResponse(content_type='text/csv')
    http['Content-Disposition'] = 'attachment; filename="stats_export.csv"'
    writer = csv.writer(http)
    writer.writerow(['label','basic','standard','premium','total'])
    for i, lbl in enumerate(data.get('labels', [])):
        writer.writerow([
            lbl,
            data['series']['basic'][i],
            data['series']['standard'][i],
            data['series']['premium'][i],
            data['series']['total'][i],
        ])
    return http


@api_view(["GET"]) 
@permission_classes([permissions.IsAuthenticated])
def test_stats_options(request):
    """Return lists for filters: outlets, machines (by outlet), devices (by machine)."""
    outlet_id = request.query_params.get('outlet_id')
    machine_id = request.query_params.get('machine_id')

    data = {}
    data['outlets'] = list(Outlet.objects.all().order_by('name').values('id', 'name'))
    if outlet_id:
        data['machines'] = list(Machine.objects.filter(outlet_id=outlet_id).order_by('name').values('id', 'name'))
    if machine_id:
        data['devices'] = list(MachineDevice.objects.filter(machine_id=machine_id).order_by('-is_active', '-assigned_date').values('device_id', 'is_active'))
    return Response(data)


@login_required(login_url='/accounts/login/')
@require_GET
def test_stats_page(request):
    return render(request, 'testing/stats.html', {})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def devices_data_api(request):
    """API endpoint for real-time devices data"""
    devices = Device.objects.all().order_by('-last_seen', 'device_id')
    # Build a lightweight context for template consumption
    context_devices = []
    # Map device_id -> DeviceStatus for quick lookup
    status_map = {ds.device_id: ds for ds in DeviceStatus.objects.all()}
    for d in devices:
        ds = status_map.get(d.device_id)
        context_devices.append({
            'device_id': d.device_id,
            'mac': d.mac,
            'assigned': d.assigned,
            'firmware': d.firmware,
            'last_seen': d.last_seen or (ds.last_seen if ds else None),
            'online': bool(ds and ds.last_seen and ds.last_seen >= timezone.now() - timedelta(minutes=5)),
            'counts': {
                'basic': getattr(ds, 'current_count_basic', None) if ds else None,
                'standard': getattr(ds, 'current_count_standard', None) if ds else None,
                'premium': getattr(ds, 'current_count_premium', None) if ds else None,
            }
        })
    return Response({'devices': context_devices})


@login_required(login_url='/accounts/login/')
def outlets_page(request):
    """List outlets and provide a simple add form."""
    from .models import Outlet
    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        address = (request.POST.get('address') or '').strip()
        # Support either 'contact_person' (new) or legacy 'contact' field name from template
        contact_person = (request.POST.get('contact_person') or request.POST.get('contact') or '').strip()
        if name:
            Outlet.objects.create(
                name=name,
                address=address or '',
                contact_person=contact_person or '',
                # Owner-maintained metrics left empty on creation
            )
            return redirect('outlets')
    outlets = Outlet.objects.all().order_by('name')
    return render(request, 'telemetry/outlets.html', { 'outlets': outlets })


@login_required(login_url='/accounts/login/')
def machines_page(request):
    """List machines, add machine, and bind/unbind device to machine."""
    from .models import Machine, Outlet, MachineDevice
    # Add machine
    if request.method == 'POST' and request.POST.get('form') == 'add_machine':
        outlet_id = request.POST.get('outlet_id')
        name = (request.POST.get('name') or '').strip()
        if name:
            outlet = None
            if outlet_id:
                try:
                    outlet = Outlet.objects.get(id=outlet_id)
                except Outlet.DoesNotExist:
                    outlet = None
            Machine.objects.create(outlet=outlet, name=name)
            return redirect('machines')
    # Data for lists/forms
    machines = Machine.objects.select_related('outlet').all().order_by('name')
    outlets = Outlet.objects.all().order_by('name')
    # Show current bindings
    active_device_ids = set(MachineDevice.objects.filter(is_active=True).values_list('device_id', flat=True))
    bindings = {md.device_id: md for md in MachineDevice.objects.filter(is_active=True)}
    # Map machine -> active device_id
    active_map = {}
    for md in MachineDevice.objects.filter(is_active=True):
        active_map[md.machine_id] = md.device_id
    # Devices available to bind (not currently bound to any machine)
    available_devices = Device.objects.exclude(device_id__in=active_device_ids).order_by('device_id')
    return render(request, 'telemetry/machines.html', {
        'machines': machines,
        'outlets': outlets,
        'bindings': bindings,
        'available_devices': available_devices,
        'active_map': active_map,
    })


@login_required(login_url='/accounts/login/')
def device_bind(request):
    from .models import Machine, MachineDevice
    if request.method == 'POST':
        device_id = (request.POST.get('device_id') or '').strip()
        machine_id = request.POST.get('machine_id')
        if device_id and machine_id:
            try:
                machine = Machine.objects.get(id=machine_id)
                # Deactivate any existing active binding for this machine
                from django.utils import timezone as _tz
                MachineDevice.objects.filter(machine=machine, is_active=True).update(is_active=False, deactivated_date=_tz.now())
                # Deactivate existing active binding for this device on any machine
                MachineDevice.objects.filter(device_id=device_id, is_active=True).update(is_active=False, deactivated_date=_tz.now())
                # Create new active binding
                MachineDevice.objects.create(machine=machine, device_id=device_id, is_active=True)
            except Machine.DoesNotExist:
                pass
    return redirect('machines')


@login_required(login_url='/accounts/login/')
def device_unbind(request):
    from .models import MachineDevice
    if request.method == 'POST':
        device_id = (request.POST.get('device_id') or '').strip()
        if device_id:
            MachineDevice.objects.filter(device_id=device_id, is_active=True).update(is_active=False)
    return redirect('machines')


@login_required(login_url='/accounts/login/')
def machine_delete(request):
    """Delete a machine by ID and cascade related bindings."""
    from .models import Machine
    if request.method == 'POST':
        machine_id = request.POST.get('machine_id')
        if machine_id:
            try:
                machine = Machine.objects.get(id=machine_id)
                machine.delete()
            except Machine.DoesNotExist:
                pass
    return redirect('machines')
