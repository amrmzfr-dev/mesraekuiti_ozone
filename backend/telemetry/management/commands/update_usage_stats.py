from django.core.management.base import BaseCommand
from django.db.models import Count, Sum, Min, Max
from django.utils import timezone
from datetime import timedelta, date
from telemetry.models import TelemetryEvent, UsageStatistics

class Command(BaseCommand):
    help = 'Update usage statistics from telemetry events'

    def handle(self, *args, **options):
        self.stdout.write('Updating usage statistics...')
        
        # Get all unique device IDs
        device_ids = TelemetryEvent.objects.values_list('device_id', flat=True).distinct()
        
        for device_id in device_ids:
            self.stdout.write(f'Processing device: {device_id}')
            
            # Get events for the last 30 days
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)
            
            events = TelemetryEvent.objects.filter(
                device_id=device_id,
                occurred_at__date__gte=start_date,
                occurred_at__date__lte=end_date
            ).exclude(event_type='status')
            
            # Group by date
            daily_events = {}
            for event in events:
                event_date = event.occurred_at.date()
                if event_date not in daily_events:
                    daily_events[event_date] = {
                        'basic_count': 0,
                        'standard_count': 0,
                        'premium_count': 0,
                        'total_events': 0,
                        'first_event': None,
                        'last_event': None
                    }
                
                # Count events by type
                if event.event_type == 'BASIC':
                    daily_events[event_date]['basic_count'] += 1
                elif event.event_type == 'STANDARD':
                    daily_events[event_date]['standard_count'] += 1
                elif event.event_type == 'PREMIUM':
                    daily_events[event_date]['premium_count'] += 1
                
                daily_events[event_date]['total_events'] += 1
                
                # Track first and last event times
                if daily_events[event_date]['first_event'] is None or event.occurred_at < daily_events[event_date]['first_event']:
                    daily_events[event_date]['first_event'] = event.occurred_at
                if daily_events[event_date]['last_event'] is None or event.occurred_at > daily_events[event_date]['last_event']:
                    daily_events[event_date]['last_event'] = event.occurred_at
            
            # Create or update UsageStatistics records
            for event_date, stats in daily_events.items():
                usage_stat, created = UsageStatistics.objects.get_or_create(
                    device_id=device_id,
                    date=event_date,
                    defaults=stats
                )
                
                if not created:
                    # Update existing record
                    usage_stat.basic_count = stats['basic_count']
                    usage_stat.standard_count = stats['standard_count']
                    usage_stat.premium_count = stats['premium_count']
                    usage_stat.total_events = stats['total_events']
                    usage_stat.first_event = stats['first_event']
                    usage_stat.last_event = stats['last_event']
                    usage_stat.save()
                
                self.stdout.write(f'  {event_date}: {stats["total_events"]} events')
        
        self.stdout.write(
            self.style.SUCCESS('Usage statistics updated successfully!')
        )
