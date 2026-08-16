"""Cria as mensagens de WhatsApp que o sistema traz por omissão.

Ficam **desligadas**. O texto está pronto e o modelo para submeter à Meta
também, mas nenhuma mensagem sai antes de alguém rever o que diz, submeter o
modelo e colar o Content SID. Criá-las já ativas seria decidir por quem gere a
clínica o que os clientes recebem.
"""

import json

from django.db import migrations

from notifications.default_messages import DEFAULT_MESSAGES


def criar(apps, schema_editor):
    WhatsAppEventSetting = apps.get_model("notifications", "WhatsAppEventSetting")

    for entrada in DEFAULT_MESSAGES:
        WhatsAppEventSetting.objects.get_or_create(
            event_type=entrada["event_type"],
            audience=entrada["audience"],
            defaults={
                "body_template": entrada["body_template"],
                "meta_template_body": entrada["meta_template_body"],
                "content_variables": json.dumps(
                    entrada["content_variables"], ensure_ascii=False, indent=2
                ),
                "is_active": False,
            },
        )


def apagar(apps, schema_editor):
    WhatsAppEventSetting = apps.get_model("notifications", "WhatsAppEventSetting")

    for entrada in DEFAULT_MESSAGES:
        # Só remove as que continuam por estrear: uma regra já ativa foi
        # revista por alguém e não deve desaparecer num rollback.
        WhatsAppEventSetting.objects.filter(
            event_type=entrada["event_type"],
            audience=entrada["audience"],
            is_active=False,
            content_sid="",
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0007_whatsappeventsetting_meta_template_body_and_more"),
    ]

    operations = [
        migrations.RunPython(criar, apagar),
    ]
