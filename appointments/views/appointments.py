from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from appointments.mixins import (
    ClinicalAccessRequiredMixin,
    InternalAreaRequiredMixin,
    LoginRequiredMixin,
)
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from appointments.audit_services import AppointmentAuditService
from appointments.cancellation_services import AppointmentCancellationService
from appointments.forms import (
    AppointmentCancelForm,
    AppointmentForm,
    ClinicalNoteForm,
)
from appointments.models import Appointment, AppointmentLog, ClinicalNote, Service
from appointments.selectors import AppointmentFilters, AppointmentSelectors
from appointments.use_cases import ConfirmAppointmentUseCase, CompleteAppointmentUseCase
from notifications.whatsapp import WhatsAppAppointmentNotificationService


def warn_schedule_override(request, form):
    """Avisa que a marcação ficou fora do horário normal.

    Encaixar é permitido, mas passar em silêncio esconderia um engano de
    digitação — 19:00 em vez de 09:00 seria aceite sem uma palavra.
    """

    motivo = getattr(form, "schedule_override_reason", None)

    if motivo:
        messages.warning(request, f"Encaixe fora do horário normal. {motivo}")


def group_appointments_by_day(appointments):
    """Junta as marcações em blocos de um dia, pela ordem em que já vinham.

    O agrupamento não reordena nada: um dicionário por ordem de inserção segue
    a ordenação que a lista trouxe. Ordenar os dias por data aqui desfazia a
    escolha de quem pediu a lista por cliente ou por serviço.
    """

    dias = {}

    for appointment in appointments:
        dias.setdefault(appointment.date, []).append(appointment)

    return [
        {"date": data, "appointments": marcacoes} for data, marcacoes in dias.items()
    ]


class AppointmentListView(InternalAreaRequiredMixin, ListView):
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

        # Os cartões são mostrados por dia. O agrupamento fica aqui e não no
        # template porque `regroup` só junta linhas seguidas, e bastava uma
        # ordenação que não fosse por data para o mesmo dia aparecer partido
        # em vários blocos.
        context["appointment_days"] = group_appointments_by_day(context["appointments"])

        context["today"] = timezone.localdate()

        return context


class AppointmentDetailView(InternalAreaRequiredMixin, DetailView):
    """Tudo o que se sabe de uma marcação, e as ações que agem sobre ela.

    A lista passou a ser de cartões sem botões. Sem um ecrã que reúna os dados
    todos, confirmar ou cancelar era carregar num ícone ao lado de uma linha,
    sem se ver a quem pertencia.
    """

    model = Appointment
    template_name = "appointments/appointment_detail.html"
    context_object_name = "appointment"

    def get_queryset(self):
        return Appointment.objects.select_related(
            "customer",
            "service",
            "created_by",
        )


class AppointmentCreateView(InternalAreaRequiredMixin, CreateView):
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
        form.instance.origin = Appointment.ORIGIN_INTERNAL

        response = super().form_valid(form)

        # Sem isto, uma marcação criada aqui não deixava rasto nenhum: a
        # auditoria começava na primeira alteração, como se a marcação tivesse
        # aparecido sozinha.
        AppointmentAuditService.log(
            appointment=self.object,
            action=AppointmentLog.ACTION_CREATE,
            user=self.request.user,
            description="Marcação criada na área interna.",
            source=AppointmentLog.SOURCE_INTERNAL,
            changes=AppointmentAuditService.creation_changes(self.object),
        )

        messages.success(self.request, "Marcação criada com sucesso.")
        warn_schedule_override(self.request, form)

        return response


class AppointmentUpdateView(InternalAreaRequiredMixin, UpdateView):
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
        # O retrato tem de ser tirado da base de dados e antes de gravar: o
        # `self.object` já traz os valores novos do formulário, e comparar com
        # ele daria sempre "nada mudou".
        anterior = AppointmentAuditService.snapshot(
            Appointment.objects.select_related("customer", "service").get(
                pk=self.object.pk
            )
        )

        previous_status = Appointment.objects.values_list(
            "status",
            flat=True,
        ).get(pk=self.object.pk)

        response = super().form_valid(form)

        self.object.refresh_from_db()

        alteracoes = AppointmentAuditService.diff(
            anterior,
            AppointmentAuditService.snapshot(self.object),
        )

        AppointmentAuditService.log(
            appointment=self.object,
            action=AppointmentLog.ACTION_UPDATE,
            user=self.request.user,
            description="Marcação alterada na área interna.",
            source=AppointmentLog.SOURCE_INTERNAL,
            changes=alteracoes,
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
                description="Marcação confirmada ao alterar o estado.",
                source=AppointmentLog.SOURCE_INTERNAL,
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

        warn_schedule_override(self.request, form)

        return response


class AppointmentCancelView(InternalAreaRequiredMixin, UpdateView):
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


class AppointmentConfirmView(InternalAreaRequiredMixin, View):
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


class AppointmentCompleteView(InternalAreaRequiredMixin, View):
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


class ClinicalNoteUpdateView(ClinicalAccessRequiredMixin, UpdateView):
    """Nota de evolução de uma marcação: os atos praticados.

    Criada na primeira abertura, tal como a ficha de anamnese, para não obrigar
    a um passo separado no meio do atendimento.
    """

    model = ClinicalNote
    form_class = ClinicalNoteForm
    template_name = "appointments/clinical_note_form.html"

    def get_appointment(self):
        return get_object_or_404(
            Appointment.objects.select_related("customer", "service"),
            pk=self.kwargs["pk"],
        )

    def get_object(self, queryset=None):
        note, _created = ClinicalNote.objects.get_or_create(
            appointment=self.get_appointment(),
        )

        return note

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["appointment"] = self.object.appointment
        return context

    def form_valid(self, form):
        if not self.object.created_by_id:
            form.instance.created_by = self.request.user

        messages.success(self.request, "Nota de evolução guardada.")

        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "appointments:clinical_note",
            kwargs={"pk": self.object.appointment_id},
        )


class AppointmentAuditView(InternalAreaRequiredMixin, ListView):
    """Histórico do que se passou com as marcações.

    Uma linha por ação, com quem a fez, quando, de onde partiu e o que mudou.
    Serve para responder depois do facto — quem desmarcou esta cliente, a que
    horas estava antes de ser mudada — e por isso é só de leitura: um registo
    que se pode editar não prova nada.
    """

    model = AppointmentLog
    template_name = "appointments/appointment_audit.html"
    context_object_name = "logs"
    paginate_by = 50

    def get_queryset(self):
        registos = (
            AppointmentLog.objects.select_related(
                "appointment",
                "appointment__customer",
                "appointment__service",
                "performed_by",
            )
            .all()
            .order_by("-created_at")
        )

        acao = self.request.GET.get("action", "").strip()
        origem = self.request.GET.get("source", "").strip()
        pesquisa = self.request.GET.get("q", "").strip()
        utilizador = self.request.GET.get("user", "").strip()

        if acao:
            registos = registos.filter(action=acao)

        if origem:
            registos = registos.filter(source=origem)

        if utilizador:
            registos = registos.filter(performed_by_id=utilizador)

        if pesquisa:
            registos = registos.filter(
                Q(appointment__reference_code__icontains=pesquisa)
                | Q(appointment__customer__full_name__icontains=pesquisa)
                | Q(description__icontains=pesquisa)
            )

        return registos

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["action_choices"] = AppointmentLog.ACTION_CHOICES
        context["source_choices"] = AppointmentLog.SOURCE_CHOICES

        # Só quem realmente aparece no registo. A lista completa de
        # utilizadores encheria o filtro com gente que nunca lá está.
        context["users"] = (
            get_user_model()
            .objects.filter(appointment_logs__isnull=False)
            .distinct()
            .order_by("full_name")
        )

        context["filters"] = {
            "action": self.request.GET.get("action", ""),
            "source": self.request.GET.get("source", ""),
            "user": self.request.GET.get("user", ""),
            "q": self.request.GET.get("q", ""),
        }

        return context
