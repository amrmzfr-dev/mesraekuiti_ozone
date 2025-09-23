from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDate, TruncHour, TruncMinute, TruncMonth
from datetime import timedelta
from telemetry.models import TelemetryEvent, UsageStatistics, Outlet, Machine, MachineDevice
from telemetry.serializers import UsageStatisticsSerializer, TelemetryEventSerializer, DeviceStatusSerializer


@api_view(["GET"]) 
@permission_classes([permissions.IsAuthenticated])
def test_stats_api(request):
  outlet_id = request.query_params.get('outlet_id')
  machine_id = request.query_params.get('machine_id')
  device_id = request.query_params.get('device_id')
  granularity = (request.query_params.get('granularity') or 'day').lower()
  cumulative = (request.query_params.get('cumulative') or 'false').lower() == 'true'
  ma_window = int(request.query_params.get('ma', 0))
  days = int(request.query_params.get('days', 7))
  start_param = request.query_params.get('start')
  end_param = request.query_params.get('end')

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

  start_dt = start_dt.astimezone(timezone.get_current_timezone()).replace(hour=0, minute=0, second=0, microsecond=0)
  end_dt = end_dt.astimezone(timezone.get_current_timezone()).replace(hour=23, minute=59, second=59, microsecond=999000)

  device_ids = None
  if device_id:
    device_ids = [device_id]
  elif machine_id:
    device_ids = list(MachineDevice.objects.filter(machine_id=machine_id).values_list('device_id', flat=True).distinct())
  elif outlet_id:
    machine_ids = list(Machine.objects.filter(outlet_id=outlet_id).values_list('id', flat=True))
    device_ids = list(MachineDevice.objects.filter(machine_id__in=machine_ids).values_list('device_id', flat=True).distinct())

  ev_qs = TelemetryEvent.objects.exclude(event_type='status').filter(
    occurred_at__gte=start_dt,
    occurred_at__lte=end_dt,
  )
  if device_ids is not None:
    ev_qs = ev_qs.filter(device_id__in=device_ids)

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
    step = None
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

  labels = []
  end_inclusive = end_dt
  if granularity == 'month':
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

  result_map = {g['bucket'].strftime(label_fmt): g for g in grouped}
  series = { 'basic': [], 'standard': [], 'premium': [], 'total': [] }
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

  if cumulative:
    for k in list(series.keys()):
      series[k] = _cumulative(series[k])
  if ma_window and ma_window > 1:
    for k in list(series.keys()):
      series[k] = _moving_average(series[k], ma_window)

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
    prev_labels = []
    cur_p = prev_start
    while len(prev_labels) < len(labels):
      prev_labels.append(cur_p.strftime(label_fmt))
      cur_p += step
    prev_map = {g['bucket'].strftime(label_fmt): g for g in grouped_prev}
    prev_series = { 'basic': [], 'standard': [], 'premium': [], 'total': [] }
    for lab in prev_labels:
      row = prev_map.get(lab)
      prev_series['basic'].append((row or {}).get('basic', 0))
      prev_series['standard'].append((row or {}).get('standard', 0))
      prev_series['premium'].append((row or {}).get('premium', 0))
      prev_series['total'].append((row or {}).get('total', 0))

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
  outlet_id = request.query_params.get('outlet_id')
  machine_id = request.query_params.get('machine_id')
  data = {}
  data['outlets'] = list(Outlet.objects.all().order_by('name').values('id', 'name'))
  if outlet_id:
    data['machines'] = list(Machine.objects.filter(outlet_id=outlet_id).order_by('name').values('id', 'name'))
  if machine_id:
    data['devices'] = list(MachineDevice.objects.filter(machine_id=machine_id).order_by('-is_active', '-assigned_date').values('device_id', 'is_active'))
  return Response(data)


