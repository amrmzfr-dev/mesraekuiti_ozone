from django.core.management.base import BaseCommand
from django.utils import timezone
import random
from datetime import timedelta

from telemetry.models import Outlet, Machine, Device, DeviceStatus, TelemetryEvent


REGIONS = [
    "CENTRAL 1",
    "CENTRAL 2",
    "NORTHERN",
    "SOURTHERN",
    "EAST COAST",
    "EAST M'SIA",
    "INDONESIA",
]


class Command(BaseCommand):
    help = "Flushes non-user data and seeds dummy outlets, machines, devices and treatment events"

    def add_arguments(self, parser):
        parser.add_argument("--events", type=int, default=12430, help="Number of treatment events to generate")

    def handle(self, *args, **options):
        num_events = options["events"]

        self.stdout.write(self.style.WARNING("Clearing existing telemetry data (except users)..."))
        TelemetryEvent.objects.all().delete()
        DeviceStatus.objects.all().delete()
        Device.objects.all().delete()
        Machine.objects.all().delete()
        Outlet.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("Cleared."))

        # Create 10 outlets
        outlets = []
        for i in range(10):
            o = Outlet.objects.create(
                outlet_name=f"Outlet {i+1}",
                region=random.choice(REGIONS),
            )
            outlets.append(o)

        # Create 20 machines, 2 per outlet
        machines = []
        for i in range(20):
            outlet = outlets[i // 2]
            m = Machine.objects.create(
                machine_code=f"M-{i+1:03d}",
                outlet=outlet,
            )
            machines.append(m)

        # Create one device per machine and bind
        devices = []
        for i, m in enumerate(machines):
            mac = f"AA:BB:CC:DD:EE:{i:02X}"
            d = Device.objects.create(
                mac=mac,
                device_id=mac,
                firmware="v1.0.0",
                token=f"tok_{i:04d}",
                assigned=True,
            )
            m.device = d
            m.save(update_fields=["device"])
            # Initialize status
            DeviceStatus.objects.create(
                device_id=d.device_id,
                wifi_connected=True,
                current_count_basic=0,
                current_count_standard=0,
                current_count_premium=0,
                last_seen=timezone.now(),
            )
            devices.append(d)

        # Prepare per-device counters per treatment
        per_device_counts = {
            d.device_id: {"BASIC": 0, "STANDARD": 0, "PREMIUM": 0} for d in devices
        }

        # Distribute events over the last 30 days
        now = timezone.now()
        for _ in range(num_events):
            d = random.choice(devices)
            t = random.choices(["BASIC", "STANDARD", "PREMIUM"], weights=[6, 3, 2])[0]
            per_device_counts[d.device_id][t] += 1
            counter_val = per_device_counts[d.device_id][t]
            # Make a unique id using overall sum of this device counters
            total_for_device = sum(per_device_counts[d.device_id].values())
            event_id = f"{d.device_id}-{total_for_device:010d}"
            occurred_at = now - timedelta(days=random.randint(0, 30), minutes=random.randint(0, 1440))

            TelemetryEvent.objects.create(
                device_id=d.device_id,
                event_id=event_id,
                event="treatment",
                treatment=t,
                counter=counter_val,
                occurred_at=occurred_at,
                event_type=t,
                count_basic=None,
                count_standard=None,
                count_premium=None,
                device_timestamp=str(int(occurred_at.timestamp())),
                wifi_status=True,
                payload={},
            )

        # Update DeviceStatus totals
        for d in devices:
            ds = DeviceStatus.objects.get(device_id=d.device_id)
            ds.current_count_basic = per_device_counts[d.device_id]["BASIC"]
            ds.current_count_standard = per_device_counts[d.device_id]["STANDARD"]
            ds.current_count_premium = per_device_counts[d.device_id]["PREMIUM"]
            ds.last_seen = now
            ds.save()

        self.stdout.write(self.style.SUCCESS(
            f"Seed complete: {len(outlets)} outlets, {len(machines)} machines, {len(devices)} devices, {num_events} events"
        ))



