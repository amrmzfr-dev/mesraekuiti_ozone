from django.db import migrations

def migrate_machine_devices(apps, schema_editor):
    """Migrate existing machine data to new structure"""
    Machine = apps.get_model('telemetry', 'Machine')
    MachineDevice = apps.get_model('telemetry', 'MachineDevice')
    
    # This migration will be run after the schema changes
    # We'll handle the data migration in a separate step
    pass

def reverse_migrate_machine_devices(apps, schema_editor):
    """Reverse migration"""
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('telemetry', '0005_alter_machine_options_remove_machine_device_id_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_machine_devices, reverse_migrate_machine_devices),
    ]
