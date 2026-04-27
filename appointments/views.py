from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import send_mail
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, FormView, ListView, TemplateView, UpdateView, View

from .forms import (
    AppointmentForm,
    CustomerForm,
    PublicAppointmentForm,
    ScheduleBlockForm,
    ServiceForm,
    PublicCancelForm,
    PublicAppointmentLookupForm,
)
from .models import Appointment, BusinessHour, Customer, ScheduleBlock, Service


class ServiceListView(LoginRequiredMixin, ListView):
    # Lists available services

    model = Service
    template_name = "appointments/service_list.html"
    context_object_name = "services"


class ServiceCreateView(LoginRequiredMixin, CreateView):
    # Creates a new service

    model = Service
    form_class = ServiceForm
    template_name = "appointments/service_form.html"
    success_url = reverse_lazy("appointments:service_list")

    def form_valid(self, form):
        messages.success(self.request, "Serviço criado com sucesso.")
        return super().form_valid(form)


class CustomerListView(LoginRequiredMixin, ListView):
    # Lists customers

    model = Customer
    template_name = "appointments/customer_list.html"
    context_object_name = "customers"


class CustomerCreateView(LoginRequiredMixin, CreateView):
    # Creates a new customer

    model = Customer
    form_class = CustomerForm
    template_name = "appointments/customer_form.html"
    success_url = reverse_lazy("appointments:customer_list")

    def form_valid(self, form):
        messages.success(self.request, "Cliente criado com sucesso.")
        return super().form_valid(form)


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


class ScheduleBlockListView(LoginRequiredMixin, ListView):
    # Lists schedule blocks

    model = ScheduleBlock
    template_name = "appointments/schedule_block_list.html"
    context_object_name = "blocks"

    def get_queryset(self):
        return ScheduleBlock.objects.order_by(
            "date",
            "start_time",
        )


class ScheduleBlockCreateView(LoginRequiredMixin, CreateView):
    # Creates a new schedule block

    model = ScheduleBlock
    form_class = ScheduleBlockForm
    template_name = "appointments/schedule_block_form.html"
    success_url = reverse_lazy("appointments:schedule_block_list")

    def form_valid(self, form):
        messages.success(self.request, "Bloqueio criado com sucesso.")
        return super().form_valid(form)


class ScheduleBlockUpdateView(LoginRequiredMixin, UpdateView):
    # Updates an existing schedule block

    model = ScheduleBlock
    form_class = ScheduleBlockForm
    template_name = "appointments/schedule_block_form.html"
    success_url = reverse_lazy("appointments:schedule_block_list")

    def form_valid(self, form):
        messages.success(self.request, "Bloqueio atualizado com sucesso.")
        return super().form_valid(form)


class PublicBookingAvailabilityMixin:
    # Shared availability logic for public booking

    slot_minutes = 30

    def get_available_slots_for(self, service, selected_date):
        # Calculate available slots without using unsaved appointment objects
        business_hour = BusinessHour.objects.filter(
            weekday=selected_date.weekday(),
            is_active=True,
        ).first()

        if not business_hour:
            return []

        now = timezone.localtime()

        current_datetime = datetime.combine(
            selected_date,
            business_hour.start_time,
        )

        business_end_datetime = datetime.combine(
            selected_date,
            business_hour.end_time,
        )

        # If selected date is today, do not show past times
        if selected_date == now.date():
            current_datetime = max(
                current_datetime,
                now.replace(second=0, microsecond=0).replace(tzinfo=None),
            )

            # Round up to the next slot interval
            minute = current_datetime.minute

            if minute % self.slot_minutes != 0:
                minutes_to_add = self.slot_minutes - (minute % self.slot_minutes)
                current_datetime += timedelta(minutes=minutes_to_add)

        appointments = Appointment.objects.filter(
            date=selected_date,
        ).exclude(
            status=Appointment.STATUS_CANCELLED,
        ).select_related(
            "service",
        )

        blocks = [
            block
            for block in ScheduleBlock.objects.filter(is_active=True)
            if block.applies_to_date(selected_date)
        ]

        available_slots = []

        while current_datetime + timedelta(minutes=service.duration_minutes) <= business_end_datetime:
            slot_start = current_datetime
            slot_end = slot_start + timedelta(minutes=service.duration_minutes)

            has_conflict = False

            for appointment in appointments:
                appointment_start = appointment.get_start_datetime()
                appointment_end = appointment.get_end_datetime()

                if slot_start < appointment_end and slot_end > appointment_start:
                    has_conflict = True
                    break

            if not has_conflict:
                for block in blocks:
                    block_start = block.get_start_datetime_for_date(selected_date)
                    block_end = block.get_end_datetime_for_date(selected_date)

                    if slot_start < block_end and slot_end > block_start:
                        has_conflict = True
                        break

            if not has_conflict:
                available_slots.append(
                    {
                        "value": slot_start.strftime("%H:%M"),
                        "label": slot_start.strftime("%H:%M"),
                    }
                )

            current_datetime += timedelta(minutes=self.slot_minutes)

        return available_slots


class PublicAppointmentCreateView(PublicBookingAvailabilityMixin, FormView):
    # Public booking form for customers

    template_name = "appointments/public_appointment_form.html"
    form_class = PublicAppointmentForm
    success_url = reverse_lazy("appointments:public_appointment_success")

    def get_initial(self):
        # Pre-fill form from query string (agenda click)
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

        return initial

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

    def form_valid(self, form):
        # Create appointment safely
        cleaned_data = form.cleaned_data

        service = cleaned_data["service"]
        date = cleaned_data["date"]
        start_time = datetime.strptime(
            cleaned_data["start_time"],
            "%H:%M",
        ).time()

        customer_name = cleaned_data["customer_name"]
        customer_phone = cleaned_data["customer_phone"]
        customer_email = cleaned_data["customer_email"]
        notes = cleaned_data.get("notes")

        with transaction.atomic():
            customer, _ = Customer.objects.get_or_create(
                email=customer_email,
                defaults={
                    "full_name": customer_name,
                    "phone": customer_phone,
                },
            )

            appointment = Appointment.objects.create(
                customer=customer,
                service=service,
                date=date,
                start_time=start_time,
                notes=notes,
                status=Appointment.STATUS_CONFIRMED,
            )

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
        reference_code = form.cleaned_data["reference_code"].strip().upper()

        try:
            appointment = Appointment.objects.get(reference_code=reference_code)
        except Appointment.DoesNotExist:
            form.add_error(
                "reference_code",
                "Código não encontrado."
            )
            return self.form_invalid(form)

        if appointment.status == Appointment.STATUS_CANCELLED:
            form.add_error(
                "reference_code",
                "Esta marcação já foi cancelada."
            )
            return self.form_invalid(form)

        appointment.status = Appointment.STATUS_CANCELLED
        appointment.save(update_fields=["status", "updated_at"])

        self.request.session["cancelled_reference_code"] = appointment.reference_code

        return redirect(
            "appointments:public_cancel_success_with_code",
            reference_code=appointment.reference_code,
        )


class PublicCancelSuccessView(TemplateView):
    # Shows cancellation success

    template_name = "appointments/public_cancel_success.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["reference_code"] = self.kwargs.get(
            "reference_code",
            self.request.session.get("cancelled_reference_code", "N/A"),
        )

        return context   
    

class PublicCancelAppointmentByCodeView(TemplateView):
    # Allows public cancellation using a direct reference code URL

    template_name = "appointments/public_cancel_by_code.html"

    def get_appointment(self):
        # Get appointment by reference code from URL
        reference_code = self.kwargs.get("reference_code", "").strip().upper()

        return Appointment.objects.filter(
            reference_code=reference_code,
        ).select_related(
            "customer",
            "service",
        ).first()

    def get_context_data(self, **kwargs):
        # Add appointment data to template context
        context = super().get_context_data(**kwargs)

        context["appointment"] = self.get_appointment()

        return context

    def post(self, request, *args, **kwargs):
        # Cancel appointment after confirmation
        appointment = self.get_appointment()

        if not appointment:
            messages.error(request, "Marcação não encontrada.")
            return redirect("appointments:public_cancel")

        if appointment.status == Appointment.STATUS_CANCELLED:
            messages.warning(request, "Esta marcação já está cancelada.")
            return redirect("appointments:public_cancel_success")

        appointment.status = Appointment.STATUS_CANCELLED
        appointment.save(update_fields=["status", "updated_at"])

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

        appointment = Appointment.objects.filter(
            reference_code=reference_code,
        ).select_related(
            "customer",
            "service",
        ).first()

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
    

class ScheduleDiagnosticsView(LoginRequiredMixin, TemplateView):
    # Shows detailed diagnostics for available and blocked schedule slots

    template_name = "appointments/schedule_diagnostics.html"

    slot_minutes = 30

    def get_selected_service(self):
        # Get selected service from query string
        service_id = self.request.GET.get("service")

        if not service_id:
            return None

        return Service.objects.filter(pk=service_id).first()

    def get_selected_date(self):
        # Get selected date from query string or use today
        date_value = self.request.GET.get("date")

        if not date_value:
            return timezone.localdate()

        try:
            return datetime.strptime(date_value, "%Y-%m-%d").date()
        except ValueError:
            return timezone.localdate()

    def build_diagnostics(self, service, selected_date):
        # Build detailed schedule diagnostics
        if not service:
            return []

        business_hour = BusinessHour.objects.filter(
            weekday=selected_date.weekday(),
            is_active=True,
        ).first()

        if not business_hour:
            return []

        current_datetime = datetime.combine(
            selected_date,
            business_hour.start_time,
        )

        business_end_datetime = datetime.combine(
            selected_date,
            business_hour.end_time,
        )

        now = timezone.localtime()

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

        diagnostics = []

        while current_datetime < business_end_datetime:
            slot_start = current_datetime
            slot_end = slot_start + timedelta(minutes=service.duration_minutes)

            status = "available"
            reason = "Horário disponível"
            related_object = None

            if slot_end > business_end_datetime:
                status = "blocked"
                reason = "O serviço termina depois do horário de funcionamento."

            elif selected_date == now.date() and slot_start < now.replace(tzinfo=None):
                status = "blocked"
                reason = "Horário já passou."

            else:
                for block in blocks:
                    block_start = block.get_start_datetime_for_date(selected_date)
                    block_end = block.get_end_datetime_for_date(selected_date)

                    if slot_start < block_end and slot_end > block_start:
                        status = "blocked"
                        reason = f"Conflito com bloqueio: {block.title}"
                        related_object = block
                        break

                if status == "available":
                    for appointment in appointments:
                        appointment_start = appointment.get_start_datetime()
                        appointment_end = appointment.get_end_datetime()

                        if slot_start < appointment_end and slot_end > appointment_start:
                            status = "blocked"
                            reason = (
                                f"Conflito com marcação: "
                                f"{appointment.reference_code} - "
                                f"{appointment.customer.full_name}"
                            )
                            related_object = appointment
                            break

            diagnostics.append(
                {
                    "start_time": slot_start.time(),
                    "end_time": slot_end.time(),
                    "status": status,
                    "reason": reason,
                    "related_object": related_object,
                }
            )

            current_datetime += timedelta(minutes=self.slot_minutes)

        return diagnostics

    def get_context_data(self, **kwargs):
        # Add diagnostics data to template context
        context = super().get_context_data(**kwargs)

        selected_service = self.get_selected_service()
        selected_date = self.get_selected_date()

        business_hour = BusinessHour.objects.filter(
            weekday=selected_date.weekday(),
            is_active=True,
        ).first()

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

        diagnostics = self.build_diagnostics(
            selected_service,
            selected_date,
        )

        context["services"] = Service.objects.order_by("name")
        context["selected_service"] = selected_service
        context["selected_date"] = selected_date
        context["business_hour"] = business_hour
        context["appointments"] = appointments
        context["blocks"] = blocks
        context["diagnostics"] = diagnostics

        return context    
    

class PublicVisualScheduleView(PublicBookingAvailabilityMixin, TemplateView):
    # Public visual schedule for customers without login

    template_name = "appointments/public_visual_schedule.html"

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

        return context