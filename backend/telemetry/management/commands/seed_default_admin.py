from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Create or reset default admin user (username: admin, password: admin)"

    def handle(self, *args, **options):
        User = get_user_model()
        user, created = User.objects.get_or_create(username='admin', defaults={
            'is_staff': True,
            'is_superuser': False,
        })
        user.is_staff = True
        user.is_superuser = False
        user.set_password('admin')
        user.save()
        if created:
            self.stdout.write(self.style.SUCCESS('Created default admin user: admin/admin'))
        else:
            self.stdout.write(self.style.WARNING('Reset password for user: admin (admin)'))



