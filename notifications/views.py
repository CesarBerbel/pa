from django.conf import settings as django_settings
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DeleteView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from appointments.mixins import InternalAreaRequiredMixin
from appointments.models import Appointment

from .followup_services import followups_for, last_sent_at, send_followup
from .forms import (
    EmailTemplateForm,
    ServiceFollowUpForm,
    WhatsAppEventSettingForm,
    WhatsAppTestForm,
)
from .models import (
    EmailTemplate,
    ServiceFollowUp,
    WhatsAppEventSetting,
    WhatsAppMessageLog,
)
from .services import EmailTemplateService
from .twilio_callbacks import record_status, signature_is_valid
from .twilio_whatsapp import resolve_recipients, send_manual, send_test, sent_logs


class EmailTemplateListView(InternalAreaRequiredMixin, ListView):
    model = EmailTemplate
    template_name = "notifications/email_template_list.html"
    context_object_name = "templates"

    def get_queryset(self):
        return EmailTemplate.objects.prefetch_related("follow_ups__service")


class EmailTemplateCreateView(InternalAreaRequiredMixin, CreateView):
    model = EmailTemplate
    form_class = EmailTemplateForm
    template_name = "notifications/email_template_form.html"
    success_url = reverse_lazy("notifications:email_template_list")

    def form_valid(self, form):
        messages.success(self.request, "Modelo de email criado.")
        return super().form_valid(form)


class EmailTemplateUpdateView(InternalAreaRequiredMixin, UpdateView):
    model = EmailTemplate
    form_class = EmailTemplateForm
    template_name = "notifications/email_template_form.html"
    success_url = reverse_lazy("notifications:email_template_list")

    def form_valid(self, form):
        messages.success(self.request, "Modelo de email atualizado.")
        return super().form_valid(form)


class EmailTemplateDeleteView(InternalAreaRequiredMixin, DeleteView):
    model = EmailTemplate
    template_name = "notifications/email_template_confirm_delete.html"
    success_url = reverse_lazy("notifications:email_template_list")

    def post(self, request, *args, **kwargs):
        modelo = self.get_object()

        # A base de dados protegeria isto com um erro cru. Vale mais explicar
        # o que está a usar o modelo do que mostrar um ProtectedError.
        em_uso = list(modelo.follow_ups.all()) + list(modelo.event_settings.all())

        if em_uso:
            messages.error(
                request,
                "Este modelo está a ser usado e não pode ser apagado. "
                "Retire-o das regras que o usam ou desative-o.",
            )
            return redirect("notifications:email_template_list")

        messages.success(request, "Modelo de email apagado.")

        return super().post(request, *args, **kwargs)


class EmailTemplatePreviewView(InternalAreaRequiredMixin, TemplateView):
    """Como o email fica, com dados de exemplo.

    Escrever um modelo com variáveis às cegas e só descobrir o resultado
    quando um cliente o recebe é o erro que isto evita.
    """

    template_name = "notifications/email_template_preview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        modelo = get_object_or_404(EmailTemplate, pk=self.kwargs["pk"])

        context["email_template"] = modelo
        context["preview"] = EmailTemplateService.render_template_object(
            email_template=modelo,
            context_data=EmailTemplateService.get_sample_context(),
        )

        return context


class ServiceFollowUpListView(InternalAreaRequiredMixin, ListView):
    model = ServiceFollowUp
    template_name = "notifications/service_followup_list.html"
    context_object_name = "followups"

    def get_queryset(self):
        return ServiceFollowUp.objects.select_related("service", "email_template")


class ServiceFollowUpCreateView(InternalAreaRequiredMixin, CreateView):
    model = ServiceFollowUp
    form_class = ServiceFollowUpForm
    template_name = "notifications/service_followup_form.html"
    success_url = reverse_lazy("notifications:service_followup_list")

    def form_valid(self, form):
        messages.success(self.request, "Seguimento criado.")
        return super().form_valid(form)


class ServiceFollowUpUpdateView(InternalAreaRequiredMixin, UpdateView):
    model = ServiceFollowUp
    form_class = ServiceFollowUpForm
    template_name = "notifications/service_followup_form.html"
    success_url = reverse_lazy("notifications:service_followup_list")

    def form_valid(self, form):
        messages.success(self.request, "Seguimento atualizado.")
        return super().form_valid(form)


class ServiceFollowUpDeleteView(InternalAreaRequiredMixin, DeleteView):
    model = ServiceFollowUp
    template_name = "notifications/service_followup_confirm_delete.html"
    success_url = reverse_lazy("notifications:service_followup_list")

    def post(self, request, *args, **kwargs):
        messages.success(request, "Seguimento removido.")
        return super().post(request, *args, **kwargs)


class AppointmentFollowUpView(InternalAreaRequiredMixin, TemplateView):
    """Seguimentos de uma marcação, com envio imediato.

    O prazo configurado serve o caso normal. Este ecrã serve o resto: a cliente
    que ligou a pedir as instruções, ou o email que se perdeu.
    """

    template_name = "notifications/appointment_followups.html"

    def get_appointment(self):
        return get_object_or_404(
            Appointment.objects.select_related("customer", "service"),
            pk=self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        appointment = self.get_appointment()
        hoje = timezone.localdate()

        linhas = []

        for followup in followups_for(appointment):
            enviado_em = last_sent_at(appointment, followup)
            previsto = followup.due_date_for(appointment)

            linhas.append(
                {
                    "followup": followup,
                    "due_date": previsto,
                    "sent_at": enviado_em,
                    "is_due": previsto <= hoje,
                }
            )

        context["appointment"] = appointment
        context["rows"] = linhas
        context["has_email"] = bool(appointment.customer.email)
        context["whatsapp_rows"] = self.get_whatsapp_rows(appointment)
        context["twilio_enabled"] = django_settings.TWILIO_ENABLED

        return context

    def get_whatsapp_rows(self, appointment):
        """Todas as mensagens configuradas, mesmo as desligadas.

        O interruptor governa o disparo automático. À mão, faz sentido poder
        enviar uma mensagem que ainda não está a sair sozinha — foi para isso
        que o texto foi escrito.
        """

        linhas = []

        for setting in WhatsAppEventSetting.objects.all():
            ultimo = sent_logs(appointment, setting).first()

            linhas.append(
                {
                    "setting": setting,
                    "recipients": resolve_recipients(setting, appointment),
                    "last_log": ultimo,
                    "sent_at": ultimo.sent_at if ultimo else None,
                    "needs_template": not setting.content_sid.strip(),
                }
            )

        return linhas


class AppointmentFollowUpSendView(InternalAreaRequiredMixin, View):
    def post(self, request, pk, followup_pk):
        appointment = get_object_or_404(Appointment, pk=pk)
        followup = get_object_or_404(ServiceFollowUp, pk=followup_pk)

        if followup.service_id != appointment.service_id:
            messages.error(request, "Este seguimento não pertence a este serviço.")
            return redirect("notifications:appointment_followups", pk=pk)

        resultado = send_followup(appointment, followup)

        if resultado.success:
            messages.success(request, resultado.message)
        else:
            messages.error(request, resultado.message)

        return redirect(reverse("notifications:appointment_followups", args=[pk]))


class WhatsAppSettingListView(InternalAreaRequiredMixin, ListView):
    model = WhatsAppEventSetting
    template_name = "notifications/whatsapp_setting_list.html"
    context_object_name = "settings_list"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["twilio_enabled"] = django_settings.TWILIO_ENABLED
        context["twilio_from"] = django_settings.TWILIO_WHATSAPP_FROM
        context["professional_number"] = django_settings.TWILIO_PROFESSIONAL_WHATSAPP
        context["recent_logs"] = WhatsAppMessageLog.objects.filter(
            provider=WhatsAppMessageLog.PROVIDER_TWILIO
        ).select_related("appointment")[:15]

        return context


class WhatsAppSettingCreateView(InternalAreaRequiredMixin, CreateView):
    model = WhatsAppEventSetting
    form_class = WhatsAppEventSettingForm
    template_name = "notifications/whatsapp_setting_form.html"
    success_url = reverse_lazy("notifications:whatsapp_setting_list")

    def form_valid(self, form):
        messages.success(self.request, "Mensagem configurada.")
        return super().form_valid(form)


class WhatsAppSettingUpdateView(InternalAreaRequiredMixin, UpdateView):
    model = WhatsAppEventSetting
    form_class = WhatsAppEventSettingForm
    template_name = "notifications/whatsapp_setting_form.html"
    success_url = reverse_lazy("notifications:whatsapp_setting_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["test_form"] = WhatsAppTestForm()
        return context

    def form_valid(self, form):
        messages.success(self.request, "Mensagem atualizada.")
        return super().form_valid(form)


class WhatsAppSettingDeleteView(InternalAreaRequiredMixin, DeleteView):
    model = WhatsAppEventSetting
    template_name = "notifications/whatsapp_setting_confirm_delete.html"
    success_url = reverse_lazy("notifications:whatsapp_setting_list")

    def post(self, request, *args, **kwargs):
        messages.success(request, "Mensagem removida.")
        return super().post(request, *args, **kwargs)


class WhatsAppSettingTestView(InternalAreaRequiredMixin, View):
    """Envio de teste, para apanhar a configuração errada antes do cliente."""

    def post(self, request, pk):
        setting = get_object_or_404(WhatsAppEventSetting, pk=pk)
        form = WhatsAppTestForm(request.POST)

        if not form.is_valid():
            messages.error(request, "Indique o número de destino.")
            return redirect("notifications:whatsapp_setting_update", pk=pk)

        resultado = send_test(setting, form.cleaned_data["recipient"])

        if resultado.success:
            messages.success(request, resultado.message)
        else:
            messages.error(request, resultado.message)

        return redirect("notifications:whatsapp_setting_update", pk=pk)


class AppointmentWhatsAppSendView(InternalAreaRequiredMixin, View):
    """Dispara uma mensagem configurada para esta marcação, agora."""

    def post(self, request, pk, setting_pk):
        appointment = get_object_or_404(
            Appointment.objects.select_related("customer", "service"), pk=pk
        )
        setting = get_object_or_404(WhatsAppEventSetting, pk=setting_pk)

        resultado = send_manual(appointment, setting)

        if resultado.success:
            messages.success(request, f"{setting}: {resultado.message}")
        else:
            messages.error(request, f"{setting}: {resultado.message}")

        return redirect("notifications:appointment_followups", pk=pk)


@method_decorator(csrf_exempt, name="dispatch")
class TwilioStatusWebhookView(View):
    """Recebe da Twilio o estado final de cada mensagem.

    Sem autenticação de sessão — quem chama é a Twilio, não um browser — mas
    com verificação de assinatura: o endereço é público e sem ela qualquer
    pessoa podia marcar mensagens como entregues.
    """

    def post(self, request):
        if not signature_is_valid(request):
            return HttpResponseForbidden("Assinatura inválida.")

        record_status(
            message_sid=request.POST.get("MessageSid", ""),
            message_status=request.POST.get("MessageStatus", ""),
            error_code=request.POST.get("ErrorCode", ""),
        )

        # A Twilio só quer saber que recebemos; o corpo é ignorado.
        return HttpResponse(status=204)
