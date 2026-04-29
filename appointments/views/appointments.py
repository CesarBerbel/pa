from django.contrib import messages
from appointments.mixins import SuperuserRequiredMixin, LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView, UpdateView, View
from appointments.emails import send_appointment_confirmation_email
from appointments.forms import AppointmentForm, AppointmentCancelForm
from appointments.audit_services import AppointmentAuditService
from appointments.models import Appointment, AppointmentLog
from appointments.cancellation_services import AppointmentCancellationService

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
        AppointmentAuditService.log(
            appointment=form.instance,
            action=AppointmentLog.ACTION_UPDATE,
            user=self.request.user,
            description="Appointment updated.",
        )
        return super().form_valid(form)


class AppointmentCancelView(SuperuserRequiredMixin, UpdateView):
    # Shows an internal cancellation form and cancels an appointment with a required reason.

    model = Appointment
    form_class = AppointmentCancelForm
    template_name = "appointments/appointment_cancel_form.html"
    success_url = reverse_lazy("appointments:appointment_list")

    def get_form_kwargs(self):
        # Remove instance because AppointmentCancelForm is a regular Form, not a ModelForm.
        kwargs = super().get_form_kwargs()
        kwargs.pop("instance", None)
        return kwargs

    def dispatch(self, request, *args, **kwargs):
        # Prevent opening the cancellation form for appointments that cannot be cancelled.
        appointment = self.get_object()

        if appointment.status == Appointment.STATUS_CANCELLED:
            messages.warning(
                request,
                "Esta marcação já está cancelada.",
            )
            return redirect("appointments:appointment_list")

        if appointment.status == Appointment.STATUS_COMPLETED:
            messages.error(
                request,
                "Marcações concluídas não podem ser canceladas.",
            )
            return redirect("appointments:appointment_list")

        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        # Pre-fill the reason if the appointment already has one.
        initial = super().get_initial()
        initial["cancellation_reason"] = self.object.cancellation_reason
        return initial

    def form_valid(self, form):
        # Cancel the appointment using centralized business rules.
        appointment = self.get_object()

        result = AppointmentCancellationService.cancel(
            appointment=appointment,
            user=self.request.user,
            cancellation_reason=form.cleaned_data["cancellation_reason"],
        )

        if result.success:
            messages.success(self.request, result.message)
            return redirect(self.success_url)

        form.add_error(None, result.message)
        return self.form_invalid(form)


class AppointmentConfirmView(SuperuserRequiredMixin, View):
    # Confirms an appointment without deleting it

    def post(self, request, pk):
        appointment = Appointment.objects.get(pk=pk)

        if appointment.status != Appointment.STATUS_CANCELLED:
            appointment.status = Appointment.STATUS_CONFIRMED
            appointment.save(update_fields=["status", "updated_at"])
            messages.success(request, "Marcação confirmada com sucesso.")
            AppointmentAuditService.log(
                appointment=appointment,
                action=AppointmentLog.ACTION_CONFIRM,
                user=request.user,
                description="Appointment confirmed.",
            )
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

        AppointmentAuditService.log(
            appointment=appointment,
            action=AppointmentLog.ACTION_COMPLETE,
            user=request.user,
            description="Appointment completed.",
        )

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