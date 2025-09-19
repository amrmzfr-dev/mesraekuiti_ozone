from django.core.management.base import BaseCommand
from django.utils import timezone
from telemetry.models import Outlet, Machine, MachineDevice, Device, DeviceStatus, TelemetryEvent, UsageStatistics
import random


class Command(BaseCommand):
    help = "Seed demo data for testing UI (creates ~10-20 devices, outlets, machines, events)."

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=12, help='Approx number of devices/machines to create')
        parser.add_argument('--days', type=int, default=10, help='Number of days of historical data to generate')
        parser.add_argument('--max-per-day', type=int, default=9, help='Max events per treatment per day (random up to this)')

    def handle(self, *args, **options):
        random.seed(42)
        count = int(options['count'])
        days = int(options['days'])
        max_per_day = max(1, int(options['max_per_day']))

        # Create outlets
        outlets = []
        for i in range(max(3, count // 4)):
            outlet, _ = Outlet.objects.get_or_create(
                name=f"Outlet {i+1}",
                defaults={
                    'location': f"Area {i+1}",
                    'address': f"{100+i} Demo Street",
                    'contact_person': f"PIC {i+1}",
                    'contact_phone': f"+60-1{i}2345678",
                    'is_active': True,
                }
            )
            outlets.append(outlet)

        # Create devices (ESP32)
        devices = []
        for i in range(count):
            dev, _ = Device.objects.get_or_create(
                mac=f"AA:BB:CC:DD:EE:{i:02d}",
                defaults={
                    'device_id': f"esp32-{1000+i}",
                    'token': f"token-{1000+i}",
                    'assigned': True,
                    'firmware': f"v1.{i%5}.{i%3}",
                }
            )
            devices.append(dev)

        # Create machines and bind devices
        machines = []
        for i in range(count):
            outlet = random.choice(outlets)
            machine, _ = Machine.objects.get_or_create(
                name=f"Machine {i+1}",
                outlet=outlet,
                defaults={
                    'machine_type': 'Ozone Generator',
                    'is_active': True,
                }
            )
            machines.append(machine)

        # Bind devices to machines (one active per machine)
        now = timezone.now()
        for machine, device in zip(machines, devices):
            # Ensure only one active per machine and per device
            MachineDevice.objects.filter(machine=machine, is_active=True).update(is_active=False)
            MachineDevice.objects.filter(device_id=device.device_id, is_active=True).update(is_active=False)
            MachineDevice.objects.update_or_create(
                machine=machine,
                device_id=device.device_id,
                defaults={'is_active': True, 'deactivated_date': None}
            )
            DeviceStatus.objects.update_or_create(
                device_id=device.device_id,
                defaults={
                    'wifi_connected': True,
                    'last_seen': now,
                    'rtc_available': True,
                    'sd_card_available': True,
                    'current_count_basic': random.randint(0, 50),
                    'current_count_standard': random.randint(0, 50),
                    'current_count_premium': random.randint(0, 50),
                    'device_timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
                }
            )

        # Generate recent events and daily stats (past N days)
        for device in devices:
            for d in range(days):
                day_dt = now - timezone.timedelta(days=days - d - 1)
                daily_counts = {
                    'BASIC': random.randint(0, max_per_day),
                    'STANDARD': random.randint(0, max_per_day),
                    'PREMIUM': random.randint(0, max_per_day),
                }
                total_events = sum(daily_counts.values())
                # Create events
                for etype, cnt in daily_counts.items():
                    for k in range(cnt):
                        TelemetryEvent.objects.create(
                            device_id=device.device_id,
                            event_type=etype,
                            count_basic=None,
                            count_standard=None,
                            count_premium=None,
                            occurred_at=day_dt - timezone.timedelta(hours=random.randint(0, 23)),
                            device_timestamp=day_dt.strftime('%Y-%m-%d %H:%M:%S'),
                            wifi_status=True,
                            payload={}
                        )

                # Update daily aggregated stats
                stats, _ = UsageStatistics.objects.get_or_create(
                    device_id=device.device_id,
                    date=day_dt.date(),
                    defaults={
                        'basic_count': 0,
                        'standard_count': 0,
                        'premium_count': 0,
                        'total_events': 0,
                    }
                )
                stats.basic_count += daily_counts['BASIC']
                stats.standard_count += daily_counts['STANDARD']
                stats.premium_count += daily_counts['PREMIUM']
                stats.total_events += total_events
                stats.first_event = stats.first_event or day_dt
                stats.last_event = day_dt
                stats.save()

        self.stdout.write(self.style.SUCCESS('Seeded demo data.'))


