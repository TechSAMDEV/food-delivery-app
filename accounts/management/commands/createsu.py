from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = 'Creates a default superuser if none exists'

    def handle(self, *args, **options):
        User = get_user_model()
        if not User.objects.filter(is_superuser=True).exists():
            User.objects.create_superuser(
                email='bro',    # Update with your admin email
                username='samuelsuperguy@gmail.com',             # Update with your admin username
                password='b@tman123'   # Update with your secure password
            )
            self.stdout.write(self.style.SUCCESS('Successfully created default superuser.'))
        else:
            self.stdout.write('Superuser already exists.')