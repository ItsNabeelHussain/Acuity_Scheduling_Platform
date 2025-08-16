#!/usr/bin/env python
"""
Test script to verify date filtering logic
"""
import os
import sys
import django
from datetime import datetime, date

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'acquity_pdf_generator.settings')
django.setup()

from acquity.models import Appointment, Calendar

def test_date_filtering():
    """Test the date filtering logic"""
    print("Testing date filtering logic...")
    
    # Get all calendars
    calendars = Calendar.objects.all()
    if not calendars.exists():
        print("No calendars found in database")
        return
    
    calendar = calendars.first()
    print(f"Using calendar: {calendar.name}")
    
    # Get all appointments for this calendar
    appointments = Appointment.objects.filter(calendar=calendar).order_by('-start_time')
    total_appointments = appointments.count()
    print(f"Total appointments: {total_appointments}")
    
    if total_appointments == 0:
        print("No appointments found to test filtering")
        return
    
    # Show first few appointments
    print("\nFirst 5 appointments:")
    for i, apt in enumerate(appointments[:5]):
        print(f"  {i+1}. {apt.client_name} - {apt.start_time} (date: {apt.start_time.date()})")
    
    # Test date filtering
    test_start_date = date(2024, 1, 1)
    test_end_date = date(2024, 12, 31)
    
    print(f"\nTesting filter: start_date >= {test_start_date}, end_date <= {test_end_date}")
    
    # Apply start date filter
    filtered_by_start = appointments.filter(start_time__date__gte=test_start_date)
    print(f"Appointments after start_date filter: {filtered_by_start.count()}")
    
    # Apply end date filter
    filtered_by_end = appointments.filter(start_time__date__lte=test_end_date)
    print(f"Appointments after end_date filter: {filtered_by_end.count()}")
    
    # Apply both filters
    filtered_both = appointments.filter(
        start_time__date__gte=test_start_date,
        start_time__date__lte=test_end_date
    )
    print(f"Appointments after both filters: {filtered_both.count()}")
    
    # Test with specific date range
    specific_start = date(2024, 6, 1)
    specific_end = date(2024, 6, 30)
    print(f"\nTesting specific range: {specific_start} to {specific_end}")
    
    specific_filtered = appointments.filter(
        start_time__date__gte=specific_start,
        start_time__date__lte=specific_end
    )
    print(f"Appointments in specific range: {specific_filtered.count()}")
    
    if specific_filtered.exists():
        print("Sample appointments in range:")
        for apt in specific_filtered[:3]:
            print(f"  - {apt.client_name}: {apt.start_time}")

if __name__ == "__main__":
    test_date_filtering() 
 