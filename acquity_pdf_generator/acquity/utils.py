def get_form_field(forms, possible_names):
    """
    Extracts the value for any of the possible field names from Acuity form data.
    - forms: list of form dicts (from Acuity API or DB)
    - possible_names: list of str, possible field names (case-insensitive, partial match allowed)
    """
    for form in forms or []:
        for field in form.get('values', []):
            field_name = field.get('name', '').strip().lower()
            for name in possible_names:
                if name.lower() in field_name:
                    return field.get('value')
    return None


def convert_to_local_time(utc_time, timezone_str):
    """
    Convert a UTC datetime to the specified local timezone.
    
    Args:
        utc_time: datetime object (assumed to be in UTC)
        timezone_str: string representation of timezone (e.g., 'America/New_York')
    
    Returns:
        datetime object in the specified timezone, or original time if conversion fails
    """
    try:
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from backports.zoneinfo import ZoneInfo
            
        if timezone_str and utc_time:
            target_tz = ZoneInfo(timezone_str)
            return utc_time.astimezone(target_tz)
    except Exception:
        pass
    return utc_time


def format_time_in_timezone(dt, timezone_str, format_str='%A, %B %d, %Y at %I:%M %p'):
    """
    Format a datetime in the specified timezone.
    
    Args:
        dt: datetime object (assumed to be in UTC)
        timezone_str: string representation of timezone
        format_str: format string for strftime
    
    Returns:
        formatted string in the specified timezone, or 'N/A' if conversion fails
    """
    try:
        local_time = convert_to_local_time(dt, timezone_str)
        if local_time:
            return local_time.strftime(format_str)
    except Exception:
        pass
    return 'N/A' 