from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


def create_default_email_event_settings(apps, schema_editor):
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")
    EmailEventSetting = apps.get_model("notifications", "EmailEventSetting")

    default_settings = [
        {
            "name": "Pedido de marcação criado",
            "event_type": "appointment_created",
            "template_key": "appointment_created",
            "is_active": True,
            "lead_time_value": 1,
            "lead_time_unit": "days",
        },
        {
            "name": "Marcação confirmada",
            "event_type": "appointment_confirmed",
            "template_key": "appointment_confirmed",
            "is_active": True,
            "lead_time_value": 1,
            "lead_time_unit": "days",
        },
        {
            "name": "Marcação cancelada",
            "event_type": "appointment_cancelled",
            "template_key": "appointment_cancelled",
            "is_active": True,
            "lead_time_value": 1,
            "lead_time_unit": "days",
        },
        {
            "name": "Lembrete 1 dia antes",
            "event_type": "appointment_reminder",
            "template_key": "appointment_reminder",
            "is_active": True,
            "lead_time_value": 1,
            "lead_time_unit": "days",
        },
        {
            "name": "Lembrete 2 horas antes",
            "event_type": "appointment_reminder",
            "template_key": "appointment_reminder",
            "is_active": True,
            "lead_time_value": 2,
            "lead_time_unit": "hours",
        },
    ]

    for setting_data in default_settings:
        template = EmailTemplate.objects.filter(
            key=setting_data["template_key"],
        ).first()

        EmailEventSetting.objects.update_or_create(
            event_type=setting_data["event_type"],
            lead_time_value=setting_data["lead_time_value"],
            lead_time_unit=setting_data["lead_time_unit"],
            defaults={
                "name": setting_data["name"],
                "email_template": template,
                "is_active": setting_data["is_active"],
                "window_before_minutes": 15,
                "window_after_minutes": 15,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailEventSetting",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Nome interno para identificar esta regra no admin.",
                        max_length=150,
                    ),
                ),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("appointment_created", "Pedido de marcação criado"),
                            ("appointment_confirmed", "Marcação confirmada"),
                            ("appointment_cancelled", "Marcação cancelada"),
                            ("appointment_reminder", "Lembrete antes da marcação"),
                        ],
                        help_text="Ação do sistema que poderá enviar email.",
                        max_length=50,
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Desmarque para não enviar email nesta ação.",
                    ),
                ),
                (
                    "lead_time_value",
                    models.PositiveIntegerField(
                        default=1,
                        help_text="Apenas para lembretes. Exemplo: 1 dia antes, 2 horas antes.",
                    ),
                ),
                (
                    "lead_time_unit",
                    models.CharField(
                        choices=[("hours", "Horas antes"), ("days", "Dias antes")],
                        default="days",
                        help_text="Apenas para lembretes.",
                        max_length=10,
                    ),
                ),
                (
                    "window_before_minutes",
                    models.PositiveIntegerField(
                        default=15,
                        help_text="Apenas para lembretes. Margem antes do horário-alvo, em minutos.",
                    ),
                ),
                (
                    "window_after_minutes",
                    models.PositiveIntegerField(
                        default=15,
                        help_text="Apenas para lembretes. Margem depois do horário-alvo, em minutos.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "email_template",
                    models.ForeignKey(
                        blank=True,
                        help_text="Template usado nesta ação. Se ficar vazio, o sistema usa o template pela chave padrão ou o texto de fallback.",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="event_settings",
                        to="notifications.emailtemplate",
                    ),
                ),
            ],
            options={
                "ordering": ["event_type", "lead_time_unit", "lead_time_value", "name"],
            },
        ),
        migrations.AddConstraint(
            model_name="emaileventsetting",
            constraint=models.UniqueConstraint(
                condition=~Q(("event_type", "appointment_reminder")),
                fields=("event_type",),
                name="unique_single_email_setting_per_non_reminder_event",
            ),
        ),
        migrations.AddConstraint(
            model_name="emaileventsetting",
            constraint=models.UniqueConstraint(
                condition=Q(("event_type", "appointment_reminder")),
                fields=("event_type", "lead_time_value", "lead_time_unit"),
                name="unique_email_reminder_setting_per_lead_time",
            ),
        ),
        migrations.RunPython(
            create_default_email_event_settings, migrations.RunPython.noop
        ),
    ]
