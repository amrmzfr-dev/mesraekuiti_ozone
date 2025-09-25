"""
Command API endpoints for ESP32 device communication
"""
import secrets
import uuid
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from telemetry.models import Device, Command
from telemetry.api.ingest import _auth_device


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def get_device_commands(request, device_id):
    """
    ESP32 polls this endpoint to get pending commands
    GET /api/device/{device_id}/commands/
    """
    # Authenticate device
    device = _auth_device(request)
    if not device or device.device_id != device_id:
        return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    
    # Update last poll time
    from telemetry.models import DeviceStatus
    ds, _ = DeviceStatus.objects.get_or_create(device_id=device.device_id)
    ds.last_poll = timezone.now()
    ds.save()
    
    # Get pending commands for this device
    commands = Command.objects.filter(
        device=device,
        status='pending'
    ).exclude(
        expires_at__lt=timezone.now()
    ).order_by('-priority', 'created_at')
    
    # Convert to response format
    command_list = []
    for cmd in commands:
        command_data = {
            'id': cmd.command_id,  # Changed from 'command_id' to 'id' for ESP32 compatibility
            'command_id': cmd.command_id,  # Keep both for backward compatibility
            'command_type': cmd.command_type,
            'priority': cmd.priority,
            'payload': cmd.payload,
            'description': cmd.description,
            'created_at': cmd.created_at.isoformat(),
            'expires_at': cmd.expires_at.isoformat() if cmd.expires_at else None,
        }
        command_list.append(command_data)
        
        # Debug logging
        print(f"📤 SENDING COMMAND TO ESP32:")
        print(f"  Command ID: {cmd.command_id}")
        print(f"  Command Type: {cmd.command_type}")
        print(f"  Device: {device_id}")
        
        # Mark command as sent
        cmd.status = 'sent'
        cmd.sent_at = timezone.now()
        cmd.save()
    
    return Response({
        'commands': command_list,
        'count': len(command_list),
        'device_id': device_id,
        'timestamp': timezone.now().isoformat()
    })


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def report_command_result(request, device_id, command_id):
    """
    ESP32 reports command execution result
    PUT /api/device/{device_id}/commands/{command_id}/
    """
    # Debug logging
    print(f"🔍 COMMAND RESULT DEBUG:")
    print(f"  Device ID: {device_id}")
    print(f"  Command ID: {command_id}")
    print(f"  Request data: {request.data}")
    
    # Authenticate device
    device = _auth_device(request)
    if not device or device.device_id != device_id:
        print(f"❌ Authentication failed for device {device_id}")
        return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    
    # Check if command_id is null or invalid
    if not command_id or command_id == 'null' or command_id == 'None':
        print(f"❌ Invalid command_id: '{command_id}'")
        return Response({
            "detail": f"Invalid command_id: '{command_id}'. Command ID cannot be null or empty."
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        command = Command.objects.get(command_id=command_id, device=device)
        print(f"✅ Found command: {command.command_id} - {command.command_type}")
    except Command.DoesNotExist:
        print(f"❌ Command not found: {command_id} for device {device_id}")
        # List all commands for this device for debugging
        all_commands = Command.objects.filter(device=device)
        print(f"  Available commands for device {device_id}:")
        for cmd in all_commands:
            print(f"    - {cmd.command_id}: {cmd.command_type} ({cmd.status})")
        return Response({"detail": "Command not found"}, status=status.HTTP_404_NOT_FOUND)
    
    # Get result data
    success = request.data.get('success', False)
    response_data = request.data.get('response_data', {})
    error_message = request.data.get('error_message', '')
    current_counters = request.data.get('current_counters', {})
    
    # Update command status
    if success:
        command.status = 'executed'
        command.executed_at = timezone.now()
        command.response_data = response_data
        command.error_message = ''
        
        # Update device last_seen
        device.last_seen = timezone.now()
        device.save()
        
        # Update device status with current counters if provided (for RESET_COUNTERS, etc.)
        if current_counters:
            from telemetry.models import DeviceStatus
            ds, _ = DeviceStatus.objects.get_or_create(device_id=device.device_id)
            ds.current_count_basic = current_counters.get("basic", ds.current_count_basic)
            ds.current_count_standard = current_counters.get("standard", ds.current_count_standard)
            ds.current_count_premium = current_counters.get("premium", ds.current_count_premium)
            ds.last_seen = timezone.now()
            ds.save()
            print(f"🔍 COMMAND RESULT - UPDATED COUNTERS: Basic={ds.current_count_basic}, Standard={ds.current_count_standard}, Premium={ds.current_count_premium}")
        else:
            # Still update DeviceStatus.last_seen even without current_counters
            from telemetry.models import DeviceStatus
            ds, _ = DeviceStatus.objects.get_or_create(device_id=device.device_id)
            ds.last_seen = timezone.now()
            ds.save()
    else:
        command.status = 'failed'
        command.error_message = error_message
        command.response_data = response_data
    
    command.save()
    
    return Response({
        'status': 'updated',
        'command_id': command_id,
        'success': success
    })


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def create_device_command(request, device_id):
    """
    Backend creates new command for device
    POST /api/device/{device_id}/commands/
    """
    try:
        device = Device.objects.get(device_id=device_id)
    except Device.DoesNotExist:
        return Response({"detail": "Device not found"}, status=status.HTTP_404_NOT_FOUND)
    
    # Get command data
    command_type = request.data.get('command_type')
    priority = request.data.get('priority', 'normal')
    payload = request.data.get('payload', {})
    description = request.data.get('description', '')
    expires_in_hours = request.data.get('expires_in_hours', 24)
    
    # Validate command type
    valid_types = [choice[0] for choice in Command.COMMAND_TYPES]
    if command_type not in valid_types:
        return Response({
            "detail": f"Invalid command type. Valid types: {valid_types}"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Generate unique command ID
    command_id = f"{device_id}-{command_type}-{uuid.uuid4().hex[:8]}"
    
    # Calculate expiration time
    expires_at = timezone.now() + timedelta(hours=expires_in_hours)
    
    # Create command
    command = Command.objects.create(
        command_id=command_id,
        device=device,
        command_type=command_type,
        priority=priority,
        payload=payload,
        description=description,
        expires_at=expires_at,
        created_by=request.user
    )
    
    return Response({
        'status': 'created',
        'command_id': command_id,
        'command_type': command_type,
        'device_id': device_id,
        'expires_at': expires_at.isoformat()
    })


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_command_status(request, device_id):
    """
    Get command status for a device
    GET /api/device/{device_id}/commands/status/
    """
    try:
        device = Device.objects.get(device_id=device_id)
    except Device.DoesNotExist:
        return Response({"detail": "Device not found"}, status=status.HTTP_404_NOT_FOUND)
    
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
    recent_commands = commands.order_by('-created_at')[:10]
    command_list = []
    for cmd in recent_commands:
        command_list.append({
            'command_id': cmd.command_id,
            'command_type': cmd.command_type,
            'status': cmd.status,
            'priority': cmd.priority,
            'created_at': cmd.created_at.isoformat(),
            'executed_at': cmd.executed_at.isoformat() if cmd.executed_at else None,
            'error_message': cmd.error_message,
            'retry_count': cmd.retry_count,
        })
    
    return Response({
        'device_id': device_id,
        'stats': stats,
        'recent_commands': command_list
    })


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def retry_command(request, command_id):
    """
    Retry a failed command
    POST /api/commands/{command_id}/retry/
    """
    try:
        command = Command.objects.get(command_id=command_id)
    except Command.DoesNotExist:
        return Response({"detail": "Command not found"}, status=status.HTTP_404_NOT_FOUND)
    
    if not command.can_retry():
        return Response({
            "detail": "Command cannot be retried (max retries reached or invalid status)"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Reset command for retry
    command.status = 'pending'
    command.retry_count += 1
    command.sent_at = None
    command.executed_at = None
    command.error_message = ''
    command.save()
    
    return Response({
        'status': 'retried',
        'command_id': command_id,
        'retry_count': command.retry_count
    })


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def bulk_create_commands(request):
    """
    Create commands for multiple devices
    POST /api/commands/bulk/
    """
    device_ids = request.data.get('device_ids', [])
    command_type = request.data.get('command_type')
    priority = request.data.get('priority', 'normal')
    payload = request.data.get('payload', {})
    description = request.data.get('description', '')
    expires_in_hours = request.data.get('expires_in_hours', 24)
    
    if not device_ids or not command_type:
        return Response({
            "detail": "device_ids and command_type are required"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Validate command type
    valid_types = [choice[0] for choice in Command.COMMAND_TYPES]
    if command_type not in valid_types:
        return Response({
            "detail": f"Invalid command type. Valid types: {valid_types}"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    created_commands = []
    failed_devices = []
    
    with transaction.atomic():
        for device_id in device_ids:
            try:
                device = Device.objects.get(device_id=device_id)
                
                # Generate unique command ID
                command_id = f"{device_id}-{command_type}-{uuid.uuid4().hex[:8]}"
                
                # Calculate expiration time
                expires_at = timezone.now() + timedelta(hours=expires_in_hours)
                
                # Create command
                command = Command.objects.create(
                    command_id=command_id,
                    device=device,
                    command_type=command_type,
                    priority=priority,
                    payload=payload,
                    description=description,
                    expires_at=expires_at,
                    created_by=request.user
                )
                
                created_commands.append({
                    'command_id': command_id,
                    'device_id': device_id
                })
                
            except Device.DoesNotExist:
                failed_devices.append(device_id)
    
    return Response({
        'status': 'bulk_created',
        'created_count': len(created_commands),
        'failed_count': len(failed_devices),
        'created_commands': created_commands,
        'failed_devices': failed_devices
    })
