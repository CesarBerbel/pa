"""Envio de WhatsApp pela Twilio.

Usa a API REST diretamente, com `urllib`, à semelhança do que já se faz para o
WhatsApp Cloud API. É um único endpoint; trazer o SDK da Twilio seria mais uma
dependência para manter por causa de um POST.

**Mensagens iniciadas pela clínica precisam de um modelo aprovado.** Tudo o que
sai daqui — pedido recebido, marcação confirmada, marcação cancelada — parte da
clínica, não de uma resposta do cliente. A Twilio só aceita texto livre nas 24
horas seguintes a uma mensagem do destinatário; fora dessa janela devolve o
erro 63016 e a mensagem não chega. Por isso cada regra pode ter um Content SID,
e o texto livre serve sobretudo para o sandbox de testes.
"""

from __future__ import annotations

import base64
import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import IntegrityError

from notifications.models import WhatsAppEventSetting, WhatsAppMessageLog
from notifications.twilio_callbacks import status_callback_url
from notifications.whatsapp_common import (
    SendResult,
    audience_language,
    build_context,
    get_sample_context,
    render_text,
    to_e164,
)

logger = logging.getLogger(__name__)

API_ROOT = "https://api.twilio.com/2010-04-01"

# O nome antigo, de quando a Twilio era o único caminho. Mantido para não
# obrigar quem chama a mudar por causa de uma mudança de nome.
TwilioSendResult = SendResult


def normalize_whatsapp_address(phone):
    """Passa um número para o formato que a Twilio espera: whatsapp:+351...

    Devolve string vazia quando não há número aproveitável, para quem chama
    poder registar a falha em vez de enviar para lado nenhum.
    """

    numero = to_e164(phone)

    return f"whatsapp:{numero}" if numero else ""


def validate_settings():
    if not settings.TWILIO_ACCOUNT_SID:
        return "Falta TWILIO_ACCOUNT_SID nas definições."

    if not settings.TWILIO_AUTH_TOKEN:
        return "Falta TWILIO_AUTH_TOKEN nas definições."

    if not normalize_whatsapp_address(settings.TWILIO_WHATSAPP_FROM):
        return "TWILIO_WHATSAPP_FROM não é um número válido."

    return ""


def resolve_recipients(setting, appointment):
    """Números para onde esta regra envia, já normalizados."""

    if setting.audience == WhatsAppEventSetting.AUDIENCE_CUSTOMER:
        brutos = [appointment.customer.phone]

    elif setting.audience == WhatsAppEventSetting.AUDIENCE_PROFESSIONAL:
        brutos = [settings.TWILIO_PROFESSIONAL_WHATSAPP]

    else:
        brutos = setting.custom_recipients.split(",")

    return [numero for numero in map(normalize_whatsapp_address, brutos) if numero]


def build_payload(setting, context, recipient, language=None):
    payload = {
        "From": normalize_whatsapp_address(settings.TWILIO_WHATSAPP_FROM),
        "To": recipient,
    }

    # Sem isto a Twilio nunca nos diz se a mensagem chegou, e o sistema fica a
    # afirmar "enviada" para uma mensagem que falhou na entrega.
    callback = status_callback_url()

    if callback:
        payload["StatusCallback"] = callback

    # A Meta aprova um modelo por língua, cada um com o seu identificador: não
    # há como traduzir um modelo aprovado no momento do envio. Sem um inglês
    # aprovado, `for_language` devolve o português.
    versao = setting.for_language(language)

    if versao["content_sid"].strip():
        payload["ContentSid"] = versao["content_sid"].strip()

        if setting.content_variables.strip():
            posicoes = json.loads(setting.content_variables)

            payload["ContentVariables"] = json.dumps(
                {
                    str(chave): render_text(str(valor), context)
                    for chave, valor in posicoes.items()
                }
            )

        return payload

    payload["Body"] = render_text(versao["body"], context)

    return payload


def post_message(payload):
    """Envia e devolve a resposta da Twilio já descodificada."""

    credenciais = base64.b64encode(
        f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}".encode()
    ).decode()

    pedido = Request(
        url=f"{API_ROOT}/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
        data=urlencode(payload).encode("utf-8"),
        headers={
            "Authorization": f"Basic {credenciais}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    with urlopen(pedido, timeout=settings.TWILIO_REQUEST_TIMEOUT) as resposta:
        return json.loads(resposta.read().decode("utf-8") or "{}")


def format_error(erro):
    """Mensagem legível a partir do que a Twilio devolveu.

    O corpo do erro traz o código e uma explicação; sem o ler, tudo o que
    sobraria era "HTTP Error 400: Bad Request".
    """

    if isinstance(erro, HTTPError):
        try:
            corpo = json.loads(erro.read().decode("utf-8") or "{}")
        except (ValueError, OSError):
            return f"HTTP {erro.code}"

        codigo = corpo.get("code")
        detalhe = corpo.get("message") or f"HTTP {erro.code}"

        if codigo == 63016:
            return (
                f"{detalhe} (código 63016: fora da janela de 24 horas, é "
                "preciso um modelo aprovado)"
            )

        return f"{detalhe} (código {codigo})" if codigo else detalhe

    if isinstance(erro, URLError):
        return f"Falha de rede: {erro.reason}"

    return str(erro)


def sent_logs(appointment, setting):
    """Envios bem sucedidos desta regra para esta marcação, do mais recente."""

    return WhatsAppMessageLog.objects.filter(
        appointment=appointment,
        provider=WhatsAppMessageLog.PROVIDER_TWILIO,
        event_type=setting.event_type,
        audience=setting.audience,
        status=WhatsAppMessageLog.STATUS_SUCCESS,
    ).order_by("-sent_at")


def already_sent(appointment, setting, recipient):
    return sent_logs(appointment, setting).filter(recipient_phone=recipient).exists()


def _record(appointment, setting, recipient, status, payload, response, error=""):
    try:
        return WhatsAppMessageLog.objects.create(
            appointment=appointment,
            provider=WhatsAppMessageLog.PROVIDER_TWILIO,
            audience=setting.audience,
            event_type=setting.event_type,
            status=status,
            template_name=setting.get_template_label(),
            recipient_phone=recipient,
            whatsapp_message_id=(response or {}).get("sid", ""),
            request_payload=json.dumps(payload, ensure_ascii=False),
            response_payload=json.dumps(response or {}, ensure_ascii=False),
            error_message=error,
        )
    except IntegrityError:
        # A restrição de unicidade cobre a corrida entre dois pedidos que
        # tentem o mesmo envio ao mesmo tempo.
        return None


def send_for_setting(appointment, setting, force=False):
    """Envia esta regra para todos os destinatários dela.

    Com `force`, repete um envio que já tinha corrido bem. É o que o botão de
    envio manual precisa: quando alguém carrega nele, é porque quer que a
    mensagem saia outra vez.
    """

    destinatarios = resolve_recipients(setting, appointment)

    if not destinatarios:
        return TwilioSendResult(
            success=False,
            message=f"{setting}: nenhum número válido para enviar.",
        )

    lingua = audience_language(setting, appointment)
    contexto = build_context(appointment, lingua)
    registos = []
    falhas = []

    for destinatario in destinatarios:
        if not force and already_sent(appointment, setting, destinatario):
            continue

        payload = build_payload(
            setting,
            contexto,
            destinatario,
            language=lingua,
        )

        try:
            resposta = post_message(payload)
        except Exception as erro:
            detalhe = format_error(erro)
            falhas.append(detalhe)
            logger.warning("Twilio falhou para %s: %s", destinatario, detalhe)

            _record(
                appointment,
                setting,
                destinatario,
                WhatsAppMessageLog.STATUS_ERROR,
                payload,
                {},
                detalhe,
            )
            continue

        registos.append(
            _record(
                appointment,
                setting,
                destinatario,
                WhatsAppMessageLog.STATUS_SUCCESS,
                payload,
                resposta,
            )
        )

    if falhas:
        return TwilioSendResult(
            success=False,
            message="; ".join(falhas),
            logs=registos,
        )

    if not registos:
        return TwilioSendResult(
            success=True,
            skipped=True,
            message="Mensagem já tinha sido enviada.",
        )

    return TwilioSendResult(
        success=True,
        message=f"{len(registos)} mensagem(ns) aceite(s) pela Twilio.",
        logs=registos,
    )


def send_manual(appointment, setting):
    """Envia esta mensagem agora, para esta marcação.

    Ao contrário do disparo automático, não olha para o acontecimento nem para
    o interruptor da regra: quem carrega no botão já decidiu. O que continua a
    valer são as credenciais e as regras da Twilio.
    """

    if not settings.TWILIO_ENABLED:
        return TwilioSendResult(False, "A Twilio está desativada nas definições.")

    erro_config = validate_settings()

    if erro_config:
        return TwilioSendResult(False, erro_config)

    try:
        return send_for_setting(appointment, setting, force=True)
    except Exception as erro:
        logger.exception("Erro inesperado no envio manual de %s", setting)
        return TwilioSendResult(False, format_error(erro))


def send_test(setting, recipient):
    """Envio de teste, com dados de exemplo.

    Não fica no histórico: o histórico é por marcação, e este envio não tem
    nenhuma. Serve para descobrir uma credencial errada ou um modelo por
    aprovar antes de a configuração apanhar um cliente real.
    """

    if not settings.TWILIO_ENABLED:
        return TwilioSendResult(False, "A Twilio está desativada nas definições.")

    erro_config = validate_settings()

    if erro_config:
        return TwilioSendResult(False, erro_config)

    destino = normalize_whatsapp_address(recipient)

    if not destino:
        return TwilioSendResult(False, "Número de destino inválido.")

    try:
        payload = build_payload(setting, get_sample_context(), destino)
        resposta = post_message(payload)
    except Exception as erro:
        return TwilioSendResult(False, format_error(erro))

    return TwilioSendResult(
        True,
        f"Teste aceite pela Twilio para {destino} "
        f"(sid {resposta.get('sid', '—')}). A entrega é confirmada depois.",
    )
