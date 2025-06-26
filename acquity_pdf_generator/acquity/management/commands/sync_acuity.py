# import requests
# from requests.auth import HTTPBasicAuth

# API_KEY = 'e242108a459377126a4967738b3e3cf2'  # Replace this
# # User ID: 30621503
# # API Key: e242108a459377126a4967738b3e3cf2
# # Endpoint to get upcoming appointments
# import requests
# from requests.auth import HTTPBasicAuth

# API_KEY = 'e242108a459377126a4967738b3e3cf2'  # Replace this

# # Endpoint to get upcoming appointments
# url = 'https://acuityscheduling.com/api/v1/appointments'

# # Optional filters
# params = {
#     'minDate': 'today',
#     'max': 5  # just fetch 5 upcoming to test
# }

# response = requests.get(url, auth=HTTPBasicAuth(API_KEY, ''), params=params)

# if response.status_code == 200:
#     appointments = response.json()
#     for appt in appointments:
#         print(f"Name: {appt['firstName']} {appt['lastName']}")
#         print(f"Time: {appt['datetime']}")
#         print(f"Phone: {appt.get('phone', 'N/A')}")
#         print(f"Address: {appt.get('address', 'N/A')}")
        
#         # Intake form responses
#         if 'forms' in appt:
#             print("\n--- Intake Form Responses ---")
#             for field in appt['forms']:
#                 print(f"{field['label']}: {field['value']}")
#         print("\n" + "-" * 50)
# else:
#     print(f"Error: {response.status_code}")
#     print(response.text)
# import requests
# from requests.auth import HTTPBasicAuth

# # Your credentials
# USER_ID = '30621503'
# API_KEY = 'e242108a459377126a4967738b3e3cf2'

# # Endpoint
# url = 'https://acuityscheduling.com/api/v1/appointments'

# # Optional query params
# params = {
#     'minDate': 'today',
#     'max': 5
# }

# # Make the request
# response = requests.get(url, auth=HTTPBasicAuth(USER_ID, API_KEY), params=params)

# # Print results
# print(f"Status Code: {response.status_code}")
# print(response.text)




# scheduling/management/commands/sync_acuity.py
from django.core.management.base import BaseCommand
from acquity.services import AcuityService

class Command(BaseCommand):
    help = 'Sync data from Acuity Scheduling API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--calendars-only',
            action='store_true',
            help='Sync only calendars',
        )
        parser.add_argument(
            '--appointments-only',
            action='store_true',
            help='Sync only appointments',
        )

    def handle(self, *args, **options):
        acuity_service = AcuityService()
        
        try:
            if options['calendars_only']:
                self.stdout.write('Syncing calendars...')
                acuity_service.sync_calendars()
                acuity_service.sync_appointment_types()
                self.stdout.write(self.style.SUCCESS('Calendars synced successfully'))
            elif options['appointments_only']:
                self.stdout.write('Syncing appointments...')
                acuity_service.sync_appointments()
                
                self.stdout.write(self.style.SUCCESS('Appointments synced successfully'))
            else:
                self.stdout.write('Syncing all data...')
                acuity_service.sync_calendars()
                acuity_service.sync_appointment_types()
                acuity_service.sync_appointments()
                
                self.stdout.write(self.style.SUCCESS('All data synced successfully'))
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error during sync: {str(e)}')
            ) 