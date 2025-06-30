# scheduling/models.py

# scheduling/services.py
import requests
from requests.auth import HTTPBasicAuth
from django.conf import settings
from django.utils import timezone
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .models import Calendar, AppointmentType, Appointment
from django.db import transaction

class AcuityService:
    def __init__(self):
        self.base_url = "https://acuityscheduling.com/api/v1"
        self.auth = HTTPBasicAuth(settings.ACUITY_USER_ID, settings.ACUITY_API_KEY)

    def _parse_acuity_datetime(self, apt_data, time_key):
        """
        Parses the many datetime formats returned by the Acuity API.
        
        Handles:
        1. Full ISO-like strings (e.g., '2025-09-13T18:00:00-0400').
        2. Time-only strings (e.g., '7:30pm') which require a separate 'date' field.
        3. Multiple date formats for the 'date' field ('YYYY-MM-DD' or 'Month Day, YYYY').
        """
        time_str = apt_data.get(time_key)
        if not time_str:
            return None, f"Missing '{time_key}' field"

        # Strategy 1: It's an ISO-like string (contains 'T').
        if 'T' in time_str:
            try:
                # Normalize timezone for fromisoformat (for Python < 3.11).
                if time_str.endswith('Z'):
                    time_str = time_str.replace('Z', '+00:00')
                elif len(time_str) > 4 and time_str[-5] in ('+', '-') and time_str[-3] != ':':
                    time_str = time_str[:-2] + ':' + time_str[-2:]
                return datetime.fromisoformat(time_str), None
            except (ValueError, TypeError) as e:
                return None, f"Invalid ISO-like format: {e}"

        # Strategy 2: It's a time string (e.g., "7:30pm").
        if 'am' in time_str.lower() or 'pm' in time_str.lower():
            try:
                date_str = apt_data.get('date')
                if not date_str:
                    return None, "Missing 'date' field for time-only appointment"
                
                # The 'date' field itself can have multiple formats.
                try:
                    dt_part = datetime.strptime(date_str, '%Y-%m-%d')
                except ValueError:
                    dt_part = datetime.strptime(date_str, '%B %d, %Y')
                    
                time_part = datetime.strptime(time_str, '%I:%M%p').time()
                naive_dt = datetime.combine(dt_part.date(), time_part)

                # Apply timezone if available.
                tz_str = apt_data.get('timezone')
                if tz_str:
                    try:
                        tz = ZoneInfo(tz_str)
                        return naive_dt.replace(tzinfo=tz), None
                    except ZoneInfoNotFoundError:
                        print(f"Warning: Unknown timezone '{tz_str}' for apt {apt_data.get('id')}. Using naive dt.")
                        return naive_dt, None
                return naive_dt, None
            except (ValueError, TypeError) as e:
                return None, f"Could not parse date/time combination: {e}"
        
        return None, f"Unrecognized datetime format: '{time_str}'"

    def get_calendars(self):
        """Fetch calendars from Acuity API"""
        try:
            response = requests.get(f"{self.base_url}/calendars", auth=self.auth)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching calendars: {e}")
            return []
        except Exception as e:
            import logging
            logging.exception('Unexpected error in get_calendars')
            return []

    def get_appointment_types(self):
        """Fetch appointment types from Acuity API"""
        try:
            response = requests.get(f"{self.base_url}/appointment-types", auth=self.auth)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching appointment types: {e}")
            return []
        except Exception as e:
            import logging
            logging.exception('Unexpected error in get_appointment_types')
            return []

    def get_appointments(self, calendar_id=None, start_date=None, end_date=None):
        """Fetch appointments from Acuity API with pagination support"""
        all_appointments = []
        page = 1
        
        while True:
            try:
                params = {'page': page}
                if calendar_id:
                    params['calendarID'] = calendar_id
                if start_date:
                    params['minDate'] = start_date.strftime('%Y-%m-%d')
                if end_date:
                    params['maxDate'] = end_date.strftime('%Y-%m-%d')
                    
                response = requests.get(f"{self.base_url}/appointments", auth=self.auth, params=params)
                response.raise_for_status()
                appointments = response.json()
                
                # If no appointments returned, we've reached the end
                if not appointments:
                    break
                    
                all_appointments.extend(appointments)
                page += 1
                
                # Optional: Add a safety limit to prevent infinite loops
                if page > 1000:  # Max 1000 pages (100,000 appointments)
                    print("Warning: Reached maximum page limit (1000). Some appointments may not be fetched.")
                    break
                    
            except requests.exceptions.RequestException as e:
                print(f"Error fetching appointments page {page}: {e}")
                break
            except Exception as e:
                import logging
                logging.exception(f'Unexpected error in get_appointments page {page}')
                break
        
        print(f"Fetched {len(all_appointments)} total appointments across {page-1} pages")
        return all_appointments

    def sync_calendars(self):
        """Sync calendars from Acuity to local database"""
        calendars_data = self.get_calendars()
        for cal_data in calendars_data:
            Calendar.objects.update_or_create(
                acuity_calendar_id=str(cal_data['id']),
                defaults={
                    'name': cal_data['name'],
                    'description': cal_data.get('description', ''),
                }
            )

    def sync_appointment_types(self):
        """Sync appointment types from Acuity to local database"""
        types_data = self.get_appointment_types()
        for type_data in types_data:
            AppointmentType.objects.update_or_create(
                acuity_type_id=str(type_data['id']),
                defaults={
                    'name': type_data['name'],
                    'duration': type_data['duration'],
                    'price': type_data.get('price', 0),
                    'description': type_data.get('description', ''),
                }
            )

    def sync_appointments(self, calendar_id=None, batch_size=100, days_back=60):
        """Sync appointments from Acuity to local database in batches to prevent memory issues"""
        from django.db import transaction
        from datetime import datetime, timedelta
        
        # Calculate date range for last 2 months (60 days)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=60)
        
        print(f"Starting sync with batch size: {batch_size}")
        print(f"Calendar ID filter: {calendar_id}")
        print(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} (last 60 days)")
        
        if calendar_id is None:
            # Fetch all calendars and sync each one
            calendars = self.get_calendars()
            total_created = 0
            total_updated = 0
            total_processed = 0
            total_appointments = 0
            for cal in calendars:
                cal_id = str(cal['id'])
                cal_name = cal.get('name', '')
                print(f"\n--- Syncing calendar: {cal_name} (ID: {cal_id}) ---")
                created_count = 0
                updated_count = 0
                processed_appointment_ids = set()
                page = 1
                while True:
                    try:
                        params = {'page': page, 'max': batch_size, 'calendarID': cal_id, 'canceled': 'all'}
                        params['minDate'] = start_date.strftime('%Y-%m-%d')
                        params['maxDate'] = end_date.strftime('%Y-%m-%d')
                        print(f"Fetching page {page} with params: {params}")
                        response = requests.get(f"{self.base_url}/appointments", auth=self.auth, params=params)
                        response.raise_for_status()
                        appointments_batch = response.json()
                        print(f"API returned {len(appointments_batch)} appointments for page {page}")
                        if not appointments_batch:
                            print(f"No appointments returned for page {page}, stopping sync for this calendar")
                            break
                        current_batch_ids = {apt.get('id') for apt in appointments_batch}
                        if page > 1 and current_batch_ids.intersection(processed_appointment_ids):
                            print(f"Page {page} contains duplicate appointments. Stopping sync for this calendar.")
                            break
                        processed_appointment_ids.update(current_batch_ids)
                        batch_created = 0
                        batch_updated = 0
                        with transaction.atomic():
                            for apt_data in appointments_batch:
                                try:
                                    calendar_obj = Calendar.objects.get(acuity_calendar_id=cal_id)
                                    appointment_type_id_val = str(apt_data.get('appointmentTypeID'))
                                    appointment_type = AppointmentType.objects.get(acuity_type_id=appointment_type_id_val)
                                    start_time, start_err = self._parse_acuity_datetime(apt_data, 'datetime')
                                    end_time, end_err = self._parse_acuity_datetime(apt_data, 'endTime')
                                    if start_err or end_err:
                                        continue
                                    processing_fee = 1.0
                                    forms = apt_data.get('forms', [])
                                    for form in forms:
                                        for field in form.get('values', []):
                                            name = field.get('name', '').lower()
                                            if 'processing fee' in name or 'fee:' in name:
                                                try:
                                                    processing_fee = float(field.get('value', 1.0))
                                                    if processing_fee < 2.0:
                                                        processing_fee = 1.0 + float(processing_fee)
                                                except Exception:
                                                    processing_fee = 1.0
                                                break
                                    color_tag = ''
                                    labels = apt_data.get('labels', [])
                                    if labels and isinstance(labels, list) and len(labels) > 0:
                                        color_tag = labels[0].get('color', '')
                                    appointment, created = Appointment.objects.update_or_create(
                                        acuity_appointment_id=str(apt_data.get('id', '')),
                                        defaults={
                                            'calendar': calendar_obj,
                                            'appointment_type': appointment_type,
                                            'client_name': f"{apt_data.get('firstName', '')} {apt_data.get('lastName', '')}",
                                            'client_email': apt_data.get('email', ''),
                                            'client_phone': apt_data.get('phone', ''),
                                            'start_time': start_time,
                                            'end_time': end_time,
                                            'notes': apt_data.get('notes', ''),
                                            'price': apt_data.get('price', 0),
                                            'status': apt_data.get('status', 'scheduled').lower(),
                                            'form_data': forms,
                                            'processing_fee': processing_fee,
                                            'last_synced': timezone.now(),
                                            'color_tag': color_tag,
                                        }
                                    )
                                    if created:
                                        batch_created += 1
                                        created_count += 1
                                    else:
                                        batch_updated += 1
                                        updated_count += 1
                                except Exception as e:
                                    import logging
                                    logging.exception(f"Unexpected error syncing appointment {apt_data.get('id', 'unknown')}")
                                    continue
                        print(f"Batch {page} saved to database: {batch_created} created, {batch_updated} updated")
                        page += 1
                        if page > 1000:
                            print("Warning: Reached maximum page limit (1000). Some appointments may not be fetched.")
                            break
                    except Exception as e:
                        import logging
                        logging.exception(f'Unexpected error in sync_appointments page {page}')
                        break
                print(f"Sync completed for calendar {cal_name}: {created_count} new, {updated_count} updated, {len(processed_appointment_ids)} unique appointments processed.")
                total_created += created_count
                total_updated += updated_count
                total_processed += len(processed_appointment_ids)
            print(f"\n=== All calendars sync summary ===")
            print(f"Total new appointments created: {total_created}")
            print(f"Total existing appointments updated: {total_updated}")
            print(f"Total unique appointments processed: {total_processed}")
            print(f"Total appointments in database: {Appointment.objects.count()}")
            return
        # If calendar_id is provided, use the original logic for a single calendar
        # ... existing code ...

    def sync_appointments_by_date_range(self, start_date=None, end_date=None, calendar_id=None, batch_size=100):
        """Sync appointments from Acuity to local database by date range to minimize memory usage"""
        from django.db import transaction
        
        print(f"Starting date-range sync: {start_date} to {end_date} with batch size: {batch_size}")
        
        created_count = 0
        updated_count = 0
        total_processed = 0
        page = 1
        
        while True:
            try:
                # Fetch one batch of appointments for the date range
                params = {'page': page, 'max': batch_size}
                if calendar_id:
                    params['calendarID'] = calendar_id
                if start_date:
                    params['minDate'] = start_date.strftime('%Y-%m-%d')
                if end_date:
                    params['maxDate'] = end_date.strftime('%Y-%m-%d')
                    
                response = requests.get(f"{self.base_url}/appointments", auth=self.auth, params=params)
                response.raise_for_status()
                appointments_batch = response.json()
                
                # If no appointments returned, we've reached the end
                if not appointments_batch:
                    break
                
                print(f"Processing batch {page}: {len(appointments_batch)} appointments")
                
                # Process this batch and save to database immediately
                batch_created = 0
                batch_updated = 0
                
                with transaction.atomic():
                    for apt_data in appointments_batch:
                        try:
                            calendar_id_val = str(apt_data.get('calendarID'))
                            appointment_type_id_val = str(apt_data.get('appointmentTypeID'))

                            if not calendar_id_val or not appointment_type_id_val:
                                print(f"Skipping appointment {apt_data.get('id', 'N/A')} due to missing calendarID or appointmentTypeID.")
                                continue

                            calendar = Calendar.objects.get(acuity_calendar_id=calendar_id_val)
                            appointment_type = AppointmentType.objects.get(acuity_type_id=appointment_type_id_val)
                            
                            # Defensive: handle missing or malformed datetime fields
                            start_time, start_err = self._parse_acuity_datetime(apt_data, 'datetime')
                            end_time, end_err = self._parse_acuity_datetime(apt_data, 'endTime')

                            if start_err:
                                print(f"Skipping appointment {apt_data.get('id', 'N/A')} due to start time error: {start_err}")
                                continue
                            if end_err:
                                # We might have a valid start but not a valid end.
                                print(f"Skipping appointment {apt_data.get('id', 'N/A')} due to end time error: {end_err}")
                                continue

                            # Extract processing fee from form data (default to 1.0 if not found)
                            processing_fee = 1.0
                            forms = apt_data.get('forms', [])
                            for form in forms:
                                for field in form.get('values', []):
                                    name = field.get('name', '').lower()
                                    if 'processing fee' in name or 'fee:' in name:
                                        try:
                                            processing_fee = float(field.get('value', 1.0))
                                            # If user enters 0.04, treat as 1.04 (4% fee)
                                            if processing_fee < 2.0:
                                                processing_fee = 1.0 + float(processing_fee)
                                        except Exception:
                                            processing_fee = 1.0
                                        break

                            # Extract color tag from labels
                            color_tag = ''
                            labels = apt_data.get('labels', [])
                            if labels and isinstance(labels, list) and len(labels) > 0:
                                color_tag = labels[0].get('color', '')

                            appointment, created = Appointment.objects.update_or_create(
                                acuity_appointment_id=str(apt_data.get('id', '')),
                                defaults={
                                    'calendar': calendar,
                                    'appointment_type': appointment_type,
                                    'client_name': f"{apt_data.get('firstName', '')} {apt_data.get('lastName', '')}",
                                    'client_email': apt_data.get('email', ''),
                                    'client_phone': apt_data.get('phone', ''),
                                    'start_time': start_time,
                                    'end_time': end_time,
                                    'notes': apt_data.get('notes', ''),
                                    'price': apt_data.get('price', 0),
                                    'status': apt_data.get('status', 'scheduled').lower(),
                                    'form_data': forms,
                                    'processing_fee': processing_fee,
                                    'last_synced': timezone.now(),
                                    'color_tag': color_tag,
                                }
                            )
                            
                            if created:
                                batch_created += 1
                                created_count += 1
                            else:
                                batch_updated += 1
                                updated_count += 1
                            
                            total_processed += 1
                                
                        except (Calendar.DoesNotExist, AppointmentType.DoesNotExist) as e:
                            print(f"Error syncing appointment {apt_data.get('id', 'unknown')}: {e}")
                            continue
                        except Exception as e:
                            import logging
                            logging.exception(f"Unexpected error syncing appointment {apt_data.get('id', 'unknown')}")
                            continue
                
                # Transaction is automatically committed here
                print(f"Batch {page} saved to database: {batch_created} created, {batch_updated} updated")
                
                # Clear the batch from memory
                del appointments_batch
                
                # Move to next page
                page += 1
                
                # Optional: Add a safety limit to prevent infinite loops
                if page > 1000:  # Max 1000 pages (100,000 appointments with batch_size=100)
                    print("Warning: Reached maximum page limit (1000). Some appointments may not be fetched.")
                    break
                    
            except requests.exceptions.RequestException as e:
                print(f"Error fetching appointments page {page}: {e}")
                break
            except Exception as e:
                import logging
                logging.exception(f'Unexpected error in sync_appointments_by_date_range page {page}')
                break
        
        print(f"Date-range sync completed: {created_count} new appointments created, {updated_count} existing appointments updated")
        print(f"Total appointments processed: {total_processed} across {page-1} pages")
        return created_count, updated_count, total_processed

    def get_appointments_count(self, calendar_id=None):
        """Get the total count of appointments from Acuity API"""
        try:
            params = {'max': 1}  # Just get 1 appointment to see total count
            if calendar_id:
                params['calendarID'] = calendar_id
                
            response = requests.get(f"{self.base_url}/appointments", auth=self.auth, params=params)
            response.raise_for_status()
            
            # Check if there's a total count in headers or response
            total_count = response.headers.get('X-Total-Count')
            if total_count:
                return int(total_count)
            
            # If no header, try to estimate from first page
            appointments = response.json()
            if len(appointments) == 0:
                return 0
            elif len(appointments) < 1:
                # If we got less than requested, this might be all appointments
                return len(appointments)
            else:
                # We got a full page, so there are likely more
                return f"At least {len(appointments)} (exact count not available)"
                
        except Exception as e:
            print(f"Error getting appointments count: {e}")
            return "Unknown"

    def get_appointments_count_by_date_range(self, start_date, end_date, calendar_id=None):
        """Get the total count of appointments from Acuity API for a specific date range"""
        try:
            params = {'max': 1}  # Just get 1 appointment to see total count
            if calendar_id:
                params['calendarID'] = calendar_id
            if start_date:
                params['minDate'] = start_date.strftime('%Y-%m-%d')
            if end_date:
                params['maxDate'] = end_date.strftime('%Y-%m-%d')
                
            response = requests.get(f"{self.base_url}/appointments", auth=self.auth, params=params)
            response.raise_for_status()
            
            # Check if there's a total count in headers or response
            total_count = response.headers.get('X-Total-Count')
            if total_count:
                return int(total_count)
            
            # If no header, try to estimate from first page
            appointments = response.json()
            if len(appointments) == 0:
                return 0
            elif len(appointments) < 1:
                # If we got less than requested, this might be all appointments
                return len(appointments)
            else:
                # We got a full page, so there are likely more
                return f"At least {len(appointments)} (exact count not available)"
                
        except Exception as e:
            print(f"Error getting appointments count: {e}")
            return "Unknown"