from django.core import signing
from datetime import datetime, timedelta
from appointments.cancellation_services import AppointmentCancellationService
from django.contrib import messages
from django.db import transaction
from django.db.models import Prefetch
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
from appointments.models import (
    Appointment,
    AppointmentLog,
    BusinessHour,
    Service,
    ServiceCategory,
)
from appointments.customer_services import find_or_create_customer
from appointments.lookup_services import PublicAppointmentLookupService
from appointments.appointment_services import AppointmentService
from appointments.availability import AvailabilityService


class PublicBookingAvailabilityMixin:
    # Shared availability logic for public booking

    slot_minutes = 30

    def get_available_slots_for(self, service, selected_date):
        # Só os horários livres. Usado na validação da submissão.
        return AvailabilityService.get_public_available_slots(
            service=service,
            selected_date=selected_date,
        )

    def get_public_slot_grid(self, service, selected_date):
        # Grelha completa mostrada à cliente: futuros, livres e ocupados.
        return AvailabilityService.build_public_slots(
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
        if not AvailabilityService.public_slot_is_bookable(
            selected_date=date,
            start_time_value=start_time,
        ):
            return False

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
                origin=Appointment.ORIGIN_PUBLIC,
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

        service = (
            Service.objects.filter(
                pk=service_id,
                is_active=True,
                category__is_active=True,
                category__is_coming_soon=False,
            )
            .select_related("category")
            .first()
        )

        if not service:
            return JsonResponse({"slots": []})

        try:
            selected_date = datetime.strptime(date_value, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"slots": []})

        with AvailabilityService.batch():
            slots = self.get_public_slot_grid(service, selected_date)
            availability_status = AvailabilityService.get_availability_status(
                service,
                selected_date,
                public_safe=True,
            )

        return JsonResponse(
            {"slots": slots, "availability_status": availability_status}
        )


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
            source=AppointmentLog.SOURCE_PUBLIC,
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
            source=AppointmentLog.SOURCE_PUBLIC,
        )

        if not cancellation_reason:
            messages.error(request, "Indique o motivo do cancelamento.")
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


class PublicAppointmentByCodeView(FormView):
    """A marcação aberta direto pelo código, sem ninguém ter de o escrever.

    É para onde aponta o link que segue nas mensagens de WhatsApp. Não usa o
    link assinado dos emails de propósito: esse leva o `updated_at` no token e
    deixa de funcionar assim que a marcação muda — bastava a profissional
    confirmar o pedido para o link que a cliente tinha recebido morrer. Uma
    mensagem de WhatsApp fica na conversa e é reaberta dias depois, muitas
    vezes já com a marcação alterada, e o link tem de continuar a servir.

    O código é a credencial, como já é para cancelar em `/cancelar/<código>/`.
    Mostrar a marcação é menos do que isso permite fazer.
    """

    template_name = "appointments/public_appointment_lookup.html"
    form_class = PublicAppointmentLookupForm

    def get_appointment(self):
        reference_code = self.kwargs.get("reference_code", "").strip().upper()

        return (
            Appointment.objects.filter(reference_code=reference_code)
            .select_related("customer", "service")
            .first()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        appointment = self.get_appointment()

        if appointment:
            context["appointment"] = appointment
            context["form"] = PublicAppointmentLookupForm(
                initial={"reference_code": appointment.reference_code}
            )
        else:
            # Sem marcação fica a página de consulta normal, com o aviso. Um
            # código antigo ou mal copiado leva a pessoa a poder tentar outro,
            # em vez de bater num 404 sem saída.
            messages.error(
                self.request,
                "Não encontramos nenhuma marcação com este código.",
            )

        return context


class PublicAppointmentLookupView(FormView):
    # Allows customers to search by reference code or request details by email.

    template_name = "appointments/public_appointment_lookup.html"
    form_class = PublicAppointmentLookupForm

    def form_valid(self, form):
        # Search appointment by reference code or send open appointment details by email.
        reference_code = form.cleaned_data.get("reference_code")
        email = form.cleaned_data.get("email")

        if email:
            result = PublicAppointmentLookupService.send_lookup_email(email)

            if not result.success:
                form.add_error("email", result.message)
                return self.form_invalid(form)

            messages.success(self.request, result.message)
            return redirect("appointments:public_appointment_lookup")

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

    days_in_strip = 7

    # No telemóvel não há faixa de dias: a escolha passa por uma lista. Chega
    # para três a quatro semanas, que é o horizonte de quem marca podologia.
    days_in_selector = 21
    selector_search_window = 60

    def get_day_options(self, selected_date):
        """Dias oferecidos na lista de datas do telemóvel.

        Só entram dias em que a clínica abre. Uma lista com domingos que depois
        aparecem sempre esgotados faria a cliente pensar que não há vaga
        nenhuma.
        """

        dias_abertos = set(
            BusinessHour.objects.filter(is_active=True).values_list(
                "weekday", flat=True
            )
        )

        today = timezone.localdate()
        dias = []

        for index in range(self.selector_search_window):
            if len(dias) >= self.days_in_selector:
                break

            dia = today + timedelta(days=index)

            if dia.weekday() in dias_abertos:
                dias.append(dia)

        # A data escolhida tem de estar na lista, mesmo que seja um dia
        # fechado ou esteja além do horizonte: sem isso a lista mostraria outro
        # dia diferente do que a página está a apresentar.
        if selected_date not in dias:
            dias.append(selected_date)
            dias.sort()

        return dias

    def get_week_days(self, selected_date, selected_service=None):
        """Faixa dos próximos dias, a começar em hoje.

        Antes começava sempre na segunda-feira da semana escolhida, o que numa
        quinta-feira mostrava três dias já passados e sem utilidade nenhuma.
        Agora corre para a frente e atravessa a semana quando é preciso.
        """

        today = timezone.localdate()
        start_date = today

        # Quando a cliente salta para uma data distante pelo campo de data, a
        # faixa acompanha-a; caso contrário mantém-se ancorada em hoje.
        if selected_date > today + timedelta(days=self.days_in_strip - 1):
            start_date = selected_date

        dias = [
            start_date + timedelta(days=index) for index in range(self.days_in_strip)
        ]

        # Uma consulta para os dias todos da faixa, em vez de uma por dia.
        AvailabilityService.preload_appointments(dias)

        week_days = []

        for current_date in dias:
            availability_status = AvailabilityService.get_availability_status(
                selected_service,
                current_date,
                public_safe=True,
            )

            week_days.append(
                {
                    "date": current_date,
                    "weekday": current_date.strftime("%a"),
                    "day": current_date.strftime("%d"),
                    "month": current_date.strftime("%b"),
                    "is_selected": current_date == selected_date,
                    "availability_status": availability_status,
                }
            )

        return week_days

    def get_selected_service(self):
        # Get selected service from query string
        service_id = self.request.GET.get("service")

        if not service_id:
            return (
                Service.objects.filter(
                    is_active=True,
                    category__is_active=True,
                    category__is_coming_soon=False,
                )
                .select_related("category")
                .order_by(
                    "category__display_order",
                    "category__name",
                    "name",
                )
                .first()
            )

        return (
            Service.objects.filter(
                pk=service_id,
                is_active=True,
                category__is_active=True,
                category__is_coming_soon=False,
            )
            .select_related("category")
            .first()
        )

    def get_selected_date(self):
        # Data escolhida, nunca no passado: um dia que já passou não tem
        # horários para oferecer, e mostrá-lo só confunde.
        today = timezone.localdate()
        date_value = self.request.GET.get("date")

        if not date_value:
            return today

        try:
            selected_date = datetime.strptime(date_value, "%Y-%m-%d").date()
        except ValueError:
            return today

        return max(selected_date, today)

    def get_context_data(self, **kwargs):
        # Add public visual schedule data to context
        with AvailabilityService.batch():
            return self.build_context(**kwargs)

    def build_context(self, **kwargs):
        """Contexto da página, já dentro do lote de leitura.

        A faixa de dias, a lista de datas e a grelha do dia escolhido olham
        todas para o mesmo horário de funcionamento e para os mesmos bloqueios.
        Sem o lote, cada dia repetia essas consultas.
        """

        context = super().get_context_data(**kwargs)

        selected_service = self.get_selected_service()
        selected_date = self.get_selected_date()

        slots = []
        availability_status = {
            "type": "no_service",
            "is_fully_blocked": False,
            "title": "Nenhum serviço selecionado",
            "message": "Escolha um serviço ativo para consultar a disponibilidade.",
            "icon": "bi-calendar2-week",
            "block_title": "",
            "block_notes": "",
        }

        if selected_service:
            slots = self.get_public_slot_grid(
                selected_service,
                selected_date,
            )
            availability_status = AvailabilityService.get_availability_status(
                selected_service,
                selected_date,
                public_safe=True,
            )

        context["service_categories"] = (
            ServiceCategory.objects.filter(
                is_active=True,
                is_coming_soon=False,
                services__is_active=True,
            )
            .prefetch_related(
                Prefetch(
                    "services",
                    queryset=Service.objects.filter(is_active=True).order_by("name"),
                )
            )
            .distinct()
            .order_by("display_order", "name")
        )

        context["services"] = (
            Service.objects.filter(
                is_active=True,
                category__is_active=True,
                category__is_coming_soon=False,
            )
            .select_related("category")
            .order_by(
                "category__display_order",
                "category__name",
                "name",
            )
        )

        context["selected_service"] = selected_service
        context["selected_date"] = selected_date
        context["slots"] = slots
        context["availability_status"] = availability_status
        context["week_days"] = self.get_week_days(selected_date, selected_service)
        context["day_options"] = self.get_day_options(selected_date)
        context["today"] = timezone.localdate()

        return context


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
