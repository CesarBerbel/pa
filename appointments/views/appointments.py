from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView, View

from appointments.forms import AppointmentForm
from appointments.models import Appointment


class AppointmentListView(LoginRequiredMixin, ListView):
    # Lists appointments

    model = Appointment
    template_name = "appointments/appointment_list.html"
    context_object_name = "appointments"

    def get_queryset(self):
        return Appointment.objects.select_related(
            "customer",
            "service",
            "created_by",
        ).order_by(
            "date",
            "start_time",
        )


class AppointmentCreateView(LoginRequiredMixin, CreateView):
    # Creates a new appointment

    model = Appointment
    form_class = AppointmentForm
    template_name = "appointments/appointment_form.html"
    success_url = reverse_lazy("appointments:appointment_list")

    def get_initial(self):
        initial = super().get_initial()

        date = self.request.GET.get("date")
        start_time = self.request.GET.get("start_time")

        if date:
            initial["date"] = date

        if start_time:
            initial["start_time"] = start_time

        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Marcação criada com sucesso.")
        return super().form_valid(form)


class AppointmentUpdateView(LoginRequiredMixin, UpdateView):
    # Edits an existing appointment only if it is not completed

    model = Appointment
    form_class = AppointmentForm
    template_name = "appointments/appointment_form.html"
    success_url = reverse_lazy("appointments:appointment_list")

    def dispatch(self, request, *args, **kwargs):
        # Prevent editing completed appointments even by direct URL access
        appointment = self.get_object()

        if appointment.status == Appointment.STATUS_COMPLETED:
            messages.error(
                request,
                "Marcações concluídas não podem ser editadas.",
            )
            return redirect("appointments:appointment_list")

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Marcação atualizada com sucesso.")
        return super().form_valid(form)


class AppointmentCancelView(LoginRequiredMixin, View):
    # Cancels an appointment without deleting it from the database

    def post(self, request, pk):
        appointment = Appointment.objects.get(pk=pk)

        appointment.status = Appointment.STATUS_CANCELLED
        appointment.save(update_fields=["status", "updated_at"])

        messages.success(request, "Marcação cancelada com sucesso.")

        return redirect("appointments:appointment_list")


class AppointmentConfirmView(LoginRequiredMixin, View):
    # Confirms an appointment without deleting it

    def post(self, request, pk):
        appointment = Appointment.objects.get(pk=pk)

        if appointment.status != Appointment.STATUS_CANCELLED:
            appointment.status = Appointment.STATUS_CONFIRMED
            appointment.save(update_fields=["status", "updated_at"])
            messages.success(request, "Marcação confirmada com sucesso.")

        return redirect("appointments:appointment_list")


class AppointmentCompleteView(LoginRequiredMixin, View):
    # Marks an appointment as completed only if it is confirmed

    def post(self, request, pk):
        appointment = Appointment.objects.get(pk=pk)

        if appointment.status != Appointment.STATUS_CONFIRMED:
            messages.error(
                request,
                "Só é possível concluir marcações confirmadas.",
            )
            return redirect("appointments:appointment_list")

        appointment.status = Appointment.STATUS_COMPLETED
        appointment.save(update_fields=["status", "updated_at"])

        messages.success(request, "Marcação concluída com sucesso.")

        return redirect("appointments:appointment_list")