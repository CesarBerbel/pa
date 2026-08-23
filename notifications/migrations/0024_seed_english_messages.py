"""Põe as versões inglesas das mensagens que a cliente lê.

Quem marca em /en/ recebia tudo em português. Passa a receber na língua em
que marcou — os emails e o WhatsApp. Os avisos à profissional ficam como
estão: quem os lê é sempre a mesma pessoa.

**Só se preenche o que está vazio.** Um campo inglês em branco significa "por
traduzir"; um campo escrito é uma decisão de quem gere a clínica e não se
apaga. Por isso a condição aqui não é `updated_at == created_at` como nas
migrações anteriores — os campos são novos e estão todos vazios, e é o vazio
que autoriza a escrita.
"""

from django.db import migrations

from notifications.english_messages import EMAIL_TEMPLATES_EN, WHATSAPP_MESSAGES_EN


def semear(apps, schema_editor):
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")
    WhatsAppEventSetting = apps.get_model("notifications", "WhatsAppEventSetting")

    for chave, versao in EMAIL_TEMPLATES_EN.items():
        modelo = EmailTemplate.objects.filter(key=chave).first()

        if modelo is None:
            continue

        campos = {}

        if not modelo.subject_en.strip():
            campos["subject_en"] = versao["subject"]

        if not modelo.body_text_en.strip():
            campos["body_text_en"] = versao["body_text"]

        if not modelo.body_html_en.strip():
            campos["body_html_en"] = versao["body_html"]

        if campos:
            # update() e não save(): a linha continua a parecer o que é, uma
            # linha de fábrica, e uma migração futura pode voltar a mexer-lhe.
            EmailTemplate.objects.filter(pk=modelo.pk).update(**campos)

    for (acontecimento, destinatario), texto in WHATSAPP_MESSAGES_EN.items():
        WhatsAppEventSetting.objects.filter(
            event_type=acontecimento,
            audience=destinatario,
            body_template_en="",
        ).update(body_template_en=texto)


def limpar(apps, schema_editor):
    """Devolve ao estado anterior: sem versões inglesas.

    Só apaga o que esta migração poderia ter escrito. Um texto inglês
    diferente do de fábrica foi escrito por alguém e fica.
    """

    EmailTemplate = apps.get_model("notifications", "EmailTemplate")
    WhatsAppEventSetting = apps.get_model("notifications", "WhatsAppEventSetting")

    for chave, versao in EMAIL_TEMPLATES_EN.items():
        EmailTemplate.objects.filter(key=chave, subject_en=versao["subject"]).update(
            subject_en=""
        )
        EmailTemplate.objects.filter(
            key=chave, body_text_en=versao["body_text"]
        ).update(body_text_en="")
        EmailTemplate.objects.filter(
            key=chave, body_html_en=versao["body_html"]
        ).update(body_html_en="")

    for (acontecimento, destinatario), texto in WHATSAPP_MESSAGES_EN.items():
        WhatsAppEventSetting.objects.filter(
            event_type=acontecimento,
            audience=destinatario,
            body_template_en=texto,
        ).update(body_template_en="")


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0023_emailtemplate_body_html_en_and_more"),
    ]

    operations = [
        migrations.RunPython(semear, limpar),
    ]
