# scheduling/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('calendar/<int:calendar_id>/', views.calendar_appointments, name='calendar_appointments'),
    path('calendar/<int:calendar_id>/export-pdf/', views.generate_pdf, name='generate_pdf'),
    path('appointment/<int:appointment_id>/', views.appointment_detail, name='appointment_detail'),
    path('appointment/<int:appointment_id>/pdf/', views.download_pdf, name='download_pdf'),
    path('sync/', views.sync_data, name='sync_data'),
    path('admin/assign-calendars/', views.assign_calendars, name='assign_calendars'),
] 