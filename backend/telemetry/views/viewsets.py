from rest_framework import viewsets, mixins, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from datetime import timedelta
from telemetry.models import TelemetryEvent, DeviceStatus, Outlet, Machine, MachineDevice, Device
from telemetry.serializers import TelemetryEventSerializer, DeviceStatusSerializer, OutletSerializer, MachineSerializer


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
      from datetime import timedelta as _td
      from django.utils import timezone as _tz
      days_int = int(days)
      qs = qs.filter(occurred_at__gte=_tz.now() - _td(days=days_int))
    if exclude_status:
      qs = qs.exclude(event_type='status')
    return qs.order_by('-occurred_at')

  @action(detail=False, methods=["get"], url_path="analytics")
  def analytics(self, request):
    from telemetry.api.stats import test_stats_api
    return test_stats_api(request)


class DeviceStatusViewSet(mixins.ListModelMixin,
                         mixins.RetrieveModelMixin,
                         viewsets.GenericViewSet):
  queryset = DeviceStatus.objects.all()
  serializer_class = DeviceStatusSerializer
  permission_classes = [permissions.AllowAny]

  @action(detail=False, methods=["get"], url_path="online")
  def online_devices(self, request):
    recent_threshold = timezone.now() - timedelta(minutes=5)
    online_devices = self.get_queryset().filter(last_seen__gte=recent_threshold)
    return Response(DeviceStatusSerializer(online_devices, many=True).data)

  @action(detail=False, methods=["get"], url_path="all")
  def all_devices(self, request):
    all_devices = self.get_queryset().order_by('-last_seen')
    return Response(DeviceStatusSerializer(all_devices, many=True).data)


class OutletViewSet(viewsets.ModelViewSet):
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
      qs = qs.filter(devices__device_id=device_id, devices__is_active=True)
    return qs

  @action(detail=False, methods=["get"], url_path="unregistered")
  def unregistered_devices(self, request):
    registered_device_ids = set(MachineDevice.objects.values_list('device_id', flat=True))
    unregistered_devices = DeviceStatus.objects.exclude(device_id__in=registered_device_ids)
    return Response(DeviceStatusSerializer(unregistered_devices, many=True).data)

  @action(detail=False, methods=["post"], url_path="register")
  def register_device(self, request):
    device_id = request.data.get('device_id')
    outlet_id = request.data.get('outlet_id')
    name = request.data.get('name', '')
    if not device_id or not outlet_id:
      return Response({"detail": "device_id and outlet_id required"}, status=400)
    try:
      outlet = Outlet.objects.get(id=outlet_id)
    except Outlet.DoesNotExist:
      return Response({"detail": "Outlet not found"}, status=404)
    if MachineDevice.objects.filter(device_id=device_id, is_active=True).exists():
      return Response({"detail": "Device already registered"}, status=400)
    machine = Machine.objects.create(
      outlet=outlet,
      name=name or f"Machine {device_id[-6:]}"
    )
    MachineDevice.objects.create(
      machine=machine,
      device_id=device_id,
      is_active=True
    )
    return Response(MachineSerializer(machine).data, status=201)


