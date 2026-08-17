import json
import re

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class EmailTemplate(models.Model):
    # Stores customizable email templates editable via admin.

    key = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique identifier, e.g. appointment_cancelled",
    )

    name = models.CharField(
        max_length=150,
        help_text="Human-readable name",
    )

    subject = models.CharField(
        max_length=255,
    )

    body_text = models.TextField()

    body_html = models.TextField(
        blank=True,
        help_text="Optional HTML version of the email",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class EmailEventSetting(models.Model):
    # Controls which appointment events send emails and which template each event uses.

    EVENT_APPOINTMENT_CREATED = "appointment_created"
    EVENT_APPOINTMENT_CONFIRMED = "appointment_confirmed"
    EVENT_APPOINTMENT_CANCELLED = "appointment_cancelled"
    EVENT_APPOINTMENT_REMINDER = "appointment_reminder"

    EVENT_CHOICES = (
        (EVENT_APPOINTMENT_CREATED, "Pedido de marcação criado"),
        (EVENT_APPOINTMENT_CONFIRMED, "Marcação confirmada"),
        (EVENT_APPOINTMENT_CANCELLED, "Marcação cancelada"),
        (EVENT_APPOINTMENT_REMINDER, "Lembrete antes da marcação"),
    )

    LEAD_TIME_UNIT_HOURS = "hours"
    LEAD_TIME_UNIT_DAYS = "days"

    LEAD_TIME_UNIT_CHOICES = (
        (LEAD_TIME_UNIT_HOURS, "Horas antes"),
        (LEAD_TIME_UNIT_DAYS, "Dias antes"),
    )

    name = models.CharField(
        max_length=150,
        help_text="Nome interno para identificar esta regra no admin.",
    )

    event_type = models.CharField(
        max_length=50,
        choices=EVENT_CHOICES,
        help_text="Ação do sistema que poderá enviar email.",
    )

    email_template = models.ForeignKey(
        EmailTemplate,
        on_delete=models.PROTECT,
        related_name="event_settings",
        blank=True,
        null=True,
        help_text="Template usado nesta ação. Se ficar vazio, o sistema usa o template pela chave padrão ou o texto de fallback.",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Desmarque para não enviar email nesta ação.",
    )

    lead_time_value = models.PositiveIntegerField(
        default=1,
        help_text="Apenas para lembretes. Exemplo: 1 dia antes, 2 horas antes.",
    )

    lead_time_unit = models.CharField(
        max_length=10,
        choices=LEAD_TIME_UNIT_CHOICES,
        default=LEAD_TIME_UNIT_DAYS,
        help_text="Apenas para lembretes.",
    )

    window_before_minutes = models.PositiveIntegerField(
        default=15,
        help_text="Apenas para lembretes. Margem antes do horário-alvo, em minutos.",
    )

    window_after_minutes = models.PositiveIntegerField(
        default=15,
        help_text="Apenas para lembretes. Margem depois do horário-alvo, em minutos.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["event_type", "lead_time_unit", "lead_time_value", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["event_type"],
                condition=~Q(event_type="appointment_reminder"),
                name="unique_single_email_setting_per_non_reminder_event",
            ),
            models.UniqueConstraint(
                fields=["event_type", "lead_time_value", "lead_time_unit"],
                condition=Q(event_type="appointment_reminder"),
                name="unique_email_reminder_setting_per_lead_time",
            ),
        ]

    def __str__(self):
        if self.event_type == self.EVENT_APPOINTMENT_REMINDER:
            return f"{self.name} - {self.get_lead_time_label()}"

        return self.name

    def clean(self):
        if self.event_type != self.EVENT_APPOINTMENT_REMINDER:
            return

        if self.lead_time_value < 1:
            raise ValidationError(
                "O aviso deve ser configurado com pelo menos 1 hora ou 1 dia antes."
            )

        if self.window_before_minutes < 1 or self.window_after_minutes < 1:
            raise ValidationError(
                "A janela de envio deve ter pelo menos 1 minuto antes e depois."
            )

    def get_lead_time_label(self):
        if self.lead_time_unit == self.LEAD_TIME_UNIT_DAYS:
            if self.lead_time_value == 1:
                return "1 dia antes"

            return f"{self.lead_time_value} dias antes"

        if self.lead_time_value == 1:
            return "1 hora antes"

        return f"{self.lead_time_value} horas antes"

    def get_log_key(self):
        if self.event_type != self.EVENT_APPOINTMENT_REMINDER:
            return self.event_type

        return f"reminder_{self.lead_time_value}_{self.lead_time_unit}"


class ServiceFollowUp(models.Model):
    """Email de seguimento, enviado uns dias depois do atendimento.

    Serve para os cuidados que vêm a seguir: um manual para os calos não
    voltarem, enviado 15 dias depois da remoção. Cada serviço pode ter mais do
    que um, em prazos diferentes.
    """

    service = models.ForeignKey(
        "appointments.Service",
        on_delete=models.CASCADE,
        related_name="follow_ups",
        verbose_name="Serviço",
        help_text="O seguimento é enviado a quem fez este serviço.",
    )

    email_template = models.ForeignKey(
        EmailTemplate,
        on_delete=models.PROTECT,
        related_name="follow_ups",
        verbose_name="Modelo de email",
    )

    days_after = models.PositiveIntegerField(
        default=15,
        verbose_name="Dias depois do atendimento",
        help_text="Zero envia no próprio dia do atendimento.",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Ativo",
        help_text="Desmarque para suspender o envio automático. O envio manual continua disponível.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["service__name", "days_after"]
        verbose_name = "Seguimento por serviço"
        verbose_name_plural = "Seguimentos por serviço"
        constraints = [
            models.UniqueConstraint(
                fields=["service", "email_template", "days_after"],
                name="unique_followup_per_service_template_delay",
            ),
        ]

    def __str__(self):
        return f"{self.service} · {self.get_delay_label()}"

    def get_delay_label(self):
        if self.days_after == 0:
            return "no próprio dia"

        if self.days_after == 1:
            return "1 dia depois"

        return f"{self.days_after} dias depois"

    def get_log_key(self):
        # A chave inclui a pk para dois seguimentos do mesmo serviço em prazos
        # diferentes não se confundirem um com o outro no registo de envios.
        return f"followup_{self.pk}"

    def due_date_for(self, appointment):
        from datetime import timedelta

        return appointment.date + timedelta(days=self.days_after)


class WhatsAppEventSetting(models.Model):
    """Quando enviar uma mensagem de WhatsApp e a quem.

    Uma linha por par acontecimento/destinatário: o pedido de marcação avisa a
    profissional e o cliente com textos diferentes, e cada um dos dois liga-se
    e desliga-se à parte.
    """

    EVENT_APPOINTMENT_REQUESTED = "appointment_requested"
    EVENT_APPOINTMENT_CONFIRMED = "appointment_confirmed"
    EVENT_APPOINTMENT_CANCELLED = "appointment_cancelled"
    EVENT_APPOINTMENT_COMPLETED = "appointment_completed"

    EVENT_CHOICES = (
        (EVENT_APPOINTMENT_REQUESTED, "Pedido de marcação recebido"),
        (EVENT_APPOINTMENT_CONFIRMED, "Marcação confirmada"),
        (EVENT_APPOINTMENT_CANCELLED, "Marcação cancelada"),
        (EVENT_APPOINTMENT_COMPLETED, "Atendimento concluído"),
    )

    AUDIENCE_CUSTOMER = "customer"
    AUDIENCE_PROFESSIONAL = "professional"
    AUDIENCE_CUSTOM = "custom"

    AUDIENCE_CHOICES = (
        (AUDIENCE_CUSTOMER, "Cliente"),
        (AUDIENCE_PROFESSIONAL, "Profissional"),
        (AUDIENCE_CUSTOM, "Outros números"),
    )

    event_type = models.CharField(
        max_length=50,
        choices=EVENT_CHOICES,
        verbose_name="Acontecimento",
    )

    audience = models.CharField(
        max_length=20,
        choices=AUDIENCE_CHOICES,
        default=AUDIENCE_CUSTOMER,
        verbose_name="Destinatário",
    )

    custom_recipients = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Números",
        help_text=(
            "Só para 'Outros números'. Separe por vírgulas, com indicativo: "
            "+351912345678, +351913333333."
        ),
    )

    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    body_template = models.TextField(
        blank=True,
        verbose_name="Mensagem",
        help_text=(
            "Texto livre, com as mesmas variáveis dos emails. A Twilio só o "
            "aceita nas 24 horas seguintes a uma mensagem do destinatário — "
            "fora disso é preciso um modelo aprovado."
        ),
    )

    content_sid = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="Modelo aprovado (Content SID)",
        help_text=(
            "Começa por HX. Necessário para mensagens iniciadas pela clínica, "
            "que é o caso de tudo o que sai daqui."
        ),
    )

    meta_template_body = models.TextField(
        blank=True,
        verbose_name="Texto para aprovação (Meta)",
        help_text=(
            "O mesmo texto com as posições numeradas — {{1}}, {{2}} — para "
            "colar no Content Template Builder da Twilio. É este que a Meta "
            "revê; o campo acima é o que o sistema envia."
        ),
    )

    content_variables = models.TextField(
        blank=True,
        verbose_name="Variáveis do modelo",
        help_text=(
            "JSON com as posições do modelo aprovado. Exemplo: "
            '{"1": "{{ customer_name }}", "2": "{{ appointment_date }}"}'
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["event_type", "audience"]
        verbose_name = "Mensagem de WhatsApp"
        verbose_name_plural = "Mensagens de WhatsApp"
        constraints = [
            models.UniqueConstraint(
                fields=["event_type", "audience"],
                name="unique_whatsapp_setting_per_event_audience",
            ),
        ]

    def __str__(self):
        return f"{self.get_event_type_display()} → {self.get_audience_display()}"

    def clean(self):
        if self.audience == self.AUDIENCE_CUSTOM and not self.custom_recipients.strip():
            raise ValidationError(
                {"custom_recipients": "Indique pelo menos um número."}
            )

        if not self.body_template.strip() and not self.content_sid.strip():
            raise ValidationError(
                "Preencha a mensagem ou indique um modelo aprovado; sem um dos "
                "dois não há nada para enviar."
            )

        if self.content_variables.strip():
            try:
                dados = json.loads(self.content_variables)
            except ValueError as erro:
                raise ValidationError(
                    {"content_variables": f"JSON inválido: {erro}"}
                ) from erro

            if not isinstance(dados, dict):
                raise ValidationError(
                    {"content_variables": "Deve ser um objeto JSON com as posições."}
                )

    def get_template_label(self):
        # Identifica no histórico se a mensagem saiu por modelo aprovado ou
        # como texto livre.
        return self.content_sid.strip() or "texto-livre"


class WhatsAppMessageLog(models.Model):
    # Stores WhatsApp sending attempts for audit and duplicate prevention.

    EVENT_APPOINTMENT_REQUESTED = "appointment_requested"
    EVENT_APPOINTMENT_CONFIRMED = "appointment_confirmed"
    EVENT_APPOINTMENT_CANCELLED = "appointment_cancelled"
    EVENT_APPOINTMENT_COMPLETED = "appointment_completed"

    EVENT_CHOICES = (
        (EVENT_APPOINTMENT_REQUESTED, "Pedido de marcação recebido"),
        (EVENT_APPOINTMENT_CONFIRMED, "Marcação confirmada"),
        (EVENT_APPOINTMENT_CANCELLED, "Marcação cancelada"),
        (EVENT_APPOINTMENT_COMPLETED, "Atendimento concluído"),
    )

    PROVIDER_CLOUD_API = "cloud_api"
    PROVIDER_TWILIO = "twilio"

    PROVIDER_CHOICES = (
        (PROVIDER_CLOUD_API, "WhatsApp Cloud API"),
        (PROVIDER_TWILIO, "Twilio"),
    )

    provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default=PROVIDER_CLOUD_API,
    )

    # Sem isto, avisar a profissional e o cliente do mesmo acontecimento com o
    # mesmo texto colidiria na restrição de unicidade e o segundo envio seria
    # dado como repetido.
    audience = models.CharField(
        max_length=20,
        default=WhatsAppEventSetting.AUDIENCE_CUSTOMER,
    )

    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"
    STATUS_SKIPPED = "skipped"

    STATUS_CHOICES = (
        (STATUS_SUCCESS, "Sucesso"),
        (STATUS_ERROR, "Erro"),
        (STATUS_SKIPPED, "Ignorado"),
    )

    appointment = models.ForeignKey(
        "appointments.Appointment",
        on_delete=models.CASCADE,
        related_name="whatsapp_logs",
    )

    event_type = models.CharField(
        max_length=50,
        choices=EVENT_CHOICES,
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
    )

    template_name = models.CharField(
        max_length=100,
    )

    recipient_phone = models.CharField(
        max_length=30,
    )

    whatsapp_message_id = models.CharField(
        max_length=255,
        blank=True,
    )

    request_payload = models.TextField(
        blank=True,
    )

    response_payload = models.TextField(
        blank=True,
    )

    error_message = models.TextField(
        blank=True,
    )

    # `status` diz se a Twilio **aceitou** a mensagem. Não diz se ela chegou:
    # a entrega acontece depois, e falha em silêncio se ninguém a for buscar.
    # Estes três campos são preenchidos pelo webhook de estado da Twilio.
    delivery_status = models.CharField(
        max_length=20,
        blank=True,
        help_text="Estado final devolvido pela Twilio: delivered, undelivered, failed.",
    )

    delivery_error_code = models.CharField(max_length=20, blank=True)

    delivery_updated_at = models.DateTimeField(blank=True, null=True)

    sent_at = models.DateTimeField(auto_now_add=True)

    DELIVERY_LABELS = {
        "queued": "Em fila",
        "sending": "A enviar",
        "sent": "Enviada",
        "delivered": "Entregue",
        "read": "Lida",
        "undelivered": "Não entregue",
        "failed": "Falhou",
    }

    def get_delivery_label(self):
        if not self.delivery_status:
            return "Aceite pela Twilio"

        return self.DELIVERY_LABELS.get(self.delivery_status, self.delivery_status)

    def delivery_failed(self):
        return self.delivery_status in {"undelivered", "failed"}

    class Meta:
        ordering = ["-sent_at"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "appointment",
                    "event_type",
                    "template_name",
                    "audience",
                    "provider",
                ],
                condition=Q(status="success"),
                name="unique_success_whatsapp_per_appointment_event_template",
            ),
        ]

    def __str__(self):
        return (
            f"{self.appointment.reference_code} - "
            f"{self.template_name} - {self.status}"
        )


class InstagramPost(models.Model):
    # Publicação real do Instagram, registada colando o código de incorporação
    # oficial (Instagram > "..." > Copiar código de incorporação) e exibida
    # como embed ao vivo (blockquote + embed.js) em carrossel no site.

    embed_code = models.TextField(
        help_text=(
            "Cole aqui o código de incorporação do Instagram (no post, clique em "
            '"..." → Copiar código de incorporação). Pode colar o bloco inteiro, '
            "inclusive a linha &lt;script&gt; — ela é removida automaticamente ao guardar."
        ),
    )

    display_order = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "-created_at"]
        verbose_name = "Publicação do Instagram"
        verbose_name_plural = "Publicações do Instagram"

    def save(self, *args, **kwargs):
        # Remove a(s) tag(s) <script> do trecho colado: o script do embed.js
        # já é carregado uma única vez pelo template, para todos os posts.
        self.embed_code = re.sub(
            r"<script\b[^>]*>.*?</script>",
            "",
            self.embed_code,
            flags=re.IGNORECASE | re.DOTALL,
        ).strip()

        super().save(*args, **kwargs)

    @property
    def permalink(self):
        match = re.search(r'data-instgrm-permalink="([^"]+)"', self.embed_code)

        return match.group(1) if match else ""

    def __str__(self):
        return self.permalink or f"Publicação #{self.pk}"
