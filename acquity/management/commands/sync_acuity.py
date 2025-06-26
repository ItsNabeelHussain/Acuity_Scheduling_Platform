import time
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from acquity.services import AcuityService
from acquity.models import Calendar, UserCalendar

class Command(BaseCommand):
    """
    A Django management command to synchronize data from the Acuity Scheduling API.
    
    This command can be run in two modes:
    1.  One-time sync: `python manage.py sync_acuity`
    2.  Daemon mode: `python manage.py sync_acuity --daemon`
        This will run the sync process continuously every minute.
    """
    help = 'Synchronizes calendars, appointment types, and appointments from Acuity API.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--daemon',
            action='store_true',
            help='Run command in daemon mode to sync continuously every minute.',
        )

    def handle(self, *args, **kwargs):
        is_daemon = kwargs['daemon']
        
        if is_daemon:
            self.stdout.write(self.style.SUCCESS("Starting Acuity sync daemon..."))
            while True:
                self.run_sync()
                self.stdout.write(f"Next sync in 60 seconds...")
                time.sleep(60)
        else:
            self.stdout.write("Running a one-time sync.")
            self.run_sync()

    def run_sync(self):
        """Performs a single sync operation."""
        self.stdout.write(f"Sync started at {time.ctime()}")
        
        service = AcuityService()
        
        try:
            # Sync all data
            service.sync_calendars()
            service.sync_appointment_types()
            service.sync_appointments()
            self.stdout.write(self.style.SUCCESS("...Core data synced successfully."))

            # Assign calendars to superusers
            calendars = Calendar.objects.all()
            superusers = User.objects.filter(is_superuser=True)
            
            if superusers.exists() and calendars.exists():
                assignment_count = 0
                for user in superusers:
                    for calendar in calendars:
                        _, created = UserCalendar.objects.get_or_create(user=user, calendar=calendar)
                        if created:
                            assignment_count += 1
                if assignment_count > 0:
                    self.stdout.write(self.style.SUCCESS(f"...Created {assignment_count} new calendar assignments for superusers."))

            self.stdout.write(self.style.SUCCESS("Acuity data synchronization complete."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"An error occurred during sync: {e}")) 