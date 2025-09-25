# Moved: keep this file as the canonical location.
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.utils import timezone
from datetime import datetime, timedelta
from django.db import transaction
from telemetry.models import TelemetryEvent, DeviceStatus, UsageStatistics, Device, Machine
import secrets
from django.contrib.auth.models import User
from rest_framework.permissions import IsAuthenticated


def _get_device_status(device_status):
    """Determine device status based on last_poll timestamp (ESP32 command polling)"""
    if not device_status:
        return 'offline'
    
    # Prefer last_poll (ESP32 command polling) over last_seen (events)
    poll_time = device_status.last_poll
    if not poll_time:
        # Fallback to last_seen if no poll time available
        poll_time = device_status.last_seen
        if not poll_time:
            return 'offline'
    
    now = timezone.now()
    time_diff = now - poll_time
    
    if time_diff <= timedelta(minutes=16):
        return 'online'
    elif time_diff <= timedelta(hours=1):
        return 'idle'
    else:
        return 'offline'


def _safe_number(value):
    """Safely convert value to int, return None if invalid."""
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (ValueError, TypeError):
        return None


@api_view(["POST"]) 
@permission_classes([permissions.AllowAny])
def iot_ingest(request):
    """Accept ESP32 form-urlencoded payload and update DeviceStatus and events only."""
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

    occurred_at = timezone.now()
    if device_timestamp:
        parsed = _parse_device_timestamp(device_timestamp)
        if parsed:
            occurred_at = parsed

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

    event_type = mode if mode in {"BASIC", "STANDARD", "PREMIUM", "status"} else "status"
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
    try:
        if not value:
            return None
        dt = datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
        return timezone.make_aware(dt)
    except Exception:
        return None


def _parse_timestamp(value):
    try:
        if str(value).isdigit():
            return timezone.datetime.fromtimestamp(int(value), tz=timezone.utc)
        from django.utils.dateparse import parse_datetime
        dt = parse_datetime(str(value))
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _update_daily_statistics(device_id, event_type, occurred_at):
    try:
        date = occurred_at.date()
        stats, created = UsageStatistics.objects.get_or_create(
            device_id=device_id,
            date=date,
            defaults={}
        )
        if event_type == "BASIC":
            stats.basic_count += 1
        elif event_type == "STANDARD":
            stats.standard_count += 1
        elif event_type == "PREMIUM":
            stats.premium_count += 1
        stats.total_count += 1
        stats.save()
    except Exception as e:
        print(f"Error updating daily statistics: {e}")


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def export_data(request):
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
    try:
        with transaction.atomic():
            TelemetryEvent.objects.all().delete()
            UsageStatistics.objects.all().delete()
            DeviceStatus.objects.all().delete()
        return Response({"status": "flushed"})
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"]) 
@permission_classes([permissions.AllowAny])
def flush_all_but_admin(request):
    """Dangerous operation: clear all app data and users except admin (username='admin')."""
    try:
        with transaction.atomic():
            # Delete domain data
            TelemetryEvent.objects.all().delete()
            UsageStatistics.objects.all().delete()
            DeviceStatus.objects.all().delete()
            # MachineDevice model removed - devices are now directly linked to machines
            Machine.objects.all().delete()
            Device.objects.all().delete()

            # Delete all users except username 'admin'
            User.objects.exclude(username='admin').delete()
        return Response({"status": "flushed_except_admin"})
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"]) 
@permission_classes([permissions.AllowAny])
def handshake(request):
    mac = (request.data.get("mac") or "").strip()
    firmware = (request.data.get("firmware") or "").strip()
    if not mac:
        return Response({"detail": "mac required"}, status=status.HTTP_400_BAD_REQUEST)
    device = Device.objects.filter(mac=mac).first()
    if not device:
        device = Device.objects.create(
            mac=mac, device_id=mac, token=secrets.token_urlsafe(24), assigned=False, firmware=firmware
        )
    else:
        # Update device_id to match MAC if it was previously different
        if device.device_id != mac:
            device.device_id = mac
        device.firmware = firmware or device.firmware
        device.last_seen = timezone.now()
        device.save()
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
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    return Device.objects.filter(token=token, assigned=True).first()


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def events(request):
    device = _auth_device(request)
    if not device:
        return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    data = request.data
    event_id = (data.get("event_id") or "").strip()
    event = (data.get("event") or "").strip()
    treatment = (data.get("treatment") or "").strip()
    counter = data.get("counter")
    ts = data.get("ts")
    current_counters = data.get("current_counters", {})
    
    # Debug logging
    print(f"🔍 EVENTS DEBUG: device_id={device.device_id}, event_id={event_id}, treatment={treatment}, counter={counter}")
    print(f"🔍 CURRENT COUNTERS: {current_counters}")
    if not event_id:
        return Response({"detail": "event_id required"}, status=status.HTTP_400_BAD_REQUEST)
    if event != "treatment" or treatment not in {"BASIC", "STANDARD", "PREMIUM"}:
        return Response({"detail": "invalid event/treatment"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        counter = int(counter)
    except Exception:
        return Response({"detail": "counter must be int"}, status=status.HTTP_400_BAD_REQUEST)
    existing = TelemetryEvent.objects.filter(event_id=event_id).first()
    if existing:
        print(f"🔍 DUPLICATE EVENT: event_id={event_id} already exists, skipping")
        return Response({"ack": True, "event_id": event_id})
    occurred_at = _parse_timestamp(ts) or timezone.now()
    TelemetryEvent.objects.create(
        device_id=device.device_id,
        event_id=event_id,
        event=event,
        treatment=treatment,
        counter=counter,
        occurred_at=occurred_at,
        event_type=treatment,
        count_basic=None,
        count_standard=None,
        count_premium=None,
        device_timestamp=ts,
        wifi_status=True,
        payload={},
    )
    # Update device last_seen
    device.last_seen = timezone.now()
    device.save()
    
    ds, _ = DeviceStatus.objects.get_or_create(device_id=device.device_id)
    ds.wifi_connected = True
    ds.device_timestamp = ts
    ds.last_seen = timezone.now()
    
    # Update counters - prioritize current_counters if provided, otherwise use individual counter
    if current_counters:
        # Use the complete current_counters object
        ds.current_count_basic = current_counters.get("basic", ds.current_count_basic)
        ds.current_count_standard = current_counters.get("standard", ds.current_count_standard)
        ds.current_count_premium = current_counters.get("premium", ds.current_count_premium)
        print(f"🔍 UPDATED FROM CURRENT_COUNTERS: Basic={ds.current_count_basic}, Standard={ds.current_count_standard}, Premium={ds.current_count_premium}")
    else:
        # Fallback to individual counter update (legacy behavior)
        if treatment == "BASIC":
            ds.current_count_basic = counter
        elif treatment == "STANDARD":
            ds.current_count_standard = counter
        elif treatment == "PREMIUM":
            ds.current_count_premium = counter
        print(f"🔍 UPDATED FROM INDIVIDUAL COUNTER: {treatment}={counter}")
    
    ds.save()
    _update_daily_statistics(device.device_id, treatment, occurred_at)
    print(f"✅ EVENT CREATED: {treatment} treatment, counter={counter}, new counts: Basic={ds.current_count_basic}, Standard={ds.current_count_standard}, Premium={ds.current_count_premium}")
    return Response({"ack": True, "event_id": event_id})


@api_view(["GET"]) 
@permission_classes([permissions.AllowAny])
def devices_data_api(request):
    devices = Device.objects.all().order_by('-last_seen', 'device_id')
    context_devices = []
    status_map = {ds.device_id: ds for ds in DeviceStatus.objects.all()}
    for d in devices:
        ds = status_map.get(d.device_id)
        # Prefer device-reported accumulated counters (ESP32), fallback to DB totals
        if ds is not None:
            basic_count = getattr(ds, 'current_count_basic', None)
            standard_count = getattr(ds, 'current_count_standard', None)
            premium_count = getattr(ds, 'current_count_premium', None)
        else:
            basic_count = standard_count = premium_count = None
        if basic_count is None:
            basic_count = TelemetryEvent.objects.filter(device_id=d.device_id, event_type='BASIC').count()
        if standard_count is None:
            standard_count = TelemetryEvent.objects.filter(device_id=d.device_id, event_type='STANDARD').count()
        if premium_count is None:
            premium_count = TelemetryEvent.objects.filter(device_id=d.device_id, event_type='PREMIUM').count()

        # Get bound machine using direct relationship (OneToOne can raise RelatedObjectDoesNotExist)
        bound_machine = None
        try:
            m = d.machine  # may raise RelatedObjectDoesNotExist when no relation exists
        except Exception:
            m = None
        if m:
            bound_machine = {
                'id': m.machine_id,
                'name': getattr(m, 'machine_code', ''),
                'outlet_id': m.outlet.outlet_id if m.outlet else None,
                'outlet_name': m.outlet.outlet_name if m.outlet else None,
            }

        context_devices.append({
            'device_id': d.device_id,
            'mac': d.mac,
            # Treat as assigned if a machine relation exists
            'assigned': bool(bound_machine),
            'firmware': d.firmware,
            'last_seen': ds.last_poll if ds and ds.last_poll else (ds.last_seen if ds else d.last_seen),
            # Determine device status based on last_seen
            'status': _get_device_status(ds),
            'bound_machine': bound_machine,
            'counts': {
                'basic': basic_count,
                'standard': standard_count,
                'premium': premium_count,
            }
        })
    return Response({'devices': context_devices})


@api_view(["GET"]) 
@permission_classes([permissions.AllowAny])
def devices_online_api(request):
    """Return only online devices"""
    devices = Device.objects.all().order_by('-last_seen', 'device_id')
    context_devices = []
    status_map = {ds.device_id: ds for ds in DeviceStatus.objects.all()}
    for d in devices:
        ds = status_map.get(d.device_id)
        # Only include devices that are online (within 5 minutes)
        device_status = _get_device_status(ds)
        if device_status == 'online':
            context_devices.append({
                'device_id': d.device_id,
                'mac': d.mac,
                'assigned': d.assigned,
                'firmware': d.firmware,
                'last_seen': ds.last_poll if ds and ds.last_poll else (ds.last_seen if ds else d.last_seen),
                'online': True,
                'counts': {
                    'basic': getattr(ds, 'current_count_basic', None) if ds else None,
                    'standard': getattr(ds, 'current_count_standard', None) if ds else None,
                    'premium': getattr(ds, 'current_count_premium', None) if ds else None,
                }
            })
    return Response({'devices': context_devices})


@api_view(["GET"]) 
@permission_classes([permissions.AllowAny])
def machines_unregistered_api(request):
    """Return machines that have no active device assigned"""
    # Get all machines that don't have any device assigned
    unregistered_machines = Machine.objects.filter(device__isnull=True).order_by('outlet__name', 'name')
    
    machines_data = []
    for machine in unregistered_machines:
        machines_data.append({
            'id': machine.id,
            'name': machine.name or f'Machine-{machine.id}',
            'outlet_name': machine.outlet.name if machine.outlet else 'No outlet',
            'outlet_id': machine.outlet.id if machine.outlet else None,
            'machine_type': machine.machine_type,
            'is_active': machine.is_active,
            'installed_date': machine.installed_date,
            'last_maintenance': machine.last_maintenance,
            'created_at': machine.created_at,
            'updated_at': machine.updated_at,
        })
    
    return Response({'machines': machines_data})


@api_view(["POST"]) 
@permission_classes([IsAuthenticated])
def bind_device_to_machine(request):
    """Bind a Device to a Machine using direct relationship.
    Payload: { "device_id": "...", "machine_id": 123 }
    """
    try:
        device_id = (request.data.get("device_id") or "").strip()
        machine_id = request.data.get("machine_id")
        if not device_id or not machine_id:
            return Response({"detail": "device_id and machine_id required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            machine = Machine.objects.get(id=machine_id)
        except Machine.DoesNotExist:
            return Response({"detail": "machine not found"}, status=status.HTTP_404_NOT_FOUND)

        device = Device.objects.filter(device_id=device_id).first()
        if not device:
            return Response({"detail": "device not found"}, status=status.HTTP_404_NOT_FOUND)

        # Unassign device from any existing machine
        if device.machine:
            device.machine.device = None
            device.machine.save()

        # Unassign any existing device from the target machine
        if machine.device:
            machine.device.machine = None
            machine.device.save()

        # Create the binding
        machine.device = device
        machine.save()

        # Mark device as assigned
        device.assigned = True
        device.save()

        if not machine.outlet_id:
            return Response({"status": "bound", "warning": "Machine has no outlet; assign outlet to include in outlet totals"})

        return Response({
            "status": "bound",
            "machine_id": machine.id,
            "device_id": device.device_id,
        })
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


