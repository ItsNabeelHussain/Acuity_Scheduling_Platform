# scheduling/models.py

# scheduling/services.py
import requests
from requests.auth import HTTPBasicAuth
from django.conf import settings
from django.utils import timezone
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    # Fallback for older Python versions
    try:
        from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    except ImportError:
        # Ultimate fallback - create a simple UTC timezone
        class SimpleUTC:
            def __init__(self):
                self.utcoffset = timedelta(0)
                self.dst = timedelta(0)
                self.name = 'UTC'
                self.tzname = lambda dt: 'UTC'
        
        ZoneInfo = lambda x: SimpleUTC()
        ZoneInfoNotFoundError = Exception

from .models import Calendar, AppointmentType, Appointment
from django.db import transaction
from acquity.utils import get_form_field
from acquity.openai_utils import extract_guest_counts_with_gpt

def safe_convert_to_utc(dt_with_tz, original_tz):
    """
    Safely convert a datetime to UTC, with fallback handling for various edge cases.
    
    Args:
        dt_with_tz: datetime object with timezone info
        original_tz: the original timezone object
    
    Returns:
        tuple: (utc_datetime, success_flag)
    """
    try:
        # Try to convert to UTC
        utc_dt = dt_with_tz.astimezone(ZoneInfo('UTC'))
        return utc_dt, True
    except Exception as e:
        print(f"Warning: Could not convert to UTC: {e}")
        try:
            # Fallback: try to manually adjust the time
            if hasattr(original_tz, 'utcoffset'):
                offset = original_tz.utcoffset(dt_with_tz)
                if offset:
                    utc_dt = dt_with_tz - offset
                    utc_dt = utc_dt.replace(tzinfo=ZoneInfo('UTC'))
                    return utc_dt, True
        except Exception as fallback_e:
            print(f"Fallback UTC conversion also failed: {fallback_e}")
        
        # Ultimate fallback: return original time with warning
        print(f"Using original time for appointment due to timezone conversion failure")
        return dt_with_tz, False


def debug_timezone_parsing(datetime_str, appointment_id):
    """
    Debug function to help troubleshoot timezone parsing issues.
    
    Args:
        datetime_str: the datetime string from Acuity API
        appointment_id: the appointment ID for debugging
    """
    print(f"=== Timezone Debug for Appointment {appointment_id} ===")
    print(f"Raw datetime string: {datetime_str}")
    print(f"String length: {len(datetime_str) if datetime_str else 0}")
    print(f"Contains 'T': {'T' in datetime_str if datetime_str else False}")
    print(f"Ends with 'Z': {datetime_str.endswith('Z') if datetime_str else False}")
    
    if datetime_str and len(datetime_str) > 4:
        print(f"Last 5 characters: {datetime_str[-5:]}")
        print(f"Last character: {datetime_str[-1]}")
        print(f"Second to last character: {datetime_str[-2]}")
        print(f"Third to last character: {datetime_str[-3]}")
        print(f"Fourth to last character: {datetime_str[-4]}")
        print(f"Fifth to last character: {datetime_str[-5]}")
    
    print("=" * 50)


def extract_timezone_from_datetime(datetime_str):
    """
    Extract timezone information from a datetime string.
    
    Args:
        datetime_str: the datetime string from Acuity API
    
    Returns:
        string: timezone name or 'UTC' if not found
    """
    if not datetime_str:
        return 'UTC'
    
    try:
        # Handle Z suffix (UTC)
        if datetime_str.endswith('Z'):
            return 'UTC'
        
        # Handle timezone offset patterns
        if 'T' in datetime_str and len(datetime_str) > 4:
            # Look for timezone offset at the end
            if datetime_str[-5] in ('+', '-'):
                offset = datetime_str[-5:]
                # Map common US timezone offsets
                if offset == '-0500':
                    return 'America/New_York'  # EST
                elif offset == '-0400':
                    return 'America/New_York'  # EDT
                elif offset == '-0800':
                    return 'America/Los_Angeles'  # PST
                elif offset == '-0700':
                    return 'America/Los_Angeles'  # PDT
                elif offset == '-0600':
                    return 'America/Chicago'  # CST
                elif offset == '-0500':
                    return 'America/Chicago'  # CDT
                elif offset == '-0700':
                    return 'America/Denver'  # MST
                elif offset == '-0600':
                    return 'America/Denver'  # MDT
                elif offset == '-0900':
                    return 'America/Anchorage'  # AKST
                elif offset == '-0800':
                    return 'America/Anchorage'  # AKDT
                elif offset == '-1000':
                    return 'Pacific/Honolulu'  # HST
                else:
                    # For other offsets, try to create a timezone name
                    try:
                        hours = int(offset[1:3])
                        minutes = int(offset[3:5])
                        if offset[0] == '-':
                            return f"UTC-{hours:02d}:{minutes:02d}"
                        else:
                            return f"UTC+{hours:02d}:{minutes:02d}"
                    except:
                        return 'UTC'
        
        # If no timezone info found, return UTC
        return 'UTC'
        
    except Exception as e:
        print(f"Error extracting timezone from datetime string: {e}")
        return 'UTC'


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
        
        IMPORTANT: All times are converted to UTC for storage but preserve original timezone info.
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
                
                # Parse the datetime with timezone info
                dt_with_tz = datetime.fromisoformat(time_str)
                
                # Convert to UTC for storage while preserving original timezone
                if dt_with_tz.tzinfo is not None:
                    # Store the original timezone info for display purposes
                    original_tz = dt_with_tz.tzinfo
                    # Convert to UTC for database storage using safe conversion
                    utc_dt, success = safe_convert_to_utc(dt_with_tz, original_tz)
                    # Return the UTC time - the timezone info will be stored separately in the database
                    return utc_dt, None
                else:
                    # No timezone info, assume it's in the client's timezone
                    # We'll need to get this from the appointment data
                    return dt_with_tz, None
                    
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
                        dt_with_tz = naive_dt.replace(tzinfo=tz)
                        # Convert to UTC for storage using safe conversion
                        utc_dt, success = safe_convert_to_utc(dt_with_tz, tz)
                        # Return the UTC time - the timezone info will be stored separately in the database
                        return utc_dt, None
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
        
        # Calculate date range: yesterday to 3 weeks (21 days) in the future
        end_date = datetime.now() + timedelta(days=21)
        start_date = datetime.now() - timedelta(days=1)
        
        print(f"Starting sync with batch size: {batch_size}")
        print(f"Calendar ID filter: {calendar_id}")
        print(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} (last 21 days)")
        
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
                        params = {'page': page, 'max': 2000, 'calendarID': cal_id, 'canceled': 'all'}
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
                        new_objs = []
                        update_objs = []
                        batch_ids = [str(apt.get('id')) for apt in appointments_batch]
                        existing_appointments = Appointment.objects.filter(acuity_appointment_id__in=batch_ids)
                        existing_map = {a.acuity_appointment_id: a for a in existing_appointments}
                        for apt_data in appointments_batch:
                            try:
                                calendar_obj = Calendar.objects.get(acuity_calendar_id=cal_id)
                                appointment_type_id_val = str(apt_data.get('appointmentTypeID'))
                                appointment_type = AppointmentType.objects.get(acuity_type_id=appointment_type_id_val)
                                start_time, start_err = self._parse_acuity_datetime(apt_data, 'datetime')
                                end_time, end_err = self._parse_acuity_datetime(apt_data, 'endTime')
                                if start_err or end_err:
                                    continue
                                processing_fee = 0.0
                                forms = apt_data.get('forms', [])
                                for form in forms:
                                    for field in form.get('values', []):
                                        name = field.get('name', '').lower()
                                        if 'processing fee' in name or 'fee:' in name:
                                            try:
                                                processing_fee = float(field.get('value', 0.0))
                                            except Exception:
                                                processing_fee = 0.0
                                            break
                                color_tag = ''
                                labels = apt_data.get('labels', [])
                                if labels and isinstance(labels, list) and len(labels) > 0:
                                    color_tag = labels[0].get('color', '')
                                
                                # Extract timezone information
                                timezone_str = apt_data.get('timezone', '')
                                if not timezone_str:
                                    # Try to get timezone from the datetime string if available
                                    if 'T' in apt_data.get('datetime', ''):
                                        dt_str = apt_data.get('datetime', '')
                                        # Debug timezone parsing for troubleshooting (commented out for production)
                                        # debug_timezone_parsing(dt_str, apt_data.get('id', 'unknown'))
                                        # Use the new robust timezone extraction function
                                        timezone_str = extract_timezone_from_datetime(dt_str)
                                    else:
                                        timezone_str = 'UTC'
                                
                                acuity_id = str(apt_data.get('id', ''))
                                if acuity_id in existing_map:
                                    # Update existing
                                    appt = existing_map[acuity_id]
                                    appt.calendar = calendar_obj
                                    appt.appointment_type = appointment_type
                                    appt.client_name = f"{apt_data.get('firstName', '')} {apt_data.get('lastName', '')}"
                                    appt.client_email = apt_data.get('email', '')
                                    appt.client_phone = apt_data.get('phone', '')
                                    appt.start_time = start_time
                                    appt.end_time = end_time
                                    appt.notes = apt_data.get('notes', '')
                                    appt.price = apt_data.get('price', 0)
                                    appt.status = apt_data.get('status', 'scheduled').lower()
                                    appt.form_data = forms
                                    appt.processing_fee = processing_fee
                                    appt.original_timezone = timezone_str
                                    appt.last_synced = timezone.now()
                                    appt.color_tag = color_tag
                                    update_objs.append(appt)
                                    batch_updated += 1
                                    updated_count += 1
                                else:
                                    # New object
                                    appt = Appointment(
                                        acuity_appointment_id=acuity_id,
                                        calendar=calendar_obj,
                                        appointment_type=appointment_type,
                                        client_name=f"{apt_data.get('firstName', '')} {apt_data.get('lastName', '')}",
                                        client_email=apt_data.get('email', ''),
                                        client_phone=apt_data.get('phone', ''),
                                        start_time=start_time,
                                        end_time=end_time,
                                        notes=apt_data.get('notes', ''),
                                        price=apt_data.get('price', 0),
                                        status=apt_data.get('status', 'scheduled').lower(),
                                        form_data=forms,
                                        processing_fee=processing_fee,
                                        original_timezone=timezone_str,
                                        last_synced=timezone.now(),
                                        color_tag=color_tag,
                                    )
                                    new_objs.append(appt)
                                    batch_created += 1
                                    created_count += 1
                            except Exception as e:
                                import logging
                                logging.exception(f"Unexpected error syncing appointment {apt_data.get('id', 'unknown')}")
                                continue
                        # Bulk create and update
                        if new_objs:
                            Appointment.objects.bulk_create(new_objs, batch_size=2000)
                        if update_objs:
                            Appointment.objects.bulk_update(update_objs, [
                                'calendar', 'appointment_type', 'client_name', 'client_email', 'client_phone',
                                'start_time', 'end_time', 'notes', 'price', 'status', 'form_data',
                                'processing_fee', 'original_timezone', 'last_synced', 'color_tag'
                            ], batch_size=2000)
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

                            # Extract processing fee from form data (default to 0.0 if not found)
                            forms = apt_data.get('forms', [])
                            processing_fee = get_form_field(forms, ['processing fee', 'fee:'])
                            if processing_fee is not None:
                                try:
                                    processing_fee = float(processing_fee)
                                except Exception:
                                    processing_fee = 0.0
                            else:
                                processing_fee = 0.0

                            # Extract color tag from labels
                            color_tag = ''
                            labels = apt_data.get('labels', [])
                            if labels and isinstance(labels, list) and len(labels) > 0:
                                color_tag = labels[0].get('color', '')

                            # Extract timezone information
                            timezone_str = apt_data.get('timezone', '')
                            if not timezone_str:
                                # Try to get timezone from the datetime string if available
                                if 'T' in apt_data.get('datetime', ''):
                                    dt_str = apt_data.get('datetime', '')
                                    # Debug timezone parsing for troubleshooting (commented out for production)
                                    # debug_timezone_parsing(dt_str, apt_data.get('id', 'unknown'))
                                    # Use the new robust timezone extraction function
                                    timezone_str = extract_timezone_from_datetime(dt_str)
                                else:
                                    timezone_str = 'UTC'

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
                                    'original_timezone': timezone_str,
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
            return len(appointments)
            
        except requests.exceptions.RequestException as e:
            print(f"Error getting appointments count: {e}")
            return 0
        except Exception as e:
            import logging
            logging.exception('Unexpected error getting appointments count')
            return 0

    def get_appointment_by_id(self, appointment_id):
        """
        Fetch a single appointment by ID from Acuity API.
        This is useful for updating existing appointments with correct timezone info.
        
        Args:
            appointment_id: The Acuity appointment ID
            
        Returns:
            dict: Appointment data from Acuity, or None if not found
        """
        try:
            response = requests.get(f"{self.base_url}/appointments/{appointment_id}", auth=self.auth)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching appointment {appointment_id}: {e}")
            return None
        except Exception as e:
            import logging
            logging.exception(f'Unexpected error fetching appointment {appointment_id}')
            return None

    def update_existing_appointment_timezone(self, appointment):
        """
        Update an existing appointment with correct timezone information from Acuity.
        
        Args:
            appointment: Django Appointment model instance
            
        Returns:
            bool: True if updated successfully, False otherwise
        """
        try:
            # Fetch fresh data from Acuity
            acuity_data = self.get_appointment_by_id(appointment.acuity_appointment_id)
            if not acuity_data:
                return False
            
            # Extract timezone information
            timezone_str = acuity_data.get('timezone', '')
            if not timezone_str:
                # Try to get timezone from the datetime string if available
                if 'T' in acuity_data.get('datetime', ''):
                    dt_str = acuity_data.get('datetime', '')
                    timezone_str = extract_timezone_from_datetime(dt_str)
                else:
                    timezone_str = 'America/New_York'  # Default fallback
            
            # Update the appointment
            appointment.original_timezone = timezone_str
            appointment.last_synced = timezone.now()
            appointment.save(update_fields=['original_timezone', 'last_synced'])
            
            print(f"Updated appointment {appointment.acuity_appointment_id} with timezone: {timezone_str}")
            return True
            
        except Exception as e:
            import logging
            logging.exception(f'Error updating appointment {appointment.acuity_appointment_id} timezone')
            return False