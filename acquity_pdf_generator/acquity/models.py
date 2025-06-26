from django.db import models
# from django.contrib.auth.models import User
from django.utils import timezone
# from django.contrib.auth import get_user_model
from django.contrib.auth.models import User

class Calendar(models.Model):
    name = models.CharField(max_length=200)
    acuity_calendar_id = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

class UserCalendar(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE)  
    can_view = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'calendar']

    def __str__(self):
        return f"{self.user.username} - {self.calendar.name}"

class AppointmentType(models.Model):
    name = models.CharField(max_length=200)
    acuity_type_id = models.CharField(max_length=50, unique=True)
    duration = models.IntegerField(help_text="Duration in minutes")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} (${self.price})"

class Appointment(models.Model):
    acuity_appointment_id = models.CharField(max_length=50, unique=True)
    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE)
    appointment_type = models.ForeignKey(AppointmentType, on_delete=models.CASCADE)
    
    # Client Information
    client_name = models.CharField(max_length=200)
    client_email = models.EmailField()
    client_phone = models.CharField(max_length=20, blank=True)
    
    # Appointment Details
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    notes = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Status
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    
    # Custom form data from Acuity
    form_data = models.JSONField(default=dict, blank=True)

    # Processing fee multiplier (e.g., 1.04 for 4% fee)
    processing_fee = models.FloatField(default=1.0, help_text="Multiplier for processing fee (e.g., 1.04 for 4% fee)")
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.client_name} - {self.start_time.strftime('%Y-%m-%d %H:%M')}"

    class Meta:
        ordering = ['-start_time']

class PDFGenerationLog(models.Model):
    """Logs each time a PDF is generated for an appointment."""
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"PDF for Appointment {self.appointment.id} generated at {self.generated_at}"
