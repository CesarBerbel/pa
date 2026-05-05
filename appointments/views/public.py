from django.core import signing
from datetime import datetime, timedelta
from appointments.cancellation_services import AppointmentCancellationService
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import FormView, TemplateView, View
from appointments.forms import (
    PublicAppointmentForm,
    PublicAppointmentLookupForm,
    PublicCancelForm,
)
from appointments.models import Appointment, Service
from appointments.customer_services import find_or_create_customer
from appointments.appointment_services import AppointmentService
from appointments.availability import AvailabilityService


class PublicBookingAvailabilityMixin:
    # Shared availability logic for public booking

    slot_minutes = 30

    def get_available_slots_for(self, service, selected_date):
        # Delegate public slot generation to the domain availability service.
        return AvailabilityService.get_available_slots(
            service=service,
            selected_date=selected_date,
        )


class PublicAppointmentCreateView(PublicBookingAvailabilityMixin, FormView):
    # Public booking form for customers

    template_name = "appointments/public_appointment_form.html"
    form_class = PublicAppointmentForm
    success_url = reverse_lazy("appointments:public_appointment_success")

    def get_initial(self):
        initial = super().get_initial()

        service_id = self.request.GET.get("service")
        date_value = self.request.GET.get("date")
        start_time_value = self.request.GET.get("start_time")

        if service_id:
            initial["service"] = service_id

        if date_value:
            initial["date"] = date_value
        else:
            initial["date"] = timezone.localdate()

        if start_time_value:
            initial["start_time"] = start_time_value

        if self.request.user.is_authenticated:
            customer = getattr(self.request.user, "customer_profile", None)

            if customer:
                initial["customer_name"] = customer.full_name
                initial["customer_phone"] = customer.phone
                initial["customer_email"] = customer.email
            else:
                initial["customer_email"] = self.request.user.email

        return initial

    def dispatch(self, request, *args, **kwargs):
        if request.method == "GET":
            service = request.GET.get("service")
            date = request.GET.get("date")
            start_time = request.GET.get("start_time")

            if not (service and date and start_time):
                return redirect("appointments:public_visual_schedule")

        if request.method == "POST":
            service = request.POST.get("service")
            date = request.POST.get("date")
            start_time = request.POST.get("start_time")

            if not (service and date and start_time):
                return redirect("appointments:public_visual_schedule")

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        # Detect if the booking came from the public visual schedule
        context = super().get_context_data(**kwargs)

        is_locked_from_agenda = bool(
            self.request.GET.get("service")
            and self.request.GET.get("date")
            and self.request.GET.get("start_time")
        )

        if self.request.POST.get("locked_from_agenda") == "1":
            is_locked_from_agenda = True

        context["is_locked_from_agenda"] = is_locked_from_agenda

        return context

    def is_selected_slot_available(self, service, date, start_time):
        available_slots = self.get_available_slots_for(
            service=service,
            selected_date=date,
        )

        return any(slot["value"] == start_time for slot in available_slots)

    def form_valid(self, form):
        # Create appointment safely
        cleaned_data = form.cleaned_data

        service = cleaned_data["service"]
        date = cleaned_data["date"]
        start_time = datetime.strptime(
            cleaned_data["start_time"],
            "%H:%M",
        ).time()

        start_time_value = start_time.strftime("%H:%M")

        if not self.is_selected_slot_available(
            service=service,
            date=date,
            start_time=start_time_value,
        ):
            messages.error(
                self.request,
                "Este horário já não está disponível. Escolha outro horário na agenda.",
            )

            return redirect(
                f"{reverse_lazy('appointments:public_visual_schedule')}?service={service.id}&date={date.strftime('%Y-%m-%d')}"
            )

        customer_name = cleaned_data["customer_name"]
        customer_phone = cleaned_data["customer_phone"]
        customer_email = cleaned_data["customer_email"]
        notes = cleaned_data.get("notes")

        with transaction.atomic():
            customer = find_or_create_customer(
                name=customer_name,
                phone=customer_phone,
                email=customer_email,
            )

            result = AppointmentService.create_appointment(
                customer=customer,
                service=service,
                date=date,
                start_time=start_time,
                notes=notes,
                status=Appointment.STATUS_SCHEDULED,
                send_email=True,
            )

            if not result.success:
                messages.error(
                    self.request,
                    result.message
                    or "Este horário já não está disponível. Escolha outro.",
                )

                return redirect(
                    f"{reverse_lazy('appointments:public_visual_schedule')}?service={service.id}&date={date.strftime('%Y-%m-%d')}"
                )

            appointment = result.appointment

        self.request.session["last_reference_code"] = appointment.reference_code

        return super().form_valid(form)


class PublicAvailableSlotsView(PublicBookingAvailabilityMixin, View):
    # Returns available public booking slots as JSON

    def get(self, request):
        service_id = request.GET.get("service")
        date_value = request.GET.get("date")

        if not service_id or not date_value:
            return JsonResponse({"slots": []})

        service = Service.objects.filter(
            pk=service_id,
            is_active=True,
        ).first()

        if not service:
            return JsonResponse({"slots": []})

        try:
            selected_date = datetime.strptime(date_value, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"slots": []})

        slots = self.get_available_slots_for(service, selected_date)

        return JsonResponse({"slots": slots})


class PublicAppointmentSuccessView(TemplateView):
    # Public appointment success page

    template_name = "appointments/public_appointment_success.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["reference_code"] = self.request.session.get(
            "last_reference_code",
            "N/A",
        )

        return context


class PublicCancelAppointmentView(FormView):
    # Allows public cancellation by reference code

    template_name = "appointments/public_cancel_form.html"
    form_class = PublicCancelForm
    success_url = reverse_lazy("appointments:public_cancel_success")

    def form_valid(self, form):
        # Cancel a public appointment by reference code using centralized business rules.
        reference_code = form.cleaned_data["reference_code"].strip().upper()

        appointment = (
            Appointment.objects.filter(
                reference_code=reference_code,
            )
            .select_related(
                "customer",
                "service",
            )
            .first()
        )

        result = AppointmentCancellationService.cancel(
            appointment=appointment,
            user=self.request.user,
            cancellation_reason=form.cleaned_data["cancellation_reason"],
        )

        if not result.success:
            form.add_error("reference_code", result.message)
            return self.form_invalid(form)

        self.request.session["cancelled_reference_code"] = appointment.reference_code

        return redirect(
            "appointments:public_cancel_success_with_code",
            reference_code=appointment.reference_code,
        )


class PublicCancelSuccessView(TemplateView):
    # Shows cancellation success

    template_name = "appointments/public_cancel_success.html"

    def get_context_data(self, **kwargs):
        # Add cancelled appointment data to show cancellation reason and timestamp.
        context = super().get_context_data(**kwargs)

        reference_code = self.kwargs.get(
            "reference_code",
            self.request.session.get("cancelled_reference_code", "N/A"),
        )

        appointment = (
            Appointment.objects.filter(
                reference_code=reference_code,
            )
            .select_related(
                "customer",
                "service",
            )
            .first()
        )

        context["reference_code"] = reference_code
        context["appointment"] = appointment

        return context


class PublicCancelAppointmentByCodeView(TemplateView):
    # Allows public cancellation using a direct reference code URL

    template_name = "appointments/public_cancel_by_code.html"

    def get_appointment(self):
        # Get appointment by reference code from URL
        reference_code = self.kwargs.get("reference_code", "").strip().upper()

        return (
            Appointment.objects.filter(
                reference_code=reference_code,
            )
            .select_related(
                "customer",
                "service",
            )
            .first()
        )

    def get_context_data(self, **kwargs):
        # Add appointment data to template context
        context = super().get_context_data(**kwargs)

        context["appointment"] = self.get_appointment()

        return context

    def post(self, request, *args, **kwargs):
        # Cancel appointment after confirmation using centralized business rules.
        appointment = self.get_appointment()

        cancellation_reason = request.POST.get("cancellation_reason", "").strip()

        result = AppointmentCancellationService.cancel(
            appointment=appointment,
            user=request.user,
            cancellation_reason=cancellation_reason,
        )

        if not cancellation_reason:
            messages.error(request, "Informe o motivo do cancelamento.")
            return redirect(
                "appointments:public_cancel_by_code",
                reference_code=appointment.reference_code,
            )

        if not result.success:
            messages.error(request, result.message)
            return redirect("appointments:public_appointment_lookup")

        request.session["cancelled_reference_code"] = appointment.reference_code

        return redirect(
            "appointments:public_cancel_success_with_code",
            reference_code=appointment.reference_code,
        )


class PublicAppointmentLookupView(FormView):
    # Allows customers to search an appointment by reference code

    template_name = "appointments/public_appointment_lookup.html"
    form_class = PublicAppointmentLookupForm

    def form_valid(self, form):
        # Search appointment by reference code
        reference_code = form.cleaned_data["reference_code"]

        appointment = (
            Appointment.objects.filter(
                reference_code=reference_code,
            )
            .select_related(
                "customer",
                "service",
            )
            .first()
        )

        if not appointment:
            form.add_error(
                "reference_code",
                "Não encontramos nenhuma marcação com este código.",
            )
            return self.form_invalid(form)

        return self.render_to_response(
            self.get_context_data(
                form=form,
                appointment=appointment,
            )
        )


class PublicVisualScheduleView(PublicBookingAvailabilityMixin, TemplateView):
    # Public visual schedule for customers without login

    template_name = "appointments/public_visual_schedule.html"

    def get_week_days(self, selected_date):
        # Build a practical 7-day navigation starting from the selected week
        start_of_week = selected_date - timedelta(days=selected_date.weekday())

        week_days = []

        for index in range(7):
            current_date = start_of_week + timedelta(days=index)

            week_days.append(
                {
                    "date": current_date,
                    "weekday": current_date.strftime("%a"),
                    "day": current_date.strftime("%d"),
                    "month": current_date.strftime("%b"),
                    "is_selected": current_date == selected_date,
                }
            )

        return week_days

    def get_selected_service(self):
        # Get selected service from query string
        service_id = self.request.GET.get("service")

        if not service_id:
            return Service.objects.filter(is_active=True).order_by("name").first()

        return Service.objects.filter(
            pk=service_id,
            is_active=True,
        ).first()

    def get_selected_date(self):
        # Get selected date from query string or use today
        date_value = self.request.GET.get("date")

        if not date_value:
            return timezone.localdate()

        try:
            return datetime.strptime(date_value, "%Y-%m-%d").date()
        except ValueError:
            return timezone.localdate()

    def get_context_data(self, **kwargs):
        # Add public visual schedule data to context
        context = super().get_context_data(**kwargs)

        selected_service = self.get_selected_service()
        selected_date = self.get_selected_date()

        slots = []

        if selected_service:
            slots = self.get_available_slots_for(
                selected_service,
                selected_date,
            )

        context["services"] = Service.objects.filter(
            is_active=True,
        ).order_by("name")

        context["selected_service"] = selected_service
        context["selected_date"] = selected_date
        context["slots"] = slots
        context["week_days"] = self.get_week_days(selected_date)

        return context

    from django.core import signing


class PublicAppointmentMagicView(TemplateView):
    template_name = "appointments/public_appointment_lookup.html"

    def get(self, request, *args, **kwargs):
        token = self.kwargs.get("token")

        try:
            payload = signing.loads(
                token,
                salt="appointment-magic-link",
                max_age=60 * 60 * 24 * 7,
            )
        except signing.SignatureExpired:
            messages.error(request, "Este link expirou.")
            return redirect("appointments:public_appointment_lookup")
        except signing.BadSignature:
            messages.error(request, "Link inválido.")
            return redirect("appointments:public_appointment_lookup")

        appointment = (
            Appointment.objects.filter(
                reference_code=payload.get("reference_code"),
            )
            .select_related("customer", "service")
            .first()
        )

        if not appointment:
            messages.error(request, "Marcação não encontrada.")
            return redirect("appointments:public_appointment_lookup")

        if appointment.status == Appointment.STATUS_CANCELLED:
            messages.error(request, "Esta marcação foi cancelada.")
            return redirect("appointments:public_appointment_lookup")

        if appointment.updated_at.isoformat() != payload.get("updated_at"):
            messages.error(request, "Este link já não é válido.")
            return redirect("appointments:public_appointment_lookup")

        return self.render_to_response(
            self.get_context_data(
                appointment=appointment,
                form=PublicAppointmentLookupForm(
                    initial={"reference_code": appointment.reference_code}
                ),
            )
        )
