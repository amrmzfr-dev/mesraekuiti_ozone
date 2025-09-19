from django.core.management.base import BaseCommand
from telemetry.models import DeviceStatus

class Command(BaseCommand):
    help = 'Update device counts with accumulated values from database events'

    def handle(self, *args, **options):
        self.stdout.write('Updating device counts with accumulated values...')
        
        devices = DeviceStatus.objects.all()
        
        for device in devices:
            self.stdout.write(f'Updating device: {device.device_id}')
            
            # Get old counts
            old_basic = device.current_count_basic
            old_standard = device.current_count_standard
            old_premium = device.current_count_premium
            
            # Update with accumulated counts
            device.update_accumulated_counts()
            
            # Show the change
            self.stdout.write(f'  Basic: {old_basic} → {device.current_count_basic}')
            self.stdout.write(f'  Standard: {old_standard} → {device.current_count_standard}')
            self.stdout.write(f'  Premium: {old_premium} → {device.current_count_premium}')
        
        self.stdout.write(
            self.style.SUCCESS('Device counts updated successfully!')
        )
