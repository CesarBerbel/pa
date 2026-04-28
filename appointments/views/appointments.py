from django.contrib import messages
from appointments.mixins import SuperuserRequiredMixin, LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView, UpdateView, View
from appointments.emails import send_appointment_confirmation_email, send_appointment_cancelled_email
from appointments.forms import AppointmentForm
from appointments.models import Appointment

class AppointmentListView(SuperuserRequiredMixin, ListView):
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


class AppointmentCreateView(SuperuserRequiredMixin, CreateView):
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


class AppointmentUpdateView(SuperuserRequiredMixin, UpdateView):
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


class AppointmentCancelView(SuperuserRequiredMixin, View):
    # Cancels an appointment without deleting it from the database

    def post(self, request, pk):
        appointment = Appointment.objects.get(pk=pk)

        appointment.status = Appointment.STATUS_CANCELLED
        appointment.save(update_fields=["status", "updated_at"])

        send_appointment_cancelled_email(appointment)

        messages.success(request, "Marcação cancelada com sucesso.")

        return redirect("appointments:appointment_list")


class AppointmentConfirmView(SuperuserRequiredMixin, View):
    # Confirms an appointment without deleting it

    def post(self, request, pk):
        appointment = Appointment.objects.get(pk=pk)

        if appointment.status != Appointment.STATUS_CANCELLED:
            appointment.status = Appointment.STATUS_CONFIRMED
            appointment.save(update_fields=["status", "updated_at"])
            messages.success(request, "Marcação confirmada com sucesso.")
            send_appointment_confirmation_email(appointment)
        return redirect("appointments:appointment_list")


class AppointmentCompleteView(SuperuserRequiredMixin, View):
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
    
class CustomerAppointmentsView(LoginRequiredMixin, TemplateView):
    template_name = "appointments/customer_appointments.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        customer = getattr(self.request.user, "customer_profile", None)

        appointments = []

        if customer:
            appointments = Appointment.objects.filter(
                customer=customer,
            ).select_related(
                "service",
            ).order_by("-date", "-start_time")

        context["appointments"] = appointments

        return context    
    
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView


class CustomerAppointmentDetailView(LoginRequiredMixin, TemplateView):
    template_name = "appointments/customer_appointment_detail.html"

    def get_appointment(self):
        customer = getattr(self.request.user, "customer_profile", None)

        if not customer:
            return None

        reference_code = self.kwargs.get("reference_code", "").strip().upper()

        return Appointment.objects.filter(
            customer=customer,
            reference_code=reference_code,
        ).select_related(
            "service",
            "customer",
        ).first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["appointment"] = self.get_appointment()
        return context    