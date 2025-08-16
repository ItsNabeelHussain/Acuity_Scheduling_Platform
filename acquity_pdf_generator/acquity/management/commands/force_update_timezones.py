from django.core.management.base import BaseCommand
from acquity.models import Appointment
from acquity.services import AcuityService
from django.utils import timezone

class Command(BaseCommand):
    help = 'Force update all existing appointments with correct timezone information from Acuity'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write('DRY RUN MODE - No changes will be made')
        
        # Get all appointments
        appointments = Appointment.objects.all()
        total_appointments = appointments.count()
        
        self.stdout.write(f'Found {total_appointments} appointments to update')
        
        if not dry_run:
            # Initialize Acuity service
            acuity_service = AcuityService()
            
            updated_count = 0
            error_count = 0
            
            for appointment in appointments:
                try:
                    # Use the new method to update timezone from Acuity
                    if acuity_service.update_existing_appointment_timezone(appointment):
                        updated_count += 1
                        self.stdout.write(f'Updated appointment {appointment.acuity_appointment_id}')
                    else:
                        error_count += 1
                        self.stdout.write(
                            self.style.WARNING(f'Could not update appointment {appointment.acuity_appointment_id}')
                        )
                    
                except Exception as e:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(f'Error updating appointment {appointment.acuity_appointment_id}: {e}')
                    )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Timezone update completed: {updated_count} updated, {error_count} errors'
                )
            )
        else:
            self.stdout.write('Dry run completed - no changes made')
            self.stdout.write('Run without --dry-run to apply changes')

        self.stdout.write(
            self.style.WARNING(
                '\nIMPORTANT: For the most accurate timezone information, '
                'run: python manage.py sync_acuity --appointments-only'
            )
        ) 