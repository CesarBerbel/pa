"""Peças partilhadas pelos fornecedores de WhatsApp.

A Twilio e o Baileys diferem no transporte — uma é uma API REST com modelos
aprovados, o outro é uma sessão emparelhada — mas concordam no resto: o mesmo
texto, as mesmas variáveis, os mesmos números. Este módulo guarda essa parte
comum, para uma correção no formato de um número não ter de ser feita duas
vezes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.conf import settings
from django.template import Context, Template
from django.urls import reverse


@dataclass
class SendResult:
    """Resultado de um envio, seja qual for o fornecedor.

    `skipped` distingue "não havia nada para enviar" de "enviou-se": as duas
    situações são sucesso, mas só uma delas põe mensagens no telemóvel de
    alguém.
    """

    success: bool
    message: str
    skipped: bool = False
    logs: list = field(default_factory=list)


def to_e164(phone):
    """Reduz um número ao formato internacional: +351912345678.

    Aceita o que vier do formulário — espaços, parênteses, o prefixo
    `whatsapp:` — e devolve string vazia quando não sobra um número
    aproveitável, para quem chama poder registar a falha em vez de enviar para
    lado nenhum.
    """

    bruto = (phone or "").strip()

    if bruto.startswith("whatsapp:"):
        bruto = bruto[len("whatsapp:") :]

    digitos = re.sub(r"[^\d+]", "", bruto)

    if not digitos:
        return ""

    if not digitos.startswith("+"):
        digitos = f"+{digitos}"

    # Nove dígitos é o número nacional mais curto que faz sentido; abaixo
    # disso é lixo ou um campo meio preenchido.
    if len(digitos) < 9:
        return ""

    return digitos


def render_text(texto, context):
    if not texto:
        return ""

    return Template(texto).render(Context(context))


def appointment_link(reference_code):
    """Endereço público onde a marcação se abre, pronto a clicar.

    Absoluto e não relativo: uma mensagem de WhatsApp não tem página de onde
    partir, e um `/consultar/...` sozinho não é clicável em lado nenhum.
    """

    caminho = reverse(
        "appointments:public_appointment_by_code",
        kwargs={"reference_code": reference_code},
    )

    return f"{settings.SITE_URL}{caminho}"


def booking_link():
    """Página onde se escolhe um horário novo.

    A mensagem de cancelamento precisa dela: apontar para a marcação que
    acabou de cair não serve de nada a quem quer remarcar.
    """

    return f"{settings.SITE_URL}{reverse('appointments:public_visual_schedule')}"


def build_context(appointment):
    return {
        "customer_name": appointment.customer.full_name,
        "customer_phone": appointment.customer.phone,
        "service_name": appointment.service.name,
        "appointment_date": appointment.date.strftime("%d/%m/%Y"),
        "appointment_time": appointment.start_time.strftime("%H:%M"),
        "reference_code": appointment.reference_code,
        "status": appointment.get_status_display(),
        "appointment_link": appointment_link(appointment.reference_code),
        "booking_link": booking_link(),
        # Fica disponível para quem escreva um texto à medida. As mensagens de
        # fábrica não a usam: um modelo aprovado pela Meta não aceita uma
        # variável vazia, e a maior parte dos cancelamentos não traz motivo.
        "cancellation_reason": appointment.cancellation_reason,
    }


def get_sample_context():
    return {
        "customer_name": "Maria Silva",
        "customer_phone": "+351910000000",
        "service_name": "Remoção de calos",
        "appointment_date": "18/08/2026",
        "appointment_time": "10:30",
        "reference_code": "AGD-EXEMPLO",
        "status": "Confirmada",
        "appointment_link": appointment_link("AGD-EXEMPLO"),
        "booking_link": booking_link(),
        "cancellation_reason": "A cliente informou que não poderá comparecer.",
    }
