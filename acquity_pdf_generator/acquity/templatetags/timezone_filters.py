from django import template
from django.utils import timezone
from acquity.utils import format_time_in_timezone, django_format_to_python_format

register = template.Library()

@register.filter
def timezone_time(value, format_string="g:i A"):
    """
    Display time in the original timezone of the appointment.
    Usage: {{ appointment|timezone_time:"g:i A" }}
    """
    if not value:
        return ""
    
    # If this is an appointment object, get its original_timezone
    if hasattr(value, 'original_timezone') and value.original_timezone:
        try:
            # Convert Django format to Python format
            python_format = django_format_to_python_format(format_string)
            return format_time_in_timezone(value.start_time, value.original_timezone, python_format)
        except:
            pass
    
    # Fallback to default time formatting
    try:
        python_format = django_format_to_python_format(format_string)
        return value.start_time.strftime(python_format)
    except:
        return value.start_time.strftime('%I:%M %p')  # Default fallback

@register.filter
def timezone_field_time(appointment, field_name):
    """
    Display a specific datetime field in the original timezone of the appointment.
    Usage: {{ appointment|timezone_field_time:"end_time" }}
    """
    if not appointment or not hasattr(appointment, 'original_timezone') or not appointment.original_timezone:
        return ""
    
    # Get the field value
    field_value = getattr(appointment, field_name, None)
    if not field_value:
        return ""
    
    try:
        # Convert Django format to Python format
        python_format = django_format_to_python_format("g:i A")
        return format_time_in_timezone(field_value, appointment.original_timezone, python_format)
    except:
        # Fallback to default time formatting
        try:
            return field_value.strftime('%I:%M %p')
        except:
            return ""

@register.filter
def timezone_datetime(value, format_string="M d, Y, g:i A"):
    """
    Display date and time in the original timezone of the appointment.
    Usage: {{ appointment|timezone_datetime:"M d, Y, g:i A" }}
    """
    if not value:
        return ""
    
    # If this is an appointment object, get its original_timezone
    if hasattr(value, 'original_timezone') and value.original_timezone:
        try:
            # Convert Django format to Python format
            python_format = django_format_to_python_format(format_string)
            return format_time_in_timezone(value.start_time, value.original_timezone, python_format)
        except:
            pass
    
    # Fallback to default datetime formatting
    try:
        python_format = django_format_to_python_format(format_string)
        return value.start_time.strftime(python_format)
    except:
        return value.start_time.strftime('%b %d, %Y, %I:%M %p')  # Default fallback

@register.filter
def timezone_date(value, format_string="M d, Y"):
    """
    Display date in the original timezone of the appointment.
    Usage: {{ appointment|timezone_date:"M d, Y" }}
    """
    if not value:
        return ""
    
    # If this is an appointment object, get its original_timezone
    if hasattr(value, 'original_timezone') and value.original_timezone:
        try:
            # Convert Django format to Python format
            python_format = django_format_to_python_format(format_string)
            return format_time_in_timezone(value.start_time, value.original_timezone, python_format)
        except:
            pass
    
    # Fallback to default date formatting
    try:
        python_format = django_format_to_python_format(format_string)
        return value.start_time.strftime(python_format)
    except:
        return value.start_time.strftime('%b %d, %Y')  # Default fallback 