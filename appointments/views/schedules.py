from datetime import datetime, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView

from appointments.models import Appointment, BusinessHour, ScheduleBlock


class DailyAgendaView(LoginRequiredMixin, TemplateView):
    # Shows appointments grouped by a selected day

    template_name = "appointments/daily_agenda.html"

    def get_selected_date(self):
        date_param = self.request.GET.get("date")

        if date_param:
            try:
                return timezone.datetime.strptime(date_param, "%Y-%m-%d").date()
            except ValueError:
                return timezone.localdate()

        return timezone.localdate()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        selected_date = self.get_selected_date()

        appointments = Appointment.objects.filter(
            date=selected_date,
        ).select_related(
            "customer",
            "service",
        ).order_by(
            "start_time",
        )

        blocks = [
            block
            for block in ScheduleBlock.objects.filter(is_active=True).order_by("start_time")
            if block.applies_to_date(selected_date)
        ]

        context["selected_date"] = selected_date
        context["previous_date"] = selected_date - timedelta(days=1)
        context["next_date"] = selected_date + timedelta(days=1)
        context["appointments"] = appointments
        context["blocks"] = blocks

        return context


class VisualScheduleView(LoginRequiredMixin, TemplateView):
    # Shows a visual daily schedule with appointments and blocked periods

    template_name = "appointments/visual_schedule.html"

    slot_minutes = 30

    def get_selected_date(self):
        date_param = self.request.GET.get("date")

        if date_param:
            try:
                return datetime.strptime(date_param, "%Y-%m-%d").date()
            except ValueError:
                return timezone.localdate()

        return timezone.localdate()

    def get_business_hour(self, selected_date):
        return BusinessHour.objects.filter(
            weekday=selected_date.weekday(),
            is_active=True,
        ).first()

    def build_slots(self, selected_date, business_hour):
        if not business_hour:
            return []

        current_datetime = datetime.combine(
            selected_date,
            business_hour.start_time,
        )

        end_datetime = datetime.combine(
            selected_date,
            business_hour.end_time,
        )

        appointments = Appointment.objects.filter(
            date=selected_date,
        ).exclude(
            status=Appointment.STATUS_CANCELLED,
        ).select_related(
            "customer",
            "service",
        ).order_by(
            "start_time",
        )

        blocks = [
            block
            for block in ScheduleBlock.objects.filter(is_active=True).order_by("start_time")
            if block.applies_to_date(selected_date)
        ]

        slots = []

        while current_datetime < end_datetime:
            slot_start = current_datetime

            slot_data = {
                "time": slot_start.time(),
                "time_value": slot_start.strftime("%H:%M"),
                "appointment": None,
                "block": None,
                "is_appointment_start": False,
                "is_inside_appointment": False,
                "is_block_start": False,
                "is_inside_block": False,
                "block_slots": 1,
                "block_height": 70,
            }

            for block in blocks:
                block_start = block.get_start_datetime_for_date(selected_date)
                block_end = block.get_end_datetime_for_date(selected_date)

                if slot_start == block_start or (
                    block.is_full_day and slot_start == current_datetime
                ):
                    duration_minutes = int(
                        (block_end - block_start).total_seconds() / 60
                    )

                    if block.is_full_day:
                        duration_minutes = int(
                            (end_datetime - current_datetime).total_seconds() / 60
                        )

                    block_slots = max(1, duration_minutes // self.slot_minutes)

                    if duration_minutes % self.slot_minutes:
                        block_slots += 1

                    slot_data["block"] = block
                    slot_data["is_block_start"] = True
                    slot_data["is_inside_block"] = True
                    slot_data["block_slots"] = block_slots
                    slot_data["block_height"] = block_slots * 70
                    break

                if slot_start > block_start and slot_start < block_end:
                    slot_data["block"] = block
                    slot_data["is_inside_block"] = True
                    break

            if not slot_data["block"]:
                for appointment in appointments:
                    appointment_start = appointment.get_start_datetime()
                    appointment_end = appointment.get_end_datetime()

                    if slot_start == appointment_start:
                        duration_minutes = appointment.service.duration_minutes
                        block_slots = max(1, duration_minutes // self.slot_minutes)

                        if duration_minutes % self.slot_minutes:
                            block_slots += 1

                        slot_data["appointment"] = appointment
                        slot_data["is_appointment_start"] = True
                        slot_data["is_inside_appointment"] = True
                        slot_data["block_slots"] = block_slots
                        slot_data["block_height"] = block_slots * 70
                        break

                    if slot_start > appointment_start and slot_start < appointment_end:
                        slot_data["appointment"] = appointment
                        slot_data["is_inside_appointment"] = True
                        break

            slots.append(slot_data)

            current_datetime += timedelta(minutes=self.slot_minutes)

        return slots

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        selected_date = self.get_selected_date()
        business_hour = self.get_business_hour(selected_date)
        slots = self.build_slots(selected_date, business_hour)

        context["selected_date"] = selected_date
        context["previous_date"] = selected_date - timedelta(days=1)
        context["next_date"] = selected_date + timedelta(days=1)
        context["business_hour"] = business_hour
        context["slots"] = slots

        return context