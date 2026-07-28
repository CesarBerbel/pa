from django.conf import settings
from django.contrib import messages
from appointments.mixins import SuperuserRequiredMixin, LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, TemplateView, UpdateView, View

from appointments.audit_services import AppointmentAuditService
from appointments.cancellation_services import AppointmentCancellationService
from appointments.forms import AppointmentCancelForm, AppointmentForm
from appointments.models import Appointment, AppointmentLog, Service
from appointments.selectors import AppointmentFilters, AppointmentSelectors
from appointments.use_cases import ConfirmAppointmentUseCase, CompleteAppointmentUseCase
from notifications.whatsapp import WhatsAppAppointmentNotificationService


class AppointmentListView(SuperuserRequiredMixin, ListView):
    # Lists appointments with filters and ordering.

    model = Appointment
    template_name = "appointments/appointment_list.html"
    context_object_name = "appointments"

    def get_filters(self):
        return AppointmentFilters.from_querydict(self.request.GET)

    def get_queryset(self):
        # Delegate filtering/query composition to the application selector layer.
        return AppointmentSelectors.list_appointments(self.get_filters())

    def get_context_data(self, **kwargs):
        # Add filter options and selected values to the template.
        context = super().get_context_data(**kwargs)

        context["services"] = Service.objects.order_by("name")
        context["status_choices"] = Appointment.STATUS_CHOICES

        context["filters"] = self.get_filters().as_template_context()

        return context


class AppointmentCreateView(SuperuserRequiredMixin, CreateView):
    # Creates a new appointment.

    model = Appointment
    form_class = AppointmentForm
    template_name = "appointments/appointment_form.html"
    success_url = reverse_lazy("appointments:appointment_list")

    def get_initial(self):
        # Pre-fill appointment date and time using query params or current local datetime.
        initial = super().get_initial()

        current_datetime = timezone.localtime()

        date = self.request.GET.get("date")
        start_time = self.request.GET.get("start_time")

        if date:
            initial["date"] = date
        else:
            initial["date"] = current_datetime.date().isoformat()

        if start_time:
            initial["start_time"] = start_time
        else:
            initial["start_time"] = current_datetime.strftime("%H:%M")

        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Marcação criada com sucesso.")
        return super().form_valid(form)


class AppointmentUpdateView(SuperuserRequiredMixin, UpdateView):
    # Edits an existing appointment only if it is not completed.

    model = Appointment
    form_class = AppointmentForm
    template_name = "appointments/appointment_form.html"
    success_url = reverse_lazy("appointments:appointment_list")

    def dispatch(self, request, *args, **kwargs):
        # Validate access before loading the appointment, otherwise anonymous
        # users could infer appointment state from the redirect and message.
        permission_denied_response = self.get_permission_denied_response()

        if permission_denied_response:
            return permission_denied_response

        # Prevent editing completed appointments even by direct URL access.
        appointment = self.get_object()

        if appointment.status == Appointment.STATUS_COMPLETED:
            messages.error(
                request,
                "Marcações concluídas não podem ser editadas.",
            )
            return redirect("appointments:appointment_list")

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        previous_status = Appointment.objects.values_list(
            "status",
            flat=True,
        ).get(pk=self.object.pk)

        response = super().form_valid(form)

        AppointmentAuditService.log(
            appointment=self.object,
            action=AppointmentLog.ACTION_UPDATE,
            user=self.request.user,
            description="Appointment updated.",
        )

        was_confirmed_now = (
            previous_status != Appointment.STATUS_CONFIRMED
            and self.object.status == Appointment.STATUS_CONFIRMED
        )

        if was_confirmed_now:
            AppointmentAuditService.log(
                appointment=self.object,
                action=AppointmentLog.ACTION_CONFIRM,
                user=self.request.user,
                description="Appointment confirmed by status update.",
            )

            whatsapp_result = WhatsAppAppointmentNotificationService.send_confirmation(
                self.object
            )

            if whatsapp_result.success:
                should_show_whatsapp_message = (
                    not whatsapp_result.skipped or settings.WHATSAPP_CLOUD_API_ENABLED
                )

                if should_show_whatsapp_message:
                    messages.success(
                        self.request,
                        f"Marcação atualizada com sucesso. {whatsapp_result.message}",
                    )
                else:
                    messages.success(
                        self.request,
                        "Marcação atualizada com sucesso.",
                    )
            else:
                messages.warning(
                    self.request,
                    "Marcação atualizada e confirmada, mas não foi possível "
                    f"enviar o WhatsApp: {whatsapp_result.message}",
                )
        else:
            messages.success(self.request, "Marcação atualizada com sucesso.")

        return response


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
        # Validate access before loading the appointment, otherwise anonymous
        # users could infer appointment state from the redirect and message.
        permission_denied_response = self.get_permission_denied_response()

        if permission_denied_response:
            return permission_denied_response

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
    # Confirms an appointment without deleting it.

    def post(self, request, pk):
        appointment = Appointment.objects.get(pk=pk)

        result = ConfirmAppointmentUseCase.execute(
            appointment=appointment,
            user=request.user,
        )

        if result.success:
            messages.success(request, result.message)
        else:
            messages.error(request, result.message)

        return redirect("appointments:appointment_list")


class AppointmentCompleteView(SuperuserRequiredMixin, View):
    # Marks an appointment as completed only if it is confirmed.

    def post(self, request, pk):
        appointment = Appointment.objects.get(pk=pk)

        result = CompleteAppointmentUseCase.execute(
            appointment=appointment,
            user=request.user,
        )

        if result.success:
            messages.success(request, result.message)
        else:
            messages.error(request, result.message)

        return redirect("appointments:appointment_list")


class CustomerAppointmentsView(LoginRequiredMixin, TemplateView):
    # Shows appointments for the authenticated customer.

    template_name = "appointments/customer_appointments.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        customer = getattr(self.request.user, "customer_profile", None)

        context["appointments"] = AppointmentSelectors.customer_appointments(customer)

        return context


class CustomerAppointmentDetailView(LoginRequiredMixin, TemplateView):
    # Shows appointment details for the authenticated customer.

    template_name = "appointments/customer_appointment_detail.html"

    def get_appointment(self):
        customer = getattr(self.request.user, "customer_profile", None)

        if not customer:
            return None

        reference_code = self.kwargs.get("reference_code", "").strip().upper()

        return AppointmentSelectors.customer_appointment_by_reference(
            customer=customer,
            reference_code=reference_code,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["appointment"] = self.get_appointment()
        return context
