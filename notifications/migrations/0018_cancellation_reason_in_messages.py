"""Põe o motivo nas mensagens de cancelamento do WhatsApp.

O email já o dizia; o WhatsApp não. Quem recebe "a sua marcação foi cancelada"
sem mais nada fica sem saber se foi engano, se foi doença da profissional, ou
se foi o cancelamento que a própria pediu.

Só mexe nas regras cujo texto ainda é exatamente o que o sistema instalou, e
nunca numa regra com Content SID preenchido: esse texto foi aprovado pela Meta
e mudá-lo por baixo do SID faria sair uma mensagem diferente da aprovada. Nesses
casos o texto novo tem de ser submetido à mão, e a variável já lá está para ser
usada.
"""

import json

from django.db import migrations

from notifications.default_messages import DEFAULT_MESSAGES

# Textos anteriores, tal como a migração 0017 os deixou.
TEXTOS_ANTERIORES = {
    ("appointment_cancelled", "customer"): (
        "Olá {{ customer_name }}, a sua marcação de {{ service_name }}, "
        "de {{ appointment_date }} às {{ appointment_time }}, foi "
        "cancelada e o horário ficou livre. A referência era "
        "{{ reference_code }}. Quando quiser remarcar, escolha um horário "
        "em {{ booking_link }} ou responda a esta mensagem — teremos todo "
        "o gosto em recebê-la."
    ),
    ("appointment_cancelled", "professional"): (
        "Marcação cancelada: {{ customer_name }} — {{ service_name }}, "
        "{{ appointment_date }} às {{ appointment_time }}. Contacto da "
        "cliente: {{ customer_phone }}. Referência {{ reference_code }}. "
        "O horário voltou a ficar livre na agenda."
    ),
}


def catalogo():
    return {
        (entrada["event_type"], entrada["audience"]): entrada
        for entrada in DEFAULT_MESSAGES
    }


def acrescentar_motivo(apps, schema_editor):
    WhatsAppEventSetting = apps.get_model("notifications", "WhatsAppEventSetting")
    novos = catalogo()

    for chave, texto_anterior in TEXTOS_ANTERIORES.items():
        entrada = novos.get(chave)

        if not entrada:
            continue

        event_type, audience = chave

        WhatsAppEventSetting.objects.filter(
            event_type=event_type,
            audience=audience,
            body_template=texto_anterior,
            content_sid="",
        ).update(
            body_template=entrada["body_template"],
            meta_template_body=entrada.get("meta_template_body", ""),
            content_variables=json.dumps(
                entrada.get("content_variables", {}), ensure_ascii=False, indent=2
            ),
        )


def retirar_motivo(apps, schema_editor):
    WhatsAppEventSetting = apps.get_model("notifications", "WhatsAppEventSetting")
    novos = catalogo()

    for chave, texto_anterior in TEXTOS_ANTERIORES.items():
        entrada = novos.get(chave)

        if not entrada:
            continue

        event_type, audience = chave

        WhatsAppEventSetting.objects.filter(
            event_type=event_type,
            audience=audience,
            body_template=entrada["body_template"],
            content_sid="",
        ).update(body_template=texto_anterior)


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0017_seed_message_catalogue"),
    ]

    operations = [
        migrations.RunPython(acrescentar_motivo, retirar_motivo),
    ]
