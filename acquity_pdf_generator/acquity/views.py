# views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from .models import User, Calendar, UserCalendar, AppointmentType, Appointment, PDFGenerationLog
from .services import AcuityService
from .pdf_generator import PDFGenerator
from datetime import datetime, timedelta
import json
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone
import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

def manage_users(request):
    return HttpResponse("Welcome to the manage users page.")

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid credentials')
    
    return render(request, 'auth/login.html')

@login_required
def dashboard(request):
    """Main dashboard for users to view their calendars and appointments"""
    if request.user.is_superuser:
        # Superuser gets to see everything
        user_calendars = UserCalendar.objects.all().select_related('user', 'calendar')
        all_appointments = Appointment.objects.all()
    else:
        # Regular user sees only their assigned calendars and appointments
        user_calendars = UserCalendar.objects.filter(user=request.user, can_view=True)
        calendar_ids = user_calendars.values_list('calendar__id', flat=True)
        all_appointments = Appointment.objects.filter(calendar__id__in=calendar_ids)

    # The total number of records accessible by the user, before any search filters.
    total_records = all_appointments.count()

    # Apply date filters if present
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    
    if start_date:
        try:
            start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
            all_appointments = all_appointments.filter(start_time__date__gte=start_datetime.date())
        except ValueError:
            start_date = ''
    
    if end_date:
        try:
            end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
            all_appointments = all_appointments.filter(start_time__date__lte=end_datetime.date())
        except ValueError:
            end_date = ''

    # Apply search filter if present
    search_query = request.GET.get('q', '')
    if search_query:
        appointments_to_display = all_appointments.filter(
            Q(client_name__icontains=search_query) |
            Q(client_email__icontains=search_query) |
            Q(appointment_type__name__icontains=search_query)
        )
    else:
        appointments_to_display = all_appointments

    # Pagination for appointments
    paginator = Paginator(appointments_to_display.order_by('start_time'), 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Stats for the cards
    api_status = "Connected"
    
    try:
        # This block will only work if the database migrations have been run.
        if request.user.is_superuser:
            pdfs_generated = PDFGenerationLog.objects.count()
        else:
            pdfs_generated = PDFGenerationLog.objects.filter(generated_by=request.user).count()
        last_sync_obj = PDFGenerationLog.objects.order_by('-generated_at').first()
        last_sync = last_sync_obj.generated_at if last_sync_obj else "N/A"
    except Exception:
        pdfs_generated = 0
        last_sync = "N/A (db schema pending)"

    context = {
        'user_calendars': user_calendars,
        'appointments_page': page_obj,
        'total_records': total_records,
        'api_status': api_status,
        'pdfs_generated': pdfs_generated,
        'last_sync': last_sync,
        'search_query': search_query,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'scheduling/dashboard.html', context)

# @login_required
def appointments_view(request):
    user = request.user
    acuity_service = AcuityService()
    
    # Get user's accessible calendars
    if user.is_superuser:
        accessible_calendars = Calendar.objects.all()
    else:
        accessible_calendars = Calendar.objects.filter(usercalendar__user=user)
    
    selected_calendar_id = request.GET.get('calendar_id')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    appointments = []
    selected_calendar = None
    start_date = None
    end_date = None
    # Validate and parse dates
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        except (ValueError, TypeError):
            messages.error(request, 'Invalid start date format. Please use YYYY-MM-DD.')
            start_date = None
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        except (ValueError, TypeError):
            messages.error(request, 'Invalid end date format. Please use YYYY-MM-DD.')
            end_date = None
    
    if selected_calendar_id:
        try:
            selected_calendar = accessible_calendars.get(id=selected_calendar_id)
            appointments = acuity_service.get_appointments(
                calendar_id=selected_calendar.acuity_calendar_id,
                start_date=start_date,
                end_date=end_date
            )
        except Calendar.DoesNotExist:
            messages.error(request, 'You do not have access to this calendar.')
        except Exception as e:
            import logging
            logging.exception('Unexpected error fetching appointments')
            messages.error(request, f'An error occurred while fetching appointments: {str(e)}')
    
    context = {
        'accessible_calendars': accessible_calendars,
        'selected_calendar': selected_calendar,
        'appointments': appointments,
        'start_date': start_date_str,
        'end_date': end_date_str,
    }
    
    return render(request, 'appointments/list.html', context)

# @login_required
def generate_pdf(request, calendar_id):
    user = request.user
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    # Check access permissions
    if user.is_superuser:
        accessible_calendars = Calendar.objects.all()
    else:
        accessible_calendars = Calendar.objects.filter(usercalendar__user=user)
    
    try:
        calendar = accessible_calendars.get(id=calendar_id)
    except Calendar.DoesNotExist:
        messages.error(request, 'You do not have access to this calendar.')
        return redirect('calendar_appointments', calendar_id=calendar_id)
    
    # Validate and parse dates
    start_date = None
    end_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        except (ValueError, TypeError):
            messages.error(request, 'Invalid start date format. Please use YYYY-MM-DD.')
            return redirect('calendar_appointments', calendar_id=calendar_id)
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        except (ValueError, TypeError):
            messages.error(request, 'Invalid end date format. Please use YYYY-MM-DD.')
            return redirect('calendar_appointments', calendar_id=calendar_id)
    
    # Get appointments
    acuity_service = AcuityService()
    try:
        appointments_data = acuity_service.get_appointments(
        calendar_id=calendar.acuity_calendar_id,
        start_date=start_date,
        end_date=end_date
    )
        print(f"Fetched {len(appointments_data)} appointments for calendar {calendar.name}")
    except Exception as e:
        import logging
        logging.exception('Unexpected error fetching appointments for PDF')
        messages.error(request, f'An error occurred while fetching appointments: {str(e)}')
        return redirect('calendar_appointments', calendar_id=calendar_id)
    
    # Generate PDF
    pdf_generator = PDFGenerator()
    try:
        # Title
        title = Paragraph(f"Appointments Report - {calendar.name}", pdf_generator.title_style)
        elements = [title]
        elements.append(Spacer(1, 20))
        
        pdf_content = pdf_generator.generate_appointment_pdf(appointments_data, calendar.name)
        print(f"PDF generated successfully for calendar {calendar.name}")
    except Exception as e:
        import logging
        logging.exception('Error generating PDF')
        messages.error(request, f'An error occurred while generating the PDF: {str(e)}')
        return redirect('calendar_appointments', calendar_id=calendar_id)
    
    # Return PDF response
    response = HttpResponse(pdf_content, content_type='application/pdf')
    filename = f"appointments_{calendar.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    response['Content-Disposition'] = f'attachment; filename=\"{filename}\"'
    
    return response

# Admin Views
# @login_required
def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.is_superuser == False:
            messages.error(request, 'Access denied. Admin privileges required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper

# @login_required
@admin_required
def manage_users(request):
    users = User.objects.filter(role='user').order_by('-created_at')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create':
            username = request.POST.get('username')
            email = request.POST.get('email')
            password = request.POST.get('password')
            
            if User.objects.filter(username=username).exists():
                messages.error(request, 'Username already exists.')
            else:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    role='user'
                )
                messages.success(request, f'User {username} created successfully.')
        
        elif action == 'delete':
            user_id = request.POST.get('user_id')
            try:
                user = User.objects.get(id=user_id, role='user')
                user.delete()
                messages.success(request, 'User deleted successfully.')
            except User.DoesNotExist:
                messages.error(request, 'User not found.')
        
        return redirect('manage_users')
    
    context = {'users': users}
    return render(request, 'admin/users.html', context)

# @login_required
@admin_required
def manage_calendars(request):
    calendars = Calendar.objects.all().order_by('-created_at')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create':
            name = request.POST.get('name')
            acuity_calendar_id = request.POST.get('acuity_calendar_id')
            description = request.POST.get('description', '')
            
            calendar = Calendar.objects.create(
                name=name,
                acuity_calendar_id=acuity_calendar_id,
                description=description
            )
            messages.success(request, f'Calendar {name} created successfully.')
        
        elif action == 'delete':
            calendar_id = request.POST.get('calendar_id')
            try:
                calendar = Calendar.objects.get(id=calendar_id)
                calendar.delete()
                messages.success(request, 'Calendar deleted successfully.')
            except Calendar.DoesNotExist:
                messages.error(request, 'Calendar not found.')
        
        return redirect('manage_calendars')
    
    context = {'calendars': calendars}
    return render(request, 'admin/calendars.html', context)

# @login_required
@admin_required
def assign_calendars(request):
    users = User.objects.filter(role='user')
    calendars = Calendar.objects.all()
    assignments = UserCalendar.objects.select_related('user', 'calendar').all()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'assign':
            user_id = request.POST.get('user_id')
            calendar_id = request.POST.get('calendar_id')
            
            try:
                user = User.objects.get(id=user_id)
                calendar = Calendar.objects.get(id=calendar_id)
                
                assignment, created = UserCalendar.objects.get_or_create(
                    user=user,
                    calendar=calendar
                )
                
                if created:
                    messages.success(request, f'Calendar {calendar.name} assigned to {user.username}.')
                else:
                    messages.info(request, 'This assignment already exists.')
            except (User.DoesNotExist, Calendar.DoesNotExist):
                messages.error(request, 'Invalid user or calendar.')
        
        elif action == 'unassign':
            assignment_id = request.POST.get('assignment_id')
            try:
                assignment = UserCalendar.objects.get(id=assignment_id)
                assignment.delete()
                messages.success(request, 'Assignment removed successfully.')
            except UserCalendar.DoesNotExist:
                messages.error(request, 'Assignment not found.')
        
        return redirect('assign_calendars')
    
    context = {
        'users': users,
        'calendars': calendars,
        'assignments': assignments,
    }
    return render(request, 'admin/assignments.html', context)

#


# scheduling/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Calendar, UserCalendar, Appointment
from .services import AcuityService
from .pdf_generator import PDFGenerator

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    return render(request, 'scheduling/login.html')

@login_required
def dashboard(request):
    """Main dashboard for users to view their calendars and appointments"""
    if request.user.is_superuser:
        # Superuser gets to see everything
        user_calendars = UserCalendar.objects.all().select_related('user', 'calendar')
        all_appointments = Appointment.objects.all()
    else:
        # Regular user sees only their assigned calendars and appointments
        user_calendars = UserCalendar.objects.filter(user=request.user, can_view=True)
        calendar_ids = user_calendars.values_list('calendar__id', flat=True)
        all_appointments = Appointment.objects.filter(calendar__id__in=calendar_ids).order_by('-start_time')

    # The total number of records accessible by the user, before any search filters.
    total_records = all_appointments.count()

    # Apply date filters if present
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    
    if start_date:
        try:
            start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
            all_appointments = all_appointments.filter(start_time__date__gte=start_datetime.date())
        except ValueError:
            start_date = ''
    
    if end_date:
        try:
            end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
            all_appointments = all_appointments.filter(start_time__date__lte=end_datetime.date())
        except ValueError:
            end_date = ''

    # Apply search filter if present
    search_query = request.GET.get('q', '')
    if search_query:
        appointments_to_display = all_appointments.filter(
            Q(client_name__icontains=search_query) |
            Q(client_email__icontains=search_query) |
            Q(appointment_type__name__icontains=search_query)
        )
    else:
        appointments_to_display = all_appointments

    # Pagination for appointments
    paginator = Paginator(appointments_to_display.order_by('start_time'), 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Stats
    api_status = "Connected" # This would be dynamic in a real scenario
    pdfs_generated = 0 # Placeholder
    last_sync = "N/A" # Placeholder
    
    context = {
        'user_calendars': user_calendars,
        'appointments_page': page_obj,
        'total_records': total_records,
        'api_status': api_status,
        'pdfs_generated': pdfs_generated,
        'last_sync': last_sync,
        'search_query': search_query,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'scheduling/dashboard.html', context)

@login_required
def calendar_appointments(request, calendar_id):
    """View appointments for a specific calendar"""
    if request.user.is_superuser:
        calendar = get_object_or_404(Calendar, id=calendar_id)
    else:
        # Check if user has access to this calendar
        user_calendar = get_object_or_404(UserCalendar, user=request.user, calendar_id=calendar_id, can_view=True)
        calendar = user_calendar.calendar
    
    # Sync appointments before displaying
    acuity_service = AcuityService()
    acuity_service.sync_appointments(calendar_id=calendar.acuity_calendar_id)
    
    # Get appointments
    appointments = Appointment.objects.filter(calendar=calendar).order_by('-start_time')
    
    # Filter by date range if provided
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    print(f"DEBUG: Raw start_date from request: {start_date_str}")
    print(f"DEBUG: Raw end_date from request: {end_date_str}")
    
    # Parse dates for filtering
    start_date_parsed = None
    end_date_parsed = None
    
    if start_date_str:
        try:
            start_date_parsed = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            print(f"DEBUG: Parsed start_date: {start_date_parsed}")
            appointments = appointments.filter(start_time__date__gte=start_date_parsed).order_by('-start_time')
            print(f"DEBUG: Appointments after start_date filter: {appointments.count()}")
        except ValueError as e:
            print(f"DEBUG: Error parsing start_date: {e}")
            pass
    
    if end_date_str:
        try:
            end_date_parsed = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            print(f"DEBUG: Parsed end_date: {end_date_parsed}")
            appointments = appointments.filter(start_time__date__lte=end_date_parsed).order_by('-start_time')
            print(f"DEBUG: Appointments after end_date filter: {appointments.count()}")
        except ValueError as e:
            print(f"DEBUG: Error parsing end_date: {e}")
            pass
    
    print(f"DEBUG: Final appointments count: {appointments.count()}")
    print(f"DEBUG: Context start_date: {start_date_str}")
    print(f"DEBUG: Context end_date: {end_date_str}")
    
    context = {
        'calendar': calendar,
        'appointments': appointments,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'debug': True,  # Enable debug mode for troubleshooting
    }
    return render(request, 'scheduling/calendar_appointments.html', context)

@login_required
def appointment_detail(request, appointment_id):
    """View details of a specific appointment"""
    appointment = get_object_or_404(Appointment, id=appointment_id)
    
    # Check if user has access to this appointment
    if not request.user.is_superuser:
        user_calendars = UserCalendar.objects.filter(
            user=request.user, 
            calendar=appointment.calendar, 
            can_view=True
        )
        if not user_calendars.exists():
            messages.error(request, "You don't have permission to view this appointment.")
            return redirect('dashboard')
    
    context = {
        'appointment': appointment,
    }
    return render(request, 'scheduling/appointment_detail.html', context)

@login_required
def download_pdf(request, appointment_id):
    """Generate and download PDF confirmation for an appointment"""
    appointment = get_object_or_404(Appointment, id=appointment_id)
    
    # Check if user has access to this appointment
    if not request.user.is_superuser:
        user_calendars = UserCalendar.objects.filter(
            user=request.user, 
            calendar=appointment.calendar, 
            can_view=True
        )
        if not user_calendars.exists():
            messages.error(request, "You don't have permission to access this appointment.")
            return redirect('dashboard')
    
    # Generate PDF
    pdf_generator = PDFGenerator()
    pdf_content = pdf_generator.generate_appointment_confirmation(appointment)
    
    # Log the PDF generation event
    PDFGenerationLog.objects.create(appointment=appointment, generated_by=request.user)
    
    # Create response
    response = HttpResponse(pdf_content, content_type='application/pdf')
    # --- Custom filename logic ---
    dt = appointment.start_time
    month = dt.strftime('%B')  # Full month name
    day = dt.strftime('%d')    # Day of month
    time = dt.strftime('%I%M%p').lower()  # 12-hour format, e.g., 0730pm
    name = appointment.client_name.replace(' ', '').replace('.', '')
    # Try to extract state from address in form_data or notes
    state = ''
    address = ''
    if hasattr(appointment, 'form_data') and appointment.form_data:
        for form in appointment.form_data:
            for field in form.get('values', []):
                if 'address' in field.get('name', '').lower():
                    address = field.get('value', '')
    if not address:
        address = getattr(appointment, 'notes', '')
    import re
    match = re.search(r',\s*([A-Z]{2})\s*\d{5}', address)
    if match:
        state = match.group(1)
    filename = f"{month}-{day}-{time}-{name}"
    if state:
        filename += f"-{state}"
    filename += ".pdf"
    response['Content-Disposition'] = f'attachment; filename=\"{filename}\"'
    
    return response

@login_required
def sync_data(request):
    """
    Manually sync data from Acuity.
    Handles both standard browser requests and AJAX requests from the dashboard.
    """
    if not request.user.is_superuser:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': "You don't have permission to sync data."}, status=403)
        messages.error(request, "You don't have permission to sync data.")
        return redirect('dashboard')
    
    try:
        acuity_service = AcuityService()
        acuity_service.sync_calendars()
        acuity_service.sync_appointment_types()
        acuity_service.sync_appointments()
        
        # If the request is from our auto-sync script, return a JSON response
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success', 'message': 'Data synchronized successfully!'})
            
        messages.success(request, "Data synchronized successfully!")
    except Exception as e:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        messages.error(request, f"Error syncing data: {str(e)}")
    
    # Redirect for standard browser requests
    return redirect(request.GET.get('next', 'dashboard'))

def generate_appointment_pdf(self, appointments_data, calendar_name):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, 
                          topMargin=72, bottomMargin=18)
    elements = []
    try:
        # Title
        title = Paragraph(f"Appointments Report - {calendar_name}", self.title_style)
        elements.append(title)
        elements.append(Spacer(1, 20))
        # ... (all other code for PDF generation, indented here) ...
        doc.build(elements)
        pdf_content = buffer.getvalue()
        buffer.close()
        return pdf_content
    except Exception as e:
        import logging
        logging.exception('Error generating appointments PDF')
        buffer.close()
        raise e