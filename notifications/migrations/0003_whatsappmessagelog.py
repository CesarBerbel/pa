# Generated manually for WhatsApp Cloud API notification audit logs.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0005_service_categories_seed"),
        ("notifications", "0002_email_event_setting"),
    ]

    operations = [
        migrations.CreateModel(
            name="WhatsAppMessageLog",
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
                    "event_type",
                    models.CharField(
                        choices=[
                            ("appointment_confirmed", "Marcação confirmada"),
                        ],
                        max_length=50,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("success", "Sucesso"),
                            ("error", "Erro"),
                            ("skipped", "Ignorado"),
                        ],
                        max_length=10,
                    ),
                ),
                ("template_name", models.CharField(max_length=100)),
                ("recipient_phone", models.CharField(max_length=30)),
                ("whatsapp_message_id", models.CharField(blank=True, max_length=255)),
                ("request_payload", models.TextField(blank=True)),
                ("response_payload", models.TextField(blank=True)),
                ("error_message", models.TextField(blank=True)),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                (
                    "appointment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="whatsapp_logs",
                        to="appointments.appointment",
                    ),
                ),
            ],
            options={
                "ordering": ["-sent_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="whatsappmessagelog",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "success")),
                fields=("appointment", "event_type", "template_name"),
                name="unique_success_whatsapp_per_appointment_event_template",
            ),
        ),
    ]
