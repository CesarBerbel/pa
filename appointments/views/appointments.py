from django.contrib import messages
from django.db import models
from appointments.mixins import SuperuserRequiredMixin, LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, TemplateView, UpdateView, View

from appointments.audit_services import AppointmentAuditService
from appointments.cancellation_services import AppointmentCancellationService
from appointments.emails import send_appointment_confirmation_email
from appointments.forms import AppointmentCancelForm, AppointmentForm
from appointments.models import Appointment, AppointmentLog, Service


class AppointmentListView(SuperuserRequiredMixin, ListView):
    # Lists appointments with filters and ordering.

    model = Appointment
    template_name = "appointments/appointment_list.html"
    context_object_name = "appointments"

    allowed_orderings = {
        "date_asc": ("date", "start_time"),
        "date_desc": ("-date", "-start_time"),
        "customer_asc": ("customer__full_name", "date", "start_time"),
        "customer_desc": ("-customer__full_name", "date", "start_time"),
        "service_asc": ("service__name", "date", "start_time"),
        "service_desc": ("-service__name", "date", "start_time"),
        "status_asc": ("status", "date", "start_time"),
        "status_desc": ("-status", "date", "start_time"),
        "created_desc": ("-created_at",),
        "created_asc": ("created_at",),
    }

    def get_queryset(self):
        # Apply search, filters and ordering from query string.
        queryset = Appointment.objects.select_related(
            "customer",
            "service",
            "created_by",
        )

        search = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()
        service_id = self.request.GET.get("service", "").strip()
        date_from = self.request.GET.get("date_from", "").strip()
        date_to = self.request.GET.get("date_to", "").strip()
        reminder = self.request.GET.get("reminder", "").strip()
        ordering = self.request.GET.get("ordering", "date_asc").strip()

        if search:
            queryset = queryset.filter(
                models.Q(reference_code__icontains=search)
                | models.Q(customer__full_name__icontains=search)
                | models.Q(customer__email__icontains=search)
                | models.Q(customer__phone__icontains=search)
                | models.Q(service__name__icontains=search)
            )

        if status:
            queryset = queryset.filter(status=status)

        if service_id:
            queryset = queryset.filter(service_id=service_id)

        if date_from:
            queryset = queryset.filter(date__gte=date_from)

        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        if reminder == "24h_sent":
            queryset = queryset.filter(reminder_24h_sent_at__isnull=False)
        elif reminder == "24h_pending":
            queryset = queryset.filter(
                reminder_24h_sent_at__isnull=True,
            ).exclude(
                status__in=[
                    Appointment.STATUS_CANCELLED,
                    Appointment.STATUS_COMPLETED,
                ]
            )
        elif reminder == "2h_sent":
            queryset = queryset.filter(reminder_2h_sent_at__isnull=False)
        elif reminder == "2h_pending":
            queryset = queryset.filter(
                reminder_2h_sent_at__isnull=True,
            ).exclude(
                status__in=[
                    Appointment.STATUS_CANCELLED,
                    Appointment.STATUS_COMPLETED,
                ]
            )

        order_by = self.allowed_orderings.get(
            ordering,
            self.allowed_orderings["date_asc"],
        )

        return queryset.order_by(*order_by)

    def get_context_data(self, **kwargs):
        # Add filter options and selected values to the template.
        context = super().get_context_data(**kwargs)

        context["services"] = Service.objects.order_by("name")
        context["status_choices"] = Appointment.STATUS_CHOICES

        context["filters"] = {
            "q": self.request.GET.get("q", ""),
            "status": self.request.GET.get("status", ""),
            "service": self.request.GET.get("service", ""),
            "date_from": self.request.GET.get("date_from", ""),
            "date_to": self.request.GET.get("date_to", ""),
            "reminder": self.request.GET.get("reminder", ""),
            "ordering": self.request.GET.get("ordering", "date_asc"),
        }

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
    # Confirms an appointment without deleting it.

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
    # Marks an appointment as completed only if it is confirmed.

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
    # Shows appointments for the authenticated customer.

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


class CustomerAppointmentDetailView(LoginRequiredMixin, TemplateView):
    # Shows appointment details for the authenticated customer.

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