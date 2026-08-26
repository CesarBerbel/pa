"""Põe os textos do lembrete da marcação: o email e a mensagem de WhatsApp.

O lembrete existe sobretudo para dar tempo de desmarcar: uma vaga libertada na
véspera ainda se preenche, uma falta avisada em cima da hora não.

A regra de WhatsApp nasce **desligada**, como todas as outras. A do email nasce
ligada, senão o comando corria de meia em meia hora sem mandar nada e ninguém
percebia porquê.
"""

import json

from django.db import migrations

from notifications.default_email_templates import DEFAULT_EMAIL_TEMPLATES
from notifications.default_messages import DEFAULT_MESSAGES
from notifications.english_messages import EMAIL_TEMPLATES_EN, WHATSAPP_MESSAGES_EN

CHAVE = "appointment_reminder"


def semear(apps, schema_editor):
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")
    EmailEventSetting = apps.get_model("notifications", "EmailEventSetting")
    WhatsAppEventSetting = apps.get_model("notifications", "WhatsAppEventSetting")

    entrada = next(item for item in DEFAULT_EMAIL_TEMPLATES if item["key"] == CHAVE)
    ingles = EMAIL_TEMPLATES_EN.get(CHAVE, {})

    modelo, _criado = EmailTemplate.objects.get_or_create(
        key=CHAVE,
        defaults={
            "name": entrada["name"],
            "subject": entrada["subject"],
            "body_text": entrada["body_text"],
            "body_html": entrada["body_html"],
            "subject_en": ingles.get("subject", ""),
            "body_text_en": ingles.get("body_text", ""),
            "body_html_en": ingles.get("body_html", ""),
            "is_active": True,
        },
    )

    EmailEventSetting.objects.get_or_create(
        event_type=entrada["event_type"],
        audience=entrada["audience"],
        defaults={
            "name": entrada["name"],
            "email_template": modelo,
            "is_active": True,
        },
    )

    for mensagem in DEFAULT_MESSAGES:
        if mensagem["event_type"] != CHAVE:
            continue

        WhatsAppEventSetting.objects.get_or_create(
            event_type=mensagem["event_type"],
            audience=mensagem["audience"],
            defaults={
                "body_template": mensagem["body_template"],
                "body_template_en": WHATSAPP_MESSAGES_EN.get(
                    (mensagem["event_type"], mensagem["audience"]), ""
                ),
                "meta_template_body": mensagem.get("meta_template_body", ""),
                "content_variables": json.dumps(
                    mensagem.get("content_variables", {}), ensure_ascii=False, indent=2
                ),
                "is_active": False,
            },
        )


def limpar(apps, schema_editor):
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")
    EmailEventSetting = apps.get_model("notifications", "EmailEventSetting")
    WhatsAppEventSetting = apps.get_model("notifications", "WhatsAppEventSetting")

    EmailEventSetting.objects.filter(event_type=CHAVE).delete()
    EmailTemplate.objects.filter(key=CHAVE, follow_ups__isnull=True).delete()
    WhatsAppEventSetting.objects.filter(
        event_type=CHAVE,
        is_active=False,
        content_sid="",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0030_reminder_setting"),
    ]

    operations = [
        migrations.RunPython(semear, limpar),
    ]
