"""Envio de WhatsApp pelo Baileys.

O Baileys liga-se ao WhatsApp como um dispositivo emparelhado, à maneira do
WhatsApp Web. É por aqui que sai todo o WhatsApp desta casa, e o que isso quer
dizer:

- **não há modelos para aprovar** nem janela de 24 horas — texto livre sempre;
- **não há custo por mensagem**;
- **não há garantia de serviço**: quem envia é o número da clínica, e um uso
  abusivo pode dar-lhe um bloqueio.

Do lado de cá isto é só um cliente HTTP. A ligação vive no serviço Node em
`baileys/`, que a mantém aberta e guarda a sessão em disco.
"""

from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import IntegrityError

from notifications.models import WhatsAppEventSetting, WhatsAppMessageLog
from notifications.whatsapp_common import (
    SendResult,
    audience_language,
    build_context,
    get_sample_context,
    render_text,
    to_e164,
)

logger = logging.getLogger(__name__)

PROVIDER = WhatsAppMessageLog.PROVIDER_BAILEYS


# -----------------------------------------------------------------------------
# Cliente HTTP do serviço Node
# -----------------------------------------------------------------------------


class BaileysError(Exception):
    """Falha a falar com o serviço, ou falha reportada por ele."""


def validate_settings():
    if not settings.BAILEYS_API_URL:
        return "Falta BAILEYS_API_URL nas definições."

    if not settings.BAILEYS_API_TOKEN:
        return "Falta BAILEYS_API_TOKEN nas definições."

    return ""


def _call(path, payload=None, method="GET"):
    """Chama o serviço Node e devolve a resposta já descodificada.

    O corpo de erro do serviço traz sempre uma explicação em `error`. Sem o
    ler, tudo o que sobraria era "HTTP Error 409: Conflict" — que não diz a
    ninguém que o problema é o WhatsApp estar desligado.
    """

    url = f"{settings.BAILEYS_API_URL.rstrip('/')}{path}"

    corpo = json.dumps(payload).encode("utf-8") if payload is not None else None

    pedido = Request(
        url=url,
        data=corpo,
        headers={
            "X-Auth-Token": settings.BAILEYS_API_TOKEN,
            "Content-Type": "application/json",
        },
        method=method,
    )

    try:
        with urlopen(pedido, timeout=settings.BAILEYS_REQUEST_TIMEOUT) as resposta:
            return json.loads(resposta.read().decode("utf-8") or "{}")

    except HTTPError as erro:
        try:
            detalhe = json.loads(erro.read().decode("utf-8") or "{}")
        except (ValueError, OSError):
            detalhe = {}

        raise BaileysError(detalhe.get("error") or f"HTTP {erro.code}") from erro

    except URLError as erro:
        # O serviço não responde: container em baixo, nome errado, ou ainda a
        # arrancar. Vale a pena distinguir isto de uma recusa do WhatsApp.
        raise BaileysError(
            f"Serviço Baileys inacessível em {settings.BAILEYS_API_URL} "
            f"({erro.reason})."
        ) from erro

    except (TimeoutError, OSError) as erro:
        raise BaileysError(f"Falha de rede com o serviço Baileys: {erro}") from erro


def get_status():
    """Estado da ligação, como o serviço Node o vê.

    Nunca levanta exceção: é chamado por um ecrã que existe precisamente para
    mostrar que as coisas estão mal.
    """

    if not settings.BAILEYS_ENABLED:
        return {
            "state": "disabled",
            "qr": "",
            "me": None,
            "lastError": "O Baileys está desligado nas definições (BAILEYS_ENABLED).",
        }

    erro_config = validate_settings()

    if erro_config:
        return {
            "state": "misconfigured",
            "qr": "",
            "me": None,
            "lastError": erro_config,
        }

    try:
        return _call("/status")
    except BaileysError as erro:
        return {"state": "unreachable", "qr": "", "me": None, "lastError": str(erro)}


def logout():
    """Termina a sessão e apaga as credenciais, para ligar outro número."""

    return _call("/logout", payload={}, method="POST")


def restart():
    """Reabre a ligação sem perder a sessão emparelhada."""

    return _call("/restart", payload={}, method="POST")


def send_text(recipient, text):
    """Envia uma mensagem. Devolve a resposta do serviço."""

    return _call("/send", payload={"to": recipient, "text": text}, method="POST")


# -----------------------------------------------------------------------------
# Envio a partir das regras configuradas
# -----------------------------------------------------------------------------


def resolve_recipients(setting, appointment):
    """Números para onde esta regra envia, já normalizados."""

    if setting.audience == WhatsAppEventSetting.AUDIENCE_CUSTOMER:
        brutos = [appointment.customer.phone]

    elif setting.audience == WhatsAppEventSetting.AUDIENCE_PROFESSIONAL:
        brutos = [settings.BAILEYS_PROFESSIONAL_WHATSAPP]

    else:
        brutos = setting.custom_recipients.split(",")

    return [numero for numero in map(to_e164, brutos) if numero]


def build_body(setting, context, language=None):
    """O texto que vai sair, na língua de quem o vai ler.

    O Baileys não conhece modelos aprovados: o que sai é o texto escrito na
    regra. Sem versão inglesa configurada, sai o português.
    """

    return render_text(setting.for_language(language)["body"], context).strip()


def sent_logs(appointment, setting):
    """Envios bem sucedidos desta regra para esta marcação, do mais recente."""

    return WhatsAppMessageLog.objects.filter(
        appointment=appointment,
        provider=PROVIDER,
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
            provider=PROVIDER,
            audience=setting.audience,
            event_type=setting.event_type,
            status=status,
            template_name=setting.get_template_label(),
            recipient_phone=recipient,
            whatsapp_message_id=(response or {}).get("id", ""),
            request_payload=json.dumps(payload, ensure_ascii=False),
            response_payload=json.dumps(response or {}, ensure_ascii=False),
            error_message=error,
        )
    except IntegrityError:
        # A restrição de unicidade cobre a corrida entre dois pedidos que
        # tentem o mesmo envio ao mesmo tempo.
        return None


def send_for_setting(appointment, setting, force=False, override=None):
    """Envia esta regra para todos os destinatários dela.

    Com `force`, repete um envio que já tinha corrido bem. É o que o botão de
    envio manual precisa: quem carrega nele quer que a mensagem saia outra vez.

    `override` é o que a janela de confirmação mudou para este envio. Só se
    aplica às regras que falam com a cliente: o aviso interno à profissional
    sai sempre como está escrito, em português, porque quem o lê é sempre a
    mesma pessoa e não foi essa a mensagem que alguém esteve a rever no ecrã.
    """

    destinatarios = resolve_recipients(setting, appointment)

    if not destinatarios:
        return SendResult(
            success=False,
            message=f"{setting}: nenhum número válido para enviar.",
        )

    para_a_cliente = setting.audience == setting.AUDIENCE_CUSTOMER
    manda_no_texto = bool(override and para_a_cliente)

    lingua = audience_language(setting, appointment)

    if manda_no_texto:
        lingua = override.language_or(lingua)

    if manda_no_texto and override.whatsapp_body:
        texto = override.whatsapp_body
    else:
        texto = build_body(setting, build_context(appointment, lingua), language=lingua)

    if not texto:
        return SendResult(
            success=False,
            message=(
                f"{setting}: a mensagem está vazia. O Baileys envia texto "
                "livre, por isso o campo Mensagem tem de estar preenchido."
            ),
        )

    registos = []
    falhas = []

    for destinatario in destinatarios:
        if not force and already_sent(appointment, setting, destinatario):
            continue

        payload = {"to": destinatario, "text": texto}

        try:
            resposta = send_text(destinatario, texto)
        except BaileysError as erro:
            detalhe = str(erro)
            falhas.append(detalhe)
            logger.warning("Baileys falhou para %s: %s", destinatario, detalhe)

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
        return SendResult(success=False, message="; ".join(falhas), logs=registos)

    if not registos:
        return SendResult(
            success=True,
            skipped=True,
            message="Mensagem já tinha sido enviada.",
        )

    return SendResult(
        success=True,
        message=f"{len(registos)} mensagem(ns) entregue(s) ao WhatsApp.",
        logs=registos,
    )


def send_manual(appointment, setting):
    """Envia esta mensagem agora, para esta marcação.

    Ao contrário do disparo automático, não olha para o interruptor da regra:
    quem carrega no botão já decidiu.
    """

    if not settings.BAILEYS_ENABLED:
        return SendResult(False, "O Baileys está desativado nas definições.")

    erro_config = validate_settings()

    if erro_config:
        return SendResult(False, erro_config)

    try:
        return send_for_setting(appointment, setting, force=True)
    except Exception as erro:
        logger.exception("Erro inesperado no envio manual de %s", setting)
        return SendResult(False, str(erro))


def send_test(setting, recipient):
    """Envio de teste, com dados de exemplo.

    Não fica no histórico: o histórico é por marcação, e este envio não tem
    nenhuma. Serve para confirmar que a ligação está de pé antes de a regra
    apanhar um cliente real.
    """

    if not settings.BAILEYS_ENABLED:
        return SendResult(False, "O Baileys está desativado nas definições.")

    erro_config = validate_settings()

    if erro_config:
        return SendResult(False, erro_config)

    destino = to_e164(recipient)

    if not destino:
        return SendResult(False, "Número de destino inválido.")

    texto = build_body(setting, get_sample_context())

    if not texto:
        return SendResult(
            False,
            "A mensagem está vazia. O Baileys envia texto livre, por isso o "
            "campo Mensagem tem de estar preenchido.",
        )

    try:
        resposta = send_text(destino, texto)
    except BaileysError as erro:
        return SendResult(False, str(erro))

    return SendResult(
        True,
        f"Teste entregue ao WhatsApp para {destino} (id {resposta.get('id') or '—'}).",
    )
