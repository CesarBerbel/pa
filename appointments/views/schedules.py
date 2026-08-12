from datetime import datetime, timedelta

from appointments.mixins import InternalAreaRequiredMixin
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View

from appointments.availability import AvailabilityService
from appointments.blocking_services import ScheduleBlockingService
from appointments.selectors import AppointmentSelectors


class DailyAgendaView(InternalAreaRequiredMixin, TemplateView):
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

        context["selected_date"] = selected_date
        context["previous_date"] = selected_date - timedelta(days=1)
        context["next_date"] = selected_date + timedelta(days=1)
        context["appointments"] = AppointmentSelectors.appointments_for_date(
            selected_date
        )
        context["blocks"] = AppointmentSelectors.blocks_for_date(selected_date)

        return context


class VisualScheduleView(InternalAreaRequiredMixin, TemplateView):
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_date = self.get_selected_date()
        business_hour = AvailabilityService.get_business_hour(selected_date)
        full_day_block = AvailabilityService.get_full_day_block_for_date(
            selected_date=selected_date,
            business_hour=business_hour,
        )

        slots = []

        if business_hour and not full_day_block:
            business_hour, slots = AvailabilityService.build_visual_slots(
                selected_date=selected_date,
                slot_minutes=self.slot_minutes,
            )

        context["selected_date"] = selected_date
        context["previous_date"] = selected_date - timedelta(days=1)
        context["next_date"] = selected_date + timedelta(days=1)
        context["business_hour"] = business_hour
        context["full_day_block"] = full_day_block
        context["slots"] = slots

        return context


class VisualScheduleBlockView(InternalAreaRequiredMixin, View):
    # Cria bloqueios a partir dos horários marcados na agenda visual.

    def post(self, request):
        raw_date = request.POST.get("date", "")

        try:
            selected_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "Data inválida para bloqueio.")
            return redirect("appointments:visual_schedule")

        destino = (
            f"{reverse('appointments:visual_schedule')}"
            f"?date={selected_date.strftime('%Y-%m-%d')}"
        )

        result = ScheduleBlockingService.block_slots(
            selected_date=selected_date,
            times=ScheduleBlockingService.parse_slot_times(
                request.POST.getlist("slots")
            ),
            title=request.POST.get("title", ""),
        )

        if result.success:
            messages.success(request, result.message)
        else:
            messages.error(request, result.message)

        return redirect(destino)
