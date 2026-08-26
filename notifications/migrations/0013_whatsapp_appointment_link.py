"""Acrescenta o link da marcação às mensagens de WhatsApp para o cliente.

Só mexe nas regras cujo texto ainda é exatamente o que o sistema instalou. Se
alguém reescreveu a mensagem, o que lá está é uma decisão de quem gere a
clínica e vale mais do que o texto de fábrica — nesses casos a variável fica
disponível e é acrescentada à mão, na página da regra.
"""

import json

from django.db import migrations

from notifications.default_messages import DEFAULT_MESSAGES

# Textos anteriores, tal como as migrações de seed os deixaram. São a prova de
# que a regra nunca foi editada.
TEXTOS_ANTERIORES = {
    ("appointment_requested", "customer"): (
        "Olá {{ customer_name }}, recebemos o seu pedido de marcação para "
        "{{ service_name }}, no dia {{ appointment_date }} às "
        "{{ appointment_time }}. A referência é {{ reference_code }}. "
        "Entraremos em contacto assim que estiver confirmado."
    ),
    ("appointment_confirmed", "customer"): (
        "Olá {{ customer_name }}, a sua marcação de {{ service_name }} "
        "está confirmada para {{ appointment_date }} às "
        "{{ appointment_time }}. Referência {{ reference_code }}. "
        "Se precisar de alterar, responda a esta mensagem."
    ),
}


def novos_textos():
    return {
        (entrada["event_type"], entrada["audience"]): entrada
        for entrada in DEFAULT_MESSAGES
    }


def acrescentar_link(apps, schema_editor):
    WhatsAppEventSetting = apps.get_model("notifications", "WhatsAppEventSetting")
    catalogo = novos_textos()

    for chave, texto_anterior in TEXTOS_ANTERIORES.items():
        event_type, audience = chave
        entrada = catalogo.get(chave)

        if not entrada:
            continue

        WhatsAppEventSetting.objects.filter(
            event_type=event_type,
            audience=audience,
            body_template=texto_anterior,
        ).update(
            body_template=entrada["body_template"],
            meta_template_body=entrada.get("meta_template_body", ""),
            content_variables=json.dumps(
                entrada.get("content_variables", {}), ensure_ascii=False, indent=2
            ),
        )


def retirar_link(apps, schema_editor):
    WhatsAppEventSetting = apps.get_model("notifications", "WhatsAppEventSetting")
    catalogo = novos_textos()

    for chave, texto_anterior in TEXTOS_ANTERIORES.items():
        event_type, audience = chave
        entrada = catalogo.get(chave)

        if not entrada:
            continue

        WhatsAppEventSetting.objects.filter(
            event_type=event_type,
            audience=audience,
            body_template=entrada["body_template"],
        ).update(body_template=texto_anterior)


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0012_messagingsetting"),
    ]

    operations = [
        migrations.RunPython(acrescentar_link, retirar_link),
    ]
