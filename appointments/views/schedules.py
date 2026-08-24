from datetime import datetime, timedelta

from appointments.mixins import InternalAreaRequiredMixin
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView, UpdateView, View

from appointments.availability import AvailabilityService
from appointments.blocking_services import ScheduleBlockingService
from appointments.forms import SchedulingSettingForm
from appointments.models import SchedulingSetting
from appointments.selectors import AppointmentSelectors
from appointments.weekly_schedule import build_week, day_agenda, week_start
from appointments.monthly_schedule import build_month


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


class WeeklyScheduleView(InternalAreaRequiredMixin, TemplateView):
    """A semana inteira em grelha, como se lê um calendário.

    É a vista por omissão da agenda interna: numa semana vê-se onde há espaço,
    que é a pergunta que se faz a uma agenda. A vista de dia continua a um
    clique, e é lá que estão as ações sobre cada marcação e o bloqueio de
    horários — coisas que não cabem numa coluna de um sétimo do ecrã.
    """

    template_name = "appointments/weekly_schedule.html"

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
        inicio = week_start(selected_date)

        semana = build_week(selected_date)

        context["week"] = semana

        # O dia que o telemóvel mostra: o escolhido, ou hoje quando a semana
        # aberta é a de hoje.
        escolhido = next(
            (dia for dia in semana.days if dia.date == selected_date),
            semana.days[0],
        )

        context["selected_day"] = escolhido
        context["day_rows"] = day_agenda(escolhido)
        context["week_start"] = inicio
        context["week_end"] = inicio + timedelta(days=6)
        context["previous_week"] = inicio - timedelta(days=7)
        context["next_week"] = inicio + timedelta(days=7)
        context["today"] = timezone.localdate()
        context["selected_date"] = selected_date

        return context


class MonthlyScheduleView(InternalAreaRequiredMixin, TemplateView):
    """O mês inteiro, com quem vem em cada dia.

    A semana responde a "onde há espaço"; o mês responde a "como está o mês".
    Por isso mostra nomes e não horas livres: numa grelha de trinta dias, o
    que se procura é o desenho do mês — os dias cheios, os vazios, e quem
    está marcado onde.
    """

    template_name = "appointments/monthly_schedule.html"

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

        context["month"] = build_month(selected_date)
        context["selected_date"] = selected_date
        context["today"] = timezone.localdate()

        return context


class VisualScheduleView(InternalAreaRequiredMixin, TemplateView):
    # Shows a visual daily schedule with appointments and blocked periods

    template_name = "appointments/visual_schedule.html"

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

        # Com o dia inteiro bloqueado a grelha continua escondida, mas os
        # encaixes que lá foram postos de propósito têm de aparecer — senão
        # existem sem que ninguém os veja.
        business_hour, slots = AvailabilityService.build_visual_slots(
            selected_date=selected_date,
            appointments_only=bool(full_day_block),
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
            notes=request.POST.get("notes", ""),
        )

        if result.success:
            messages.success(request, result.message)
        else:
            messages.error(request, result.message)

        return redirect(destino)


class SchedulingSettingView(InternalAreaRequiredMixin, UpdateView):
    """As regras de agenda, num sítio só.

    O que aqui se mexe muda o que a agenda desenha e o que o site aceita — por
    isso o ecrã diz, ao lado de cada campo, o que muda quando o valor muda.
    """

    model = SchedulingSetting
    form_class = SchedulingSettingForm
    template_name = "appointments/scheduling_setting_form.html"
    success_url = reverse_lazy("appointments:scheduling_setting")

    def get_object(self, queryset=None):
        return SchedulingSetting.load()

    def form_valid(self, form):
        form.instance.updated_by = self.request.user

        resposta = super().form_valid(form)

        messages.success(self.request, "Regras de agenda atualizadas.")

        return resposta
