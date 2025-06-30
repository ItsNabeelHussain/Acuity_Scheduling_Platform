# scheduling/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Calendar, UserCalendar, AppointmentType, Appointment, PricingSetting

# Customize User Admin
class UserCalendarInline(admin.TabularInline):
    model = UserCalendar
    extra = 1

class UserAdmin(BaseUserAdmin):
    inlines = (UserCalendarInline,)

admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(Calendar)
class CalendarAdmin(admin.ModelAdmin):
    list_display = ['name', 'acuity_calendar_id', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'acuity_calendar_id']

@admin.register(UserCalendar)
class UserCalendarAdmin(admin.ModelAdmin):
    list_display = ['user', 'calendar', 'can_view', 'assigned_at']
    list_filter = ['can_view', 'assigned_at', 'calendar']
    search_fields = ['user__username', 'calendar__name']

@admin.register(AppointmentType)
class AppointmentTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'acuity_type_id', 'duration', 'price', 'is_active']
    list_filter = ['is_active', 'duration']
    search_fields = ['name', 'acuity_type_id']

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['client_name', 'calendar', 'appointment_type', 'start_time', 'status', 'price', 'display_form_data']
    list_filter = ['status', 'calendar', 'appointment_type', 'start_time']
    search_fields = ['client_name', 'client_email', 'acuity_appointment_id']
    readonly_fields = ['acuity_appointment_id', 'created_at','last_synced', 'form_data']
    date_hierarchy = 'start_time'

    def display_form_data(self, obj):
        """
        Creates a string representation of the form data for the admin list display.
        """
        if not obj.form_data:
            return "No form data"
        
        # In Acuity, form_data is a list of dictionaries.
        # Let's show the first few fields to keep the list view clean.
        items = []
        for form in obj.form_data:
            for field in form.get('values', []):
                items.append(f"{field.get('name', 'N/A')}: {field.get('value', 'N/A')}")
        
        return " | ".join(items[:3]) + ('...' if len(items) > 3 else '')

    display_form_data.short_description = "Form Data"

admin.site.register(PricingSetting)
