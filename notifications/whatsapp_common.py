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


def cancellation_reason(appointment):
    """O motivo do cancelamento, pronto a entrar no meio de uma frase.

    Duas correções, ambas por causa de quem o escreve à mão:

    * sai sem o ponto final, porque a mensagem já o põe a seguir — uns motivos
      vêm com ponto, outros sem, e sem isto metade das mensagens dizia
      "não poderá comparecer..";
    * nunca sai vazio, porque um modelo aprovado pela Meta é recusado se uma
      das posições chegar em branco. O cancelamento exige motivo, portanto
      isto quase nunca serve de nada — mas "quase" não chega quando o custo é
      a mensagem não sair.
    """

    motivo = (appointment.cancellation_reason or "").strip().rstrip(".").strip()

    return motivo or "não indicado"


def audience_language(setting, appointment):
    """A língua desta mensagem.

    À cliente fala-se na língua dela; à profissional fala-se sempre
    português, seja qual for a da cliente — quem lê os avisos internos é
    sempre a mesma pessoa.
    """

    if setting.audience != setting.AUDIENCE_CUSTOMER:
        return "pt-pt"

    # A marcação vem primeiro: a língua guardada na cliente é a da última vez
    # que ela marcou, e muda debaixo das marcações que já existem.
    if getattr(appointment, "customer_speaks_english", False):
        return "en"

    cliente = getattr(appointment, "customer", None)

    return getattr(cliente, "language", "") or "pt-pt"


def build_context(appointment, language=None):
    """As variáveis da mensagem, já na língua em que ela vai ser escrita.

    O nome do serviço está guardado na base de dados e não passa pelo gettext:
    é aqui que se escolhe. Sem a língua, uma confirmação inglesa dizia "your
    appointment for Pedicure terapêutica" — metade traduzida.

    Fica a `None` — português — para os avisos à profissional.
    """

    return {
        "customer_name": appointment.customer.full_name,
        "customer_phone": appointment.customer.phone,
        "service_name": appointment.service.name_for_language(language),
        "appointment_date": appointment.date.strftime("%d/%m/%Y"),
        "appointment_time": appointment.start_time.strftime("%H:%M"),
        "reference_code": appointment.reference_code,
        "status": appointment.get_status_display(),
        "appointment_link": appointment_link(appointment.reference_code),
        "booking_link": booking_link(),
        "cancellation_reason": cancellation_reason(appointment),
        "is_home_visit": appointment.is_home_visit,
        "home_address": appointment.home_address.strip(),
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
        "is_home_visit": False,
        "home_address": "",
        "appointment_link": appointment_link("AGD-EXEMPLO"),
        "booking_link": booking_link(),
        "cancellation_reason": "A cliente informou que não poderá comparecer.",
    }
