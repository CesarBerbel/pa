"""Põe as confirmações a dizer onde é o atendimento, quando é em domicílio.

O texto dizia sempre "esperamos por si na <morada da clínica>". Numa marcação
em domicílio isso é o contrário do que vai acontecer: a cliente ficava à espera
no sítio errado, ou — pior — ficava em casa a duvidar do que tinha combinado.

Os textos passam a decidir a frase pelo que a marcação é. A condição vive no
modelo da mensagem, e não em código, porque é lá que alguém a pode reescrever
sem um deploy.

**O que já foi editado não se toca.** Um texto reescrito na área interna é uma
decisão de quem gere a clínica e vale mais do que o texto de fábrica.

Os modelos aprovados pela Meta ficam de fora de propósito: o texto aprovado não
muda por se mudar aqui, e um modelo com outro número de variáveis deixaria de
corresponder ao SID que já foi aprovado. Uma confirmação de domicílio enviada
por esse caminho continua a dizer a morada da clínica — para deixar de o dizer,
é preciso submeter um modelo novo à Meta.
"""

from django.db import migrations

from notifications.default_email_templates import DEFAULT_EMAIL_TEMPLATES
from notifications.default_messages import DEFAULT_MESSAGES
from notifications.english_messages import EMAIL_TEMPLATES_EN, WHATSAPP_MESSAGES_EN

CONFIRMACOES = ("appointment_confirmed", "appointment_confirmed_internal")


def nunca_editado(objeto):
    return objeto.updated_at == objeto.created_at


def semear_emails(apps):
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")

    for entrada in DEFAULT_EMAIL_TEMPLATES:
        if entrada["key"] not in CONFIRMACOES:
            continue

        modelo = EmailTemplate.objects.filter(key=entrada["key"]).first()

        if modelo is None or not nunca_editado(modelo):
            continue

        campos = {
            "body_text": entrada["body_text"],
            "body_html": entrada["body_html"],
        }

        versao_inglesa = EMAIL_TEMPLATES_EN.get(entrada["key"])

        if versao_inglesa:
            campos["body_text_en"] = versao_inglesa["body_text"]
            campos["body_html_en"] = versao_inglesa["body_html"]

        # update() e não save(): assim a linha continua a parecer o que é, uma
        # linha de fábrica, e uma migração futura pode voltar a atualizá-la.
        EmailTemplate.objects.filter(pk=modelo.pk).update(**campos)


def semear_whatsapp(apps):
    WhatsAppEventSetting = apps.get_model("notifications", "WhatsAppEventSetting")

    for entrada in DEFAULT_MESSAGES:
        if entrada["event_type"] not in CONFIRMACOES:
            continue

        regra = WhatsAppEventSetting.objects.filter(
            event_type=entrada["event_type"],
            audience=entrada["audience"],
        ).first()

        if regra is None or not nunca_editado(regra):
            continue

        # Só o texto livre: `meta_template_body` fica intacto, pelo motivo
        # explicado em cima.
        campos = {"body_template": entrada["body_template"]}

        texto_ingles = WHATSAPP_MESSAGES_EN.get(
            (entrada["event_type"], entrada["audience"])
        )

        if texto_ingles:
            campos["body_template_en"] = texto_ingles

        WhatsAppEventSetting.objects.filter(pk=regra.pk).update(**campos)


def semear(apps, schema_editor):
    semear_emails(apps)
    semear_whatsapp(apps)


def nada(apps, schema_editor):
    """Sem volta atrás.

    Reverter era repor o texto antigo, que diz a morada da clínica em todas as
    marcações — inclusive nas de domicílio que entretanto existam. O texto novo
    diz a mesma coisa que o antigo quando o atendimento é na clínica, portanto
    não há nada a desfazer.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0026_beforeaftercase_reveal_orientation"),
    ]

    operations = [
        migrations.RunPython(semear, nada),
    ]
