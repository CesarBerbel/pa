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
