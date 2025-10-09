from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from .models import Outlet, Machine, Device, DeviceStatus, TelemetryEvent, Command
from django.contrib.auth import authenticate, login
from django.contrib.auth import get_user_model
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from telemetry.api.ingest import _get_device_status


@require_http_methods(["GET"])
@ensure_csrf_cookie
def login_page(request):
    return render(request, "auth/login.html")


@require_http_methods(["POST"])
@csrf_exempt
def login_submit(request):
    username = request.POST.get("username", "").strip()
    password = request.POST.get("password", "").strip()
    user = authenticate(request, username=username, password=password)
    if user is None:
        return render(request, "telemetry/_login_form.html", {"error": "Invalid credentials"}, status=400)
    login(request, user)
    # In HTMX, redirect using HX-Redirect so the whole page navigates to /dashboard
    resp = HttpResponse(status=204)
    resp["HX-Redirect"] = "/dashboard/"
    return resp


@require_http_methods(["GET"])
@ensure_csrf_cookie
def register_page(request):
    return render(request, "auth/register.html")


@require_http_methods(["POST"])
@csrf_exempt
def register_submit(request):
    User = get_user_model()
    username = request.POST.get("username", "").strip()
    password = request.POST.get("password", "").strip()
    role = request.POST.get("role", "dealer").strip()
    if not username or not password:
        return render(request, "telemetry/_register_form.html", {"error": "Username and password required"}, status=400)
    if User.objects.filter(username=username).exists():
        return render(request, "telemetry/_register_form.html", {"error": "Username already exists"}, status=400)
    user = User.objects.create_user(username=username, password=password, role=role)
    # After successful register, send them to login page
    resp = HttpResponse(status=204)
    resp["HX-Redirect"] = "/login/"
    return resp



@login_required
def dashboard(request):
    # Get statistics for dashboard
    total_outlets = Outlet.objects.count()
    total_machines = Machine.objects.count()
    total_devices = Device.objects.count()
    online_devices = Device.objects.filter(last_seen__gte=timezone.now() - timedelta(minutes=5)).count()
    
    context = {
        'user': request.user,
        'total_outlets': total_outlets,
        'total_machines': total_machines,
        'total_devices': total_devices,
        'online_devices': online_devices,
    }
    return render(request, "dashboard/index.html", context)


@login_required
def outlets_page(request):
    # List outlets and show create form
    outlets = Outlet.objects.order_by('outlet_name')
    # Prefetch machines and their bound devices for aggregation
    outlets = outlets.prefetch_related(
        'machines__device'
    )
    # Build a lookup of device_id -> DeviceStatus for fast access
    device_status_map = {ds.device_id: ds for ds in DeviceStatus.objects.all()}
    
    # Calculate statistics
    total_outlets = outlets.count()
    outlets_with_machines = outlets.filter(machines__isnull=False).distinct().count()
    total_machines_in_outlets = sum(outlet.machines.count() for outlet in outlets)
    active_outlets = outlets.count()  # Assuming all outlets are active for now
    
    # Per-outlet treatment aggregates (Basic, Standard, Premium, Total)
    for outlet in outlets:
        basic_sum = 0
        standard_sum = 0
        premium_sum = 0
        # Sum current counters from bound devices under this outlet's machines
        for m in outlet.machines.all():
            if m.device:
                ds = device_status_map.get(m.device.device_id)
                if ds:
                    basic_sum += getattr(ds, 'current_count_basic', 0) or 0
                    standard_sum += getattr(ds, 'current_count_standard', 0) or 0
                    premium_sum += getattr(ds, 'current_count_premium', 0) or 0
        # Attach to outlet for easy template access
        outlet.treat_basic = basic_sum
        outlet.treat_standard = standard_sum
        outlet.treat_premium = premium_sum
        outlet.treat_total = basic_sum + standard_sum + premium_sum

    # Aggregated totals across all outlets (sum of current device counters)
    agg_basic = sum(getattr(o, 'treat_basic', 0) or 0 for o in outlets)
    agg_standard = sum(getattr(o, 'treat_standard', 0) or 0 for o in outlets)
    agg_premium = sum(getattr(o, 'treat_premium', 0) or 0 for o in outlets)
    agg_total = agg_basic + agg_standard + agg_premium
    
    # Convert outlets to JSON for JavaScript
    import json
    outlets_json = []
    for outlet in outlets:
        outlets_json.append({
            'id': outlet.outlet_id,
            'outlet_name': outlet.outlet_name,
            'region': outlet.region or '-',
            'machine_count': outlet.machines.count(),
            'treat_basic': getattr(outlet, 'treat_basic', 0) or 0,
            'treat_standard': getattr(outlet, 'treat_standard', 0) or 0,
            'treat_premium': getattr(outlet, 'treat_premium', 0) or 0,
            'treat_total': getattr(outlet, 'treat_total', 0) or 0,
        })
    
    # Convert to JSON string
    outlets_json = json.dumps(outlets_json)
    
    context = {
        'outlets': outlets,
        'outlets_json': outlets_json,
        'total_outlets': total_outlets,
        'outlets_with_machines': outlets_with_machines,
        'total_machines_in_outlets': total_machines_in_outlets,
        'active_outlets': active_outlets,
        'agg_basic': agg_basic,
        'agg_standard': agg_standard,
        'agg_premium': agg_premium,
        'agg_total': agg_total,
    }
    return render(request, "outlets/index.html", context)


@login_required
def outlets_create(request):
    if request.method == 'GET':
        return render(request, "outlets/create.html")
    
    name = (request.POST.get('outlet_name') or '').strip()
    pic_sm = (request.POST.get('pic_sm') or '').strip()
    sm_number = (request.POST.get('sm_number') or '').strip()
    if not name:
        return render(request, "outlets/create.html", {"error": "Outlet name is required"}, status=400)
    Outlet.objects.create(outlet_name=name, pic_sm=pic_sm or None, sm_number=sm_number or None)
    return redirect('outlets_page')


@login_required
def machines_page(request):
    machines = Machine.objects.select_related('outlet', 'device').order_by('machine_id')
    
    # Get device statuses for machines with devices
    device_statuses = {}
    for status in DeviceStatus.objects.all():
        device_statuses[status.device_id] = status
    
    # Attach device status to each machine's device
    for machine in machines:
        if machine.device:
            machine.device.device_status = device_statuses.get(machine.device.device_id)
    
    # Calculate statistics
    total_machines = machines.count()
    active_machines = machines.filter(is_active=True).count()
    assigned_machines = machines.filter(outlet__isnull=False).count()
    machines_with_devices = machines.filter(device__isnull=False).count()
    
    # Convert machines to JSON for JavaScript
    import json
    machines_json = []
    for machine in machines:
        machine_data = {
            'id': machine.machine_id,  # expose primary key as 'id' for JS
            'name': machine.name,
            'outlet': {
                'outlet_name': machine.outlet.outlet_name if machine.outlet else None
            },
            'installed_at': machine.installed_at.isoformat() if machine.installed_at else None,
            'is_active': machine.is_active,
        }
        
        # Add device information if machine has a device
        if machine.device:
            ds = device_statuses.get(machine.device.device_id)
            machine_data['device'] = {
                'device_id': machine.device.device_id,
                'mac': machine.device.mac,
                'status': _get_device_status(ds) if ds else 'offline',
                'last_seen': ds.last_seen.isoformat() if ds and ds.last_seen else None,
            }
        
        machines_json.append(machine_data)
    
    # Convert to JSON string to ensure proper boolean conversion
    machines_json = json.dumps(machines_json)
    
    # Get outlets for assignment modal
    outlets = Outlet.objects.all().order_by('outlet_name')
    
    context = {
        'machines': machines,
        'machines_json': machines_json,
        'outlets': outlets,
        'total_machines': total_machines,
        'active_machines': active_machines,
        'assigned_machines': assigned_machines,
        'machines_with_devices': machines_with_devices,
    }
    return render(request, "machines/index.html", context)


@login_required
def machines_create(request):
    if request.method == 'GET':
        return render(request, "machines/create.html")
    
    name = (request.POST.get('name') or '').strip()
    if not name:
        return render(request, "machines/create.html", {"error": "Name is required"}, status=400)
    # Use machine_code for label; machine_id (PK) auto-generates
    Machine.objects.create(machine_code=name, outlet=None)
    return redirect('machines_page')


@login_required
def outlet_manage(request, outlet_id):
    try:
        outlet = Outlet.objects.get(pk=outlet_id)
    except Outlet.DoesNotExist:
        return redirect('outlets_page')
    machines = Machine.objects.filter(outlet=outlet).select_related('device').order_by('machine_id')
    unassigned = Machine.objects.filter(outlet__isnull=True).order_by('machine_id')
    return render(request, 'outlets/manage.html', {"outlet": outlet, "machines": machines, "unassigned": unassigned})


@login_required
@require_http_methods(["POST"])
def outlet_assign_machine(request, outlet_id):
    try:
        outlet = Outlet.objects.get(pk=outlet_id)
    except Outlet.DoesNotExist:
        return redirect('outlets_page')
    machine_id = request.POST.get('machine_id')
    if machine_id:
        try:
            m = Machine.objects.get(machine_id=machine_id)
            m.outlet = outlet
            m.save()
        except Machine.DoesNotExist:
            pass
    return redirect('outlet_manage', outlet_id=outlet.outlet_id)


@login_required
def devices_page(request):
    """Devices management page showing ESP32 devices and their status"""
    devices = Device.objects.select_related('machine', 'machine__outlet').order_by('-last_seen', 'device_id')
    
    # Get device statuses and attach to devices
    device_statuses = {}
    for status in DeviceStatus.objects.all():
        device_statuses[status.device_id] = status
    
    # Attach device status to each device
    for device in devices:
        device.device_status = device_statuses.get(device.device_id)
    
    # Get recent events (last 24 hours)
    recent_events = TelemetryEvent.objects.filter(
        occurred_at__gte=timezone.now() - timedelta(days=1)
    ).order_by('-occurred_at')[:50]
    
    # Machine assignments are now handled via direct relationship (device.machine)
    
    # Statistics
    total_devices = devices.count()
    online_devices = devices.filter(last_seen__gte=timezone.now() - timedelta(minutes=5)).count()
    assigned_devices = devices.filter(assigned=True).count()
    unassigned_devices = total_devices - assigned_devices
    
    # Get all machines for assignment dropdown
    machines = Machine.objects.select_related('outlet').order_by('machine_code')
    
    context = {
        'devices': devices,
        'device_statuses': device_statuses,
        'recent_events': recent_events,
        'machines': machines,
        'total_devices': total_devices,
        'online_devices': online_devices,
        'assigned_devices': assigned_devices,
        'unassigned_devices': unassigned_devices,
    }
    
    return render(request, "devices/index.html", context)


@login_required
@require_http_methods(["POST"])
def device_assign(request, device_id):
    """Assign a device to a machine"""
    try:
        device = Device.objects.get(device_id=device_id)
    except Device.DoesNotExist:
        return redirect('devices_page')
    
    machine_id = request.POST.get('machine_id')
    if machine_id:
        try:
            machine = Machine.objects.get(pk=machine_id)
            
            # Unassign device from any existing machine
            try:
                if device.machine:
                    device.machine.device = None
                    device.machine.save()
            except:
                # Device has no machine assigned
                pass
            
            # Remove any existing device from the target machine
            if machine.device is not None:
                existing_device = machine.device
                existing_device.assigned = False
                existing_device.save()
            
            # Create the assignment (set the OneToOneField on the machine)
            machine.device = device
            machine.save()
            
            # Update device assignment status
            device.assigned = True
            device.save()
            
        except Machine.DoesNotExist:
            pass
    
    return redirect('devices_page')


@login_required
@require_http_methods(["POST"])
def device_unassign(request, device_id):
    """Unassign a device from its machine"""
    try:
        device = Device.objects.get(device_id=device_id)
        
        # Safely check if device has a machine assigned
        try:
            if device.machine is not None:
                # Remove device from machine (this is the correct way)
                machine = device.machine
                machine.device = None
                machine.save()
        except:
            # Device has no machine assigned - this is fine, just clear the assignment flag
            pass
        
        # Update device assignment status (always clear the assigned flag)
        device.assigned = False
        device.save()
        
    except Device.DoesNotExist:
        pass
    
    return redirect('devices_page')


@login_required
def device_detail(request, device_id):
    """Detailed view of a specific device"""
    try:
        device = Device.objects.get(device_id=device_id)
    except Device.DoesNotExist:
        return redirect('devices_page')
    
    # Get device status
    try:
        device_status = DeviceStatus.objects.get(device_id=device_id)
    except DeviceStatus.DoesNotExist:
        device_status = None
    
    # Get recent events
    recent_events = TelemetryEvent.objects.filter(
        device_id=device_id
    ).order_by('-occurred_at')[:100]
    
    # Get machine assignment (direct relationship)
    machine_assignment = device.machine if device.machine else None
    
    # Get usage statistics (last 30 days)
    from datetime import date
    thirty_days_ago = date.today() - timedelta(days=30)
    usage_stats = TelemetryEvent.objects.filter(
        device_id=device_id,
        occurred_at__gte=thirty_days_ago
    ).values('event_type').annotate(count=Count('id')).order_by('-count')
    
    context = {
        'device': device,
        'device_status': device_status,
        'recent_events': recent_events,
        'machine_assignment': machine_assignment,
        'usage_stats': usage_stats,
    }
    
    return render(request, "devices/detail.html", context)


@login_required
def device_commands(request, device_id):
    """Command management page for a specific device"""
    try:
        device = Device.objects.get(device_id=device_id)
    except Device.DoesNotExist:
        return redirect('devices_page')
    
    # Get command statistics
    commands = Command.objects.filter(device=device)
    
    stats = {
        'total': commands.count(),
        'pending': commands.filter(status='pending').count(),
        'sent': commands.filter(status='sent').count(),
        'executed': commands.filter(status='executed').count(),
        'failed': commands.filter(status='failed').count(),
        'timeout': commands.filter(status='timeout').count(),
    }
    
    # Get recent commands
    recent_commands = commands.order_by('-created_at')[:20]
    
    context = {
        'device': device,
        'stats': stats,
        'recent_commands': recent_commands,
        'command_types': Command.COMMAND_TYPES,
        'priority_choices': Command.PRIORITY_CHOICES,
    }
    
    return render(request, "devices/commands.html", context)


@login_required
@require_http_methods(["POST"])
def create_command(request, device_id):
    """Create a new command for a device"""
    try:
        device = Device.objects.get(device_id=device_id)
    except Device.DoesNotExist:
        return redirect('devices_page')
    
    command_type = request.POST.get('command_type')
    priority = request.POST.get('priority', 'normal')
    description = request.POST.get('description', '')
    expires_in_hours = int(request.POST.get('expires_in_hours', 24))
    
    if command_type:
        # Generate unique command ID
        import uuid
        command_id = f"{device_id}-{command_type}-{uuid.uuid4().hex[:8]}"
        
        # Calculate expiration time
        from django.utils import timezone
        from datetime import timedelta
        expires_at = timezone.now() + timedelta(hours=expires_in_hours)
        
        # Create command
        Command.objects.create(
            command_id=command_id,
            device=device,
            command_type=command_type,
            priority=priority,
            description=description,
            expires_at=expires_at,
            created_by=request.user
        )
    
    return redirect('device_commands', device_id=device_id)


@login_required
@require_http_methods(["POST"])
def machine_assign(request, machine_id):
    """Assign a machine to an outlet"""
    machine = get_object_or_404(Machine, machine_id=machine_id)
    outlet_id = request.POST.get('outlet_id')
    
    if not outlet_id:
        return redirect('machines_page')
    
    try:
        outlet = Outlet.objects.get(outlet_id=outlet_id)
        machine.outlet = outlet
        machine.save()
    except Outlet.DoesNotExist:
        pass
    
    return redirect('machines_page')


@login_required
@require_http_methods(["POST"])
def machine_unassign(request, machine_id):
    """Unassign a machine from its outlet"""
    machine = get_object_or_404(Machine, machine_id=machine_id)
    machine.outlet = None
    machine.save()
    return redirect('machines_page')


@login_required
def machine_treatment_logs(request, machine_id):
    """Show detailed treatment logs for a specific machine"""
    try:
        machine = Machine.objects.get(machine_id=machine_id)
    except Machine.DoesNotExist:
        return redirect('machines_page')
    
    # Get the device associated with this machine
    device = machine.device
    if not device:
        # Machine has no device assigned
        context = {
            'machine': machine,
            'device': None,
            'treatment_logs': [],
            'stats': {
                'total_treatments': 0,
                'basic_treatments': 0,
                'standard_treatments': 0,
                'premium_treatments': 0,
            }
        }
        return render(request, "machines/treatment_logs.html", context)
    
    # Get treatment events for this device
    treatment_events = TelemetryEvent.objects.filter(
        device_id=device.device_id,
        event='treatment'
    ).order_by('-occurred_at')
    
    # Get reset commands for this device
    reset_commands = Command.objects.filter(
        device=device,
        command_type='RESET_COUNTERS'
    ).order_by('-created_at')
    
    # Get device status for current counters
    try:
        device_status = DeviceStatus.objects.get(device_id=device.device_id)
    except DeviceStatus.DoesNotExist:
        device_status = None
    
    # Calculate statistics - Historical counts from TelemetryEvent
    total_treatments = treatment_events.count()
    basic_treatments = treatment_events.filter(treatment='BASIC').count()
    standard_treatments = treatment_events.filter(treatment='STANDARD').count()
    premium_treatments = treatment_events.filter(treatment='PREMIUM').count()
    
    # Get current counters from DeviceStatus
    current_basic = device_status.current_count_basic if device_status else 0
    current_standard = device_status.current_count_standard if device_status else 0
    current_premium = device_status.current_count_premium if device_status else 0
    current_total = current_basic + current_standard + current_premium
    
    # Convert QuerySets to JSON-serializable format
    import json
    treatment_logs_json = []
    for log in treatment_events:
        treatment_logs_json.append({
            'id': log.id,
            'event_id': log.event_id,
            'treatment': log.treatment,
            'counter': log.counter,
            'device_timestamp': log.device_timestamp,
            'occurred_at': log.occurred_at.isoformat(),
            'wifi_status': log.wifi_status,
            'payload': log.payload,
            'counters': {
                'basic': (log.count_basic or 0),
                'standard': (log.count_standard or 0),
                'premium': (log.count_premium or 0),
            },
        })
    
    reset_commands_json = []
    for cmd in reset_commands:
        # Try to extract counters from response_data.current_counters if present
        response_data = cmd.response_data or {}
        current_counters = {}
        if isinstance(response_data, dict):
            current_counters = response_data.get('current_counters') or {}
        reset_commands_json.append({
            'id': cmd.id,
            'command_id': cmd.command_id,
            'status': cmd.status,
            'created_at': cmd.created_at.isoformat(),
            'executed_at': cmd.executed_at.isoformat() if cmd.executed_at else None,
            'response_data': response_data,
            'counters': {
                'basic': int(current_counters.get('basic', 0) or 0),
                'standard': int(current_counters.get('standard', 0) or 0),
                'premium': int(current_counters.get('premium', 0) or 0),
            },
        })
    
    context = {
        'machine': machine,
        'device': device,
        'device_status': device_status,
        'treatment_logs': treatment_events,
        'treatment_logs_json': json.dumps(treatment_logs_json),
        'reset_commands': reset_commands,
        'reset_commands_json': json.dumps(reset_commands_json),
        'stats': {
            'total_treatments': total_treatments,
            'basic_treatments': basic_treatments,
            'standard_treatments': standard_treatments,
            'premium_treatments': premium_treatments,
            'total_resets': reset_commands.count(),
            'current_total': current_total,
            'current_basic': current_basic,
            'current_standard': current_standard,
            'current_premium': current_premium,
        }
    }
    return render(request, "machines/treatment_logs.html", context)


@login_required
@require_http_methods(["POST"])
def machine_delete(request, machine_id):
    """Delete a machine and safely unbind any attached device."""
    machine = get_object_or_404(Machine, machine_id=machine_id)
    # Unbind device if present
    if machine.device:
        device = machine.device
        device.machine = None
        device.assigned = False
        device.save()
        machine.device = None
    # Remove outlet link implicitly by deleting machine
    machine.delete()
    return redirect('machines_page')


@login_required
def machine_logs_api(request, machine_id):
    """Return JSON of treatment logs and reset commands for a given machine (for auto-refresh)."""
    try:
        machine = Machine.objects.get(machine_id=machine_id)
    except Machine.DoesNotExist:
        from django.http import JsonResponse
        return JsonResponse({'error': 'machine_not_found'}, status=404)

    device = machine.device
    if not device:
        from django.http import JsonResponse
        return JsonResponse({'treatment_logs': [], 'reset_commands': []})

    treatment_events = TelemetryEvent.objects.filter(
        device_id=device.device_id,
        event='treatment'
    ).order_by('-occurred_at')[:500]

    from django.http import JsonResponse
    import json

    # Serialize treatment events
    treatment_logs_json = []
    for log in treatment_events:
        treatment_logs_json.append({
            'id': log.id,
            'event_id': log.event_id,
            'treatment': log.treatment,
            'counter': log.counter,
            'device_timestamp': log.device_timestamp,
            'occurred_at': log.occurred_at.isoformat(),
            'wifi_status': log.wifi_status,
            'payload': log.payload or {},
            'counters': {
                'basic': (log.count_basic or 0),
                'standard': (log.count_standard or 0),
                'premium': (log.count_premium or 0),
            },
        })

    # Serialize reset commands
    reset_commands = Command.objects.filter(
        device=device,
        command_type='RESET_COUNTERS'
    ).order_by('-created_at')[:200]

    reset_commands_json = []
    for cmd in reset_commands:
        response_data = cmd.response_data or {}
        current_counters = response_data.get('current_counters') if isinstance(response_data, dict) else {}
        reset_commands_json.append({
            'id': cmd.id,
            'command_id': cmd.command_id,
            'status': cmd.status,
            'created_at': cmd.created_at.isoformat(),
            'executed_at': cmd.executed_at.isoformat() if cmd.executed_at else None,
            'response_data': response_data,
            'counters': {
                'basic': int((current_counters or {}).get('basic', 0) or 0),
                'standard': int((current_counters or {}).get('standard', 0) or 0),
                'premium': int((current_counters or {}).get('premium', 0) or 0),
            },
        })

    return JsonResponse({
        'treatment_logs': treatment_logs_json,
        'reset_commands': reset_commands_json,
    })
