"""Encaminha as regras de WhatsApp para quem as envia.

Este é o único ponto por onde as marcações disparam mensagens de WhatsApp, e é
por isso que continua a existir mesmo depois de o transporte ter passado a ser
um só: as marcações não têm de saber qual é, e trocá-lo — ou voltar a ter
dois — é uma alteração deste ficheiro e de mais nenhum.

O envio pode estar desligado nas definições (`BAILEYS_ENABLED`). Uma regra
ligada com o envio desligado não é erro: é uma regra à espera, e o ecrã de
configuração mostra-a como tal.
"""

from __future__ import annotations

import logging

from django.conf import settings

from notifications import baileys_whatsapp
from notifications.models import MessagingSetting, WhatsAppEventSetting
from notifications.whatsapp_common import (
    SendResult,
    audience_language,
    build_context,
)

logger = logging.getLogger(__name__)

MESSAGING_OFF = (
    "O envio de WhatsApp está desligado nas configurações. Nada foi enviado."
)


def messaging_off_result():
    """Resposta única para quando o interruptor geral está desligado.

    É sucesso e não falha: não enviar foi o que se pediu. Vai como `skipped`
    para os ecrãs poderem dizer que não saiu nada, em vez de darem a entender
    que a mensagem seguiu.
    """

    return SendResult(True, MESSAGING_OFF, skipped=True)


def provider_module(setting=None):
    """Por onde as mensagens de WhatsApp saem.

    Houve dois caminhos — um serviço contratado e o número da clínica — e por
    isso havia aqui uma escolha por regra. Ficou um: o Baileys. A função fica,
    e as chamadas também, porque é ela que diz num sítio só qual é o caminho —
    e é aqui que se acrescenta outro, se algum dia voltar a haver.
    """

    return baileys_whatsapp


def provider_enabled(provider=None):
    return settings.BAILEYS_ENABLED


def provider_error(setting):
    """Porque é que esta regra não pode enviar agora, se for o caso.

    Devolve string vazia quando está tudo em ordem. Usado pelo ecrã de
    configuração para explicar o que falta a uma regra que parece ligada.
    """

    if not provider_enabled():
        return "O envio pelo número da clínica está desligado no servidor."

    return provider_module().validate_settings()


def resolve_recipients(setting, appointment):
    """Números desta regra, normalizados como o fornecedor dela precisa."""

    return provider_module().resolve_recipients(setting, appointment)


def sent_logs(appointment, setting):
    return provider_module().sent_logs(appointment, setting)


def send_manual(appointment, setting):
    """Dispara esta regra agora, para esta marcação."""

    if not MessagingSetting.whatsapp_enabled():
        return messaging_off_result()

    return provider_module().send_manual(appointment, setting)


def send_test(setting, recipient):
    """Envio de teste com dados de exemplo, pelo fornecedor da regra."""

    # O teste também é uma mensagem que chega ao telemóvel de alguém, e por
    # isso está sujeito ao interruptor como os outros envios.
    if not MessagingSetting.whatsapp_enabled():
        return messaging_off_result()

    return provider_module().send_test(setting, recipient)


def preview(appointment, event_type, override=None):
    """O que sairia por WhatsApp para este acontecimento, sem enviar nada.

    Percorre as mesmas regras que o `notify` percorre e pede a cada fornecedor
    o texto que ele construiria. O que não faz é a chamada ao fornecedor: é a
    única diferença entre ver e enviar.

    Devolve uma lista de mensagens e uma lista de razões — uma regra ligada mas
    sem número válido, ou um canal desligado, é informação que quem está a
    decidir precisa de ver antes de carregar no botão.
    """

    mensagens = []
    avisos = []

    if not MessagingSetting.whatsapp_enabled():
        return [], ["O envio de WhatsApp está desligado nas configurações."]

    regras = WhatsAppEventSetting.objects.filter(
        event_type=event_type,
        is_active=True,
    )

    if not regras:
        return [], ["Nenhuma regra de WhatsApp ativa para este acontecimento."]

    for regra in regras:
        if not provider_enabled():
            avisos.append("O envio pelo número da clínica está desligado no servidor.")
            continue

        try:
            destinatarios = resolve_recipients(regra, appointment)
            # A pré-visualização mostra o que a pessoa vai mesmo receber,
            # incluindo a língua — e incluindo a língua escolhida na janela,
            # senão trocar para inglês mostrava português e enviava inglês.
            lingua = audience_language(regra, appointment)

            if override and regra.audience == regra.AUDIENCE_CUSTOMER:
                lingua = override.language_or(lingua)
            texto = provider_module().build_body(
                regra,
                build_context(appointment, lingua),
                language=lingua,
            )
        except Exception as erro:
            logger.exception("Não foi possível pré-visualizar %s", regra)
            avisos.append(f"{regra}: {erro}")
            continue

        if not destinatarios:
            avisos.append(f"{regra}: nenhum número válido para enviar.")
            continue

        if not (texto or "").strip():
            avisos.append(f"{regra}: a mensagem está vazia.")
            continue

        mensagens.append(
            {
                "audience": regra.get_audience_display(),
                # A chave crua, e não a etiqueta traduzida: quem decide se isto
                # se pode reescrever é o código, e comparar com "Cliente"
                # partia-se assim que alguém renomeasse a etiqueta no admin.
                "editable": regra.audience == regra.AUDIENCE_CUSTOMER,
                "provider": "WhatsApp da clínica",
                "to": destinatarios,
                "body": texto,
            }
        )

    return mensagens, avisos


def notify(appointment, event_type, override=None):
    """Dispara todas as regras ativas para este acontecimento.

    Nunca levanta exceção: uma falha de envio não pode desfazer uma marcação
    que já foi gravada.

    `override` é o texto e a língua que a janela de confirmação escolheu para
    este envio, e vai até ao fornecedor sem passar por lado nenhum que grave.
    """

    if not MessagingSetting.whatsapp_enabled():
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
        if not provider_enabled():
            ignoradas += 1
            continue

        # Ligado mas mal configurado é outra coisa. Uma credencial em falta
        # calada é uma mensagem que ninguém percebe que não saiu.
        erro_config = provider_module().validate_settings()

        if erro_config:
            logger.warning("WhatsApp mal configurado: %s", erro_config)
            houve_falha = True
            mensagens.append(erro_config)
            continue

        try:
            resultado = provider_module().send_for_setting(
                appointment, regra, override=override
            )
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
