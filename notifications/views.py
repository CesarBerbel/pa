from django.conf import settings as django_settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
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
    MessagingSettingForm,
    ServiceFollowUpForm,
    WhatsAppEventSettingForm,
    WhatsAppTestForm,
)
from .models import (
    EmailEventSetting,
    EmailTemplate,
    MessagingSetting,
    ServiceFollowUp,
    WhatsAppEventSetting,
    WhatsAppMessageLog,
)
from . import baileys_whatsapp
from .services import EmailTemplateService
from .whatsapp_dispatch import (
    provider_error,
    resolve_recipients,
    send_manual,
    send_test,
    sent_logs,
)


class EmailTemplateListView(InternalAreaRequiredMixin, ListView):
    """Os modelos de email, separados por quem os manda.

    Numa lista só, os textos automáticos e os de acompanhamento ficavam
    misturados e com nomes parecidos — e o que se abria para editar era o
    outro. Separados, a lista responde à pergunta certa: não "que modelos
    existem", mas "o que é que sai daqui sozinho e o que é que sai por causa
    de um serviço".

    As mensagens por serviço vivem aqui em baixo, e não num ecrã à parte: um
    seguimento é um modelo mais um serviço mais uma altura, e configurá-lo
    obrigava a saltar entre dois menus para ver as duas metades da mesma
    coisa.
    """

    model = EmailTemplate
    template_name = "notifications/email_template_list.html"
    context_object_name = "templates"

    def get_queryset(self):
        return EmailTemplate.objects.prefetch_related(
            "follow_ups__service",
            "event_settings",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        grupos = {
            EmailTemplate.USE_AUTOMATIC: [],
            EmailTemplate.USE_FOLLOWUP: [],
            EmailTemplate.USE_UNUSED: [],
        }

        for modelo in context["templates"]:
            grupos[modelo.usage()].append(modelo)

        context["automatic_templates"] = grupos[EmailTemplate.USE_AUTOMATIC]
        context["followup_templates"] = grupos[EmailTemplate.USE_FOLLOWUP]
        context["unused_templates"] = grupos[EmailTemplate.USE_UNUSED]

        context["followups"] = ServiceFollowUp.objects.select_related(
            "service", "email_template"
        )

        return context


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


class ServiceFollowUpCreateView(InternalAreaRequiredMixin, CreateView):
    model = ServiceFollowUp
    form_class = ServiceFollowUpForm
    template_name = "notifications/service_followup_form.html"
    success_url = reverse_lazy("notifications:email_template_list")

    def form_valid(self, form):
        messages.success(self.request, "Mensagem criada.")
        return super().form_valid(form)


class ServiceFollowUpUpdateView(InternalAreaRequiredMixin, UpdateView):
    model = ServiceFollowUp
    form_class = ServiceFollowUpForm
    template_name = "notifications/service_followup_form.html"
    success_url = reverse_lazy("notifications:email_template_list")

    def form_valid(self, form):
        messages.success(self.request, "Mensagem atualizada.")
        return super().form_valid(form)


class ServiceFollowUpDeleteView(InternalAreaRequiredMixin, DeleteView):
    model = ServiceFollowUp
    template_name = "notifications/service_followup_confirm_delete.html"
    success_url = reverse_lazy("notifications:email_template_list")

    def post(self, request, *args, **kwargs):
        messages.success(request, "Mensagem removida.")
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
        context["whatsapp_enabled"] = django_settings.BAILEYS_ENABLED

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
                    # O que falta é o texto da mensagem.
                    "needs_template": not setting.is_ready_to_send(),
                    "blocked_reason": provider_error(setting),
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
    """Aba das mensagens: quando enviar, a quem, e por que caminho."""

    model = WhatsAppEventSetting
    template_name = "notifications/whatsapp_setting_list.html"
    context_object_name = "settings_list"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["active_tab"] = "messages"
        context["baileys_enabled"] = django_settings.BAILEYS_ENABLED
        context["professional_number"] = django_settings.BAILEYS_PROFESSIONAL_WHATSAPP

        # Uma regra pode estar ligada e mesmo assim não enviar, porque o envio
        # está desligado no servidor. Sem isto explicado na tabela, o ecrã diz
        # "A enviar" para uma mensagem que não sai.
        context["rows"] = [
            {"setting": regra, "blocked_reason": provider_error(regra)}
            for regra in context["settings_list"]
        ]

        # Os envios antigos pela Twilio continuam a aparecer: o histórico é
        # para se poder olhar para trás, e para trás ela ainda lá está.
        context["recent_logs"] = WhatsAppMessageLog.objects.select_related(
            "appointment"
        )[:15]

        return context


class WhatsAppConnectionView(InternalAreaRequiredMixin, TemplateView):
    """Aba da ligação: o QR code e o estado do número da clínica.

    O emparelhamento é uma sessão, não uma credencial que se cole num ficheiro
    de ambiente. Por isso precisa de um ecrã: alguém tem de ler um código com
    o telemóvel, e alguém tem de poder ver se a ligação ainda está de pé.
    """

    template_name = "notifications/whatsapp_connection.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["active_tab"] = "connection"
        context["baileys_enabled"] = django_settings.BAILEYS_ENABLED
        context["baileys_url"] = django_settings.BAILEYS_API_URL

        # O estado inicial vem do servidor para o ecrã não abrir vazio; a
        # partir daí é o JavaScript que o vai refrescando.
        context["status"] = baileys_whatsapp.get_status()

        # Quantas regras dependem desta ligação: com ela em baixo, é este o
        # número de mensagens que deixa de sair.
        context["active_rules"] = WhatsAppEventSetting.objects.filter(
            is_active=True
        ).count()

        context["total_rules"] = WhatsAppEventSetting.objects.count()

        return context


class WhatsAppConnectionStatusView(InternalAreaRequiredMixin, View):
    """Estado da ligação em JSON, para o ecrã se ir atualizando sozinho.

    O QR code muda a cada 20 segundos e a ligação pode cair a qualquer
    momento. Obrigar a recarregar a página para ver isso tornaria o
    emparelhamento uma questão de sorte.
    """

    def get(self, request):
        estado = baileys_whatsapp.get_status()

        return JsonResponse(
            {
                "state": estado.get("state", "unknown"),
                "qr": estado.get("qr", ""),
                "me": estado.get("me"),
                "last_error": estado.get("lastError", ""),
                "connected_at": estado.get("connectedAt"),
                "label": WHATSAPP_STATE_LABELS.get(
                    estado.get("state", ""), estado.get("state", "desconhecido")
                ),
            }
        )


WHATSAPP_STATE_LABELS = {
    "disabled": "Desligado nas definições",
    "misconfigured": "Mal configurado",
    "unreachable": "Serviço inacessível",
    "starting": "A arrancar",
    "connecting": "A ligar",
    "waiting_qr": "À espera da leitura do QR code",
    "connected": "Ligado",
    "disconnected": "Desligado",
    "logged_out": "Sessão terminada no telemóvel",
}


class WhatsAppConnectionLogoutView(InternalAreaRequiredMixin, View):
    """Termina a sessão para se poder ligar outro número."""

    def post(self, request):
        try:
            baileys_whatsapp.logout()
            messages.success(
                request,
                "Sessão terminada. Leia o QR code novo para voltar a ligar.",
            )
        except baileys_whatsapp.BaileysError as erro:
            messages.error(request, str(erro))

        return redirect("notifications:whatsapp_connection")


class WhatsAppConnectionRestartView(InternalAreaRequiredMixin, View):
    """Reabre a ligação sem perder o emparelhamento."""

    def post(self, request):
        try:
            baileys_whatsapp.restart()
            messages.success(request, "A reabrir a ligação.")
        except baileys_whatsapp.BaileysError as erro:
            messages.error(request, str(erro))

        return redirect("notifications:whatsapp_connection")


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


class MessagingSettingView(InternalAreaRequiredMixin, UpdateView):
    """Que canais podem escrever aos clientes: email, WhatsApp, ou nenhum."""

    model = MessagingSetting
    form_class = MessagingSettingForm
    template_name = "notifications/messaging_setting_form.html"
    success_url = reverse_lazy("notifications:messaging_setting")

    def get_object(self, queryset=None):
        return MessagingSetting.load()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Quantas regras deixam de disparar enquanto isto estiver desligado. É
        # o que torna a decisão concreta para quem está a olhar para o ecrã.
        context["regras_whatsapp_ativas"] = WhatsAppEventSetting.objects.filter(
            is_active=True
        ).count()

        context["eventos_email_ativos"] = EmailEventSetting.objects.filter(
            is_active=True
        ).count()

        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user

        resposta = super().form_valid(form)

        # A mensagem diz o que fica calado, e não o que ficou ligado: é o
        # silêncio que costuma ser descoberto tarde e por outra pessoa.
        calados = [
            nome
            for nome, ligado in (
                ("emails", form.instance.send_emails),
                ("mensagens de WhatsApp", form.instance.send_whatsapp),
            )
            if not ligado
        ]

        if not calados:
            messages.success(
                self.request,
                "Envio ligado nos dois canais. Emails e WhatsApp voltam a sair.",
            )
        else:
            messages.warning(
                self.request,
                f"Não saem {' nem '.join(calados)} até voltar a ligar. "
                "As marcações continuam a funcionar.",
            )

        return resposta
