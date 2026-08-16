"""Cria os modelos de email principais e liga-os às regras de envio.

Antes disto as regras existiam com o modelo por preencher, e o que saía era o
texto de reserva embutido no código: funcional, mas texto simples e não
editável. A partir daqui o conteúdo é editável na área interna.

Ao contrário das mensagens de WhatsApp, estes ficam **ativos**: o email já
estava a sair, e deixá-los desligados seria trocar um email simples por email
nenhum.
"""

from django.db import migrations

from notifications.default_email_templates import DEFAULT_EMAIL_TEMPLATES


def criar(apps, schema_editor):
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")
    EmailEventSetting = apps.get_model("notifications", "EmailEventSetting")

    for entrada in DEFAULT_EMAIL_TEMPLATES:
        modelo, _ = EmailTemplate.objects.get_or_create(
            key=entrada["key"],
            defaults={
                "name": entrada["name"],
                "subject": entrada["subject"],
                "body_text": entrada["body_text"],
                "body_html": entrada["body_html"],
                "is_active": True,
            },
        )

        # Só preenche o que está por preencher. Uma regra que já aponta para
        # outro modelo foi decidida por alguém e não se toca.
        EmailEventSetting.objects.filter(
            event_type=entrada["event_type"],
            email_template__isnull=True,
        ).update(email_template=modelo)


def apagar(apps, schema_editor):
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")
    EmailEventSetting = apps.get_model("notifications", "EmailEventSetting")

    chaves = [entrada["key"] for entrada in DEFAULT_EMAIL_TEMPLATES]

    EmailEventSetting.objects.filter(email_template__key__in=chaves).update(
        email_template=None
    )
    EmailTemplate.objects.filter(key__in=chaves).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0008_seed_default_whatsapp_messages"),
    ]

    operations = [
        migrations.RunPython(criar, apagar),
    ]
