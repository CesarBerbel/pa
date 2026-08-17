"""Encaminha cada regra de WhatsApp para o fornecedor que ela escolheu.

Este é o único ponto por onde as marcações disparam mensagens. O que muda de
regra para regra é o transporte — Twilio ou Baileys — e é isso que aqui se
decide, para as marcações não terem de saber que existe mais do que um.

Cada fornecedor pode estar desligado nas definições (`TWILIO_ENABLED`,
`BAILEYS_ENABLED`). Uma regra que aponte para um fornecedor desligado não é
erro: é uma regra à espera, e o ecrã de configuração mostra-a como tal.
"""

from __future__ import annotations

import logging

from django.conf import settings

from notifications import baileys_whatsapp, twilio_whatsapp
from notifications.models import MessagingSetting, WhatsAppEventSetting
from notifications.whatsapp_common import SendResult

logger = logging.getLogger(__name__)

MESSAGING_OFF = (
    "O envio de mensagens está desligado nas configurações. "
    "Nada foi enviado."
)


def messaging_off_result():
    """Resposta única para quando o interruptor geral está desligado.

    É sucesso e não falha: não enviar foi o que se pediu. Vai como `skipped`
    para os ecrãs poderem dizer que não saiu nada, em vez de darem a entender
    que a mensagem seguiu.
    """

    return SendResult(True, MESSAGING_OFF, skipped=True)

PROVIDERS = {
    WhatsAppEventSetting.PROVIDER_TWILIO: twilio_whatsapp,
    WhatsAppEventSetting.PROVIDER_BAILEYS: baileys_whatsapp,
}


def provider_module(setting):
    return PROVIDERS.get(setting.provider, twilio_whatsapp)


def provider_enabled(provider):
    if provider == WhatsAppEventSetting.PROVIDER_BAILEYS:
        return settings.BAILEYS_ENABLED

    return settings.TWILIO_ENABLED


def provider_error(setting):
    """Porque é que esta regra não pode enviar agora, se for o caso.

    Devolve string vazia quando está tudo em ordem. Usado pelo ecrã de
    configuração para explicar o que falta a uma regra que parece ligada.
    """

    if not provider_enabled(setting.provider):
        return (
            f"{setting.get_provider_display()} está desligado nas definições "
            "do servidor."
        )

    return provider_module(setting).validate_settings()


def resolve_recipients(setting, appointment):
    """Números desta regra, normalizados como o fornecedor dela precisa."""

    return provider_module(setting).resolve_recipients(setting, appointment)


def sent_logs(appointment, setting):
    return provider_module(setting).sent_logs(appointment, setting)


def send_manual(appointment, setting):
    """Dispara esta regra agora, para esta marcação."""

    if not MessagingSetting.messaging_enabled():
        return messaging_off_result()

    return provider_module(setting).send_manual(appointment, setting)


def send_test(setting, recipient):
    """Envio de teste com dados de exemplo, pelo fornecedor da regra."""

    # O teste também é uma mensagem que chega ao telemóvel de alguém, e por
    # isso está sujeito ao interruptor como os outros envios.
    if not MessagingSetting.messaging_enabled():
        return messaging_off_result()

    return provider_module(setting).send_test(setting, recipient)


def notify(appointment, event_type):
    """Dispara todas as regras ativas para este acontecimento.

    Nunca levanta exceção: uma falha de envio não pode desfazer uma marcação
    que já foi gravada.
    """

    if not MessagingSetting.messaging_enabled():
        return messaging_off_result()

    regras = WhatsAppEventSetting.objects.filter(
        event_type=event_type,
        is_active=True,
    )

    if not regras:
        return SendResult(
            True, "Nenhuma regra ativa para este acontecimento.", skipped=True
        )

    mensagens = []
    registos = []
    houve_falha = False
    ignoradas = 0

    for regra in regras:
        # Desligado é uma decisão de quem administra: nada a enviar, nada a
        # reportar.
        if not provider_enabled(regra.provider):
            ignoradas += 1
            continue

        # Ligado mas mal configurado é outra coisa. Uma credencial em falta
        # calada é uma mensagem que ninguém percebe que não saiu.
        erro_config = provider_module(regra).validate_settings()

        if erro_config:
            logger.warning(
                "%s mal configurado: %s", regra.get_provider_display(), erro_config
            )
            houve_falha = True
            mensagens.append(erro_config)
            continue

        try:
            resultado = provider_module(regra).send_for_setting(appointment, regra)
        except Exception as erro:
            logger.exception("Erro inesperado a enviar %s", regra)
            houve_falha = True
            mensagens.append(f"{regra}: {erro}")
            continue

        registos.extend(resultado.logs)

        if not resultado.success:
            houve_falha = True
            mensagens.append(resultado.message)

    if houve_falha:
        # Uma credencial em falta afeta todas as regras do mesmo fornecedor e
        # repetiria a mesma frase tantas vezes quantas as regras.
        unicas = list(dict.fromkeys(mensagens))

        return SendResult(False, "; ".join(unicas), logs=registos)

    if not registos:
        if ignoradas:
            return SendResult(
                True,
                f"{ignoradas} regra(s) por enviar: fornecedor desligado ou mal "
                "configurado.",
                skipped=True,
            )

        return SendResult(True, "Nada por enviar.", skipped=True, logs=registos)

    return SendResult(True, f"{len(registos)} mensagem(ns) enviada(s).", logs=registos)
