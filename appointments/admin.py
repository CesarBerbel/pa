from django import forms

from .models import Appointment, Customer, ScheduleBlock, Service


class ServiceForm(forms.ModelForm):
    # Form used to create and edit services

    class Meta:
        model = Service
        fields = [
            "name",
            "description",
            "duration_minutes",
            "price",
            "is_active",
        ]


class CustomerForm(forms.ModelForm):
    # Form used to create and edit customers

    class Meta:
        model = Customer
        fields = [
            "full_name",
            "email",
            "phone",
        ]


class AppointmentForm(forms.ModelForm):
    # Form used to create and edit appointments

    class Meta:
        model = Appointment
        fields = [
            "customer",
            "service",
            "date",
            "start_time",
            "status",
            "notes",
        ]
        widgets = {
            "date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
            "start_time": forms.TimeInput(
                attrs={
                    "type": "time",
                }
            ),
        }


class ScheduleBlockForm(forms.ModelForm):
    # Form used to create schedule blocks

    class Meta:
        model = ScheduleBlock
        fields = [
            "title",
            "block_type",
            "date",
            "start_time",
            "end_time",
            "is_full_day",
            "is_active",
            "notes",
        ]
        widgets = {
            "date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
            "start_time": forms.TimeInput(
                attrs={
                    "type": "time",
                }
            ),
            "end_time": forms.TimeInput(
                attrs={
                    "type": "time",
                }
            ),
        }