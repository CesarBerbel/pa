"""Põe o catálogo de mensagens completo: os que faltavam e os que foram reescritos.

Passam a existir, além do que já cá estava:

* o aviso por email à profissional, no pedido novo e no cancelamento — até aqui
  esses avisos só saíam por WhatsApp, e um WhatsApp desligado era um pedido que
  ficava sem ninguém a saber;
* a confirmação de uma marcação combinada na clínica, dita de outra maneira que
  a resposta a um pedido feito no site;
* o agradecimento do fim do atendimento, por email;
* dois modelos por serviço — o seguimento de uns dias depois e o texto de
  recomendações que se manda à mão — que ficam à espera de ser escolhidos numa
  mensagem de serviço.

**O que já foi editado não se toca.** Um texto reescrito na área interna é uma
decisão de quem gere a clínica e vale mais do que o texto de fábrica. A prova
de que nunca foi editado é `updated_at == created_at`: as migrações anteriores
mexeram nas linhas com `update()`, que não mexe nesses campos, mas qualquer
gravação feita num ecrã mexe.

As regras de WhatsApp novas nascem desligadas, como as outras: o texto está
pronto, mas nada sai antes de alguém o rever e submeter o modelo à Meta.
"""

import json

from django.db import migrations

from notifications.default_email_templates import DEFAULT_EMAIL_TEMPLATES
from notifications.default_messages import DEFAULT_MESSAGES


def nunca_editado(objeto):
    return objeto.updated_at == objeto.created_at


def semear_emails(apps):
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")
    EmailEventSetting = apps.get_model("notifications", "EmailEventSetting")

    for entrada in DEFAULT_EMAIL_TEMPLATES:
        campos = {
            "name": entrada["name"],
            "subject": entrada["subject"],
            "body_text": entrada["body_text"],
            "body_html": entrada["body_html"],
        }

        modelo = EmailTemplate.objects.filter(key=entrada["key"]).first()

        if modelo is None:
            modelo = EmailTemplate.objects.create(
                key=entrada["key"], is_active=True, **campos
            )
        elif nunca_editado(modelo):
            # update() e não save(): assim a linha continua a parecer o que é,
            # uma linha de fábrica, e uma migração futura pode voltar a
            # atualizá-la sem pisar ninguém.
            EmailTemplate.objects.filter(pk=modelo.pk).update(**campos)

        if not entrada.get("event_type"):
            # Os modelos por serviço não pertencem a acontecimento nenhum:
            # ficam disponíveis para quem criar a mensagem do serviço.
            continue

        regra, criada = EmailEventSetting.objects.get_or_create(
            event_type=entrada["event_type"],
            audience=entrada["audience"],
            defaults={
                "name": entrada["name"],
                "email_template": modelo,
                "is_active": True,
            },
        )

        # Uma regra que já aponta para outro modelo foi decidida por alguém.
        if not criada and regra.email_template_id is None:
            EmailEventSetting.objects.filter(pk=regra.pk).update(email_template=modelo)


def semear_whatsapp(apps):
    WhatsAppEventSetting = apps.get_model("notifications", "WhatsAppEventSetting")

    for entrada in DEFAULT_MESSAGES:
        campos = {
            "body_template": entrada["body_template"],
            "meta_template_body": entrada.get("meta_template_body", ""),
            "content_variables": json.dumps(
                entrada.get("content_variables", {}), ensure_ascii=False, indent=2
            ),
        }

        regra = WhatsAppEventSetting.objects.filter(
            event_type=entrada["event_type"],
            audience=entrada["audience"],
        ).first()

        if regra is None:
            WhatsAppEventSetting.objects.create(
                event_type=entrada["event_type"],
                audience=entrada["audience"],
                is_active=False,
                **campos,
            )
            continue

        # Um modelo já aprovado pela Meta não pode mudar de texto por baixo do
        # SID: o que sairia deixava de corresponder ao que foi aprovado.
        if nunca_editado(regra) and not regra.content_sid:
            WhatsAppEventSetting.objects.filter(pk=regra.pk).update(**campos)


def semear(apps, schema_editor):
    semear_emails(apps)
    semear_whatsapp(apps)


def limpar(apps, schema_editor):
    """Desfaz apenas o que esta migração acrescentou e ninguém estreou."""

    EmailTemplate = apps.get_model("notifications", "EmailTemplate")
    EmailEventSetting = apps.get_model("notifications", "EmailEventSetting")
    WhatsAppEventSetting = apps.get_model("notifications", "WhatsAppEventSetting")

    novos = [
        "appointment_created_professional",
        "appointment_confirmed_internal",
        "appointment_cancelled_professional",
        "appointment_completed",
        "service_followup",
        "service_manual",
    ]

    EmailEventSetting.objects.filter(email_template__key__in=novos).delete()
    EmailTemplate.objects.filter(key__in=novos, follow_ups__isnull=True).delete()

    WhatsAppEventSetting.objects.filter(
        event_type="appointment_confirmed_internal",
        is_active=False,
        content_sid="",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0016_service_message_triggers_and_email_audience"),
    ]

    operations = [
        migrations.RunPython(semear, limpar),
    ]
