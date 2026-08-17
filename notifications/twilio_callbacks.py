"""Webhook de estado de entrega da Twilio.

A resposta ao envio diz apenas que a Twilio **aceitou** a mensagem. A entrega
acontece depois, e pode falhar — número sem WhatsApp, destinatário que não
aderiu ao sandbox, modelo por aprovar. Sem este webhook, tudo isso é invisível
do lado de cá e o sistema fica a dizer "enviada" para sempre.
"""

from __future__ import annotations

import base64
import hmac
import logging
from hashlib import sha1
from urllib.parse import urljoin

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from notifications.models import WhatsAppMessageLog

logger = logging.getLogger(__name__)


def status_callback_url():
    """URL pública para onde a Twilio devolve o estado.

    Só em HTTPS público: a Twilio não alcança `localhost`, e mandar-lhe um
    endereço inalcançável enche os registos dela de erros sem servir para nada.
    """

    base = (settings.SITE_URL or "").rstrip("/")

    if not base.startswith("https://"):
        return ""

    return urljoin(f"{base}/", reverse("notifications:twilio_status").lstrip("/"))


def signature_is_valid(request):
    """Confirma que o pedido vem mesmo da Twilio.

    O endereço é público. Sem esta verificação, qualquer pessoa podia marcar as
    mensagens como entregues — ou como falhadas — a partir da rua.

    A Twilio assina o URL completo seguido dos parâmetros do formulário
    ordenados por nome e concatenados como chave+valor, com HMAC-SHA1 e o token
    da conta.
    """

    assinatura = request.headers.get("X-Twilio-Signature", "")

    if not assinatura or not settings.TWILIO_AUTH_TOKEN:
        return False

    url = request.build_absolute_uri()

    # Atrás de um proxy o Django pode ver http; a Twilio assinou o https.
    if url.startswith("http://") and settings.SITE_URL.startswith("https://"):
        url = "https://" + url[len("http://") :]

    dados = "".join(
        f"{chave}{request.POST[chave]}" for chave in sorted(request.POST.keys())
    )

    esperada = base64.b64encode(
        hmac.new(
            settings.TWILIO_AUTH_TOKEN.encode("utf-8"),
            (url + dados).encode("utf-8"),
            sha1,
        ).digest()
    ).decode()

    return hmac.compare_digest(esperada, assinatura)


def record_status(message_sid, message_status, error_code=""):
    """Guarda o estado no registo do envio correspondente."""

    if not message_sid:
        return None

    registo = WhatsAppMessageLog.objects.filter(whatsapp_message_id=message_sid).first()

    if not registo:
        # Uma mensagem enviada por outra via, ou por um ambiente diferente que
        # partilha a conta Twilio. Não é erro nosso; fica anotado e segue.
        logger.info("Estado da Twilio para SID desconhecido: %s", message_sid)
        return None

    registo.delivery_status = message_status or ""
    registo.delivery_error_code = str(error_code or "")
    registo.delivery_updated_at = timezone.now()

    registo.save(
        update_fields=[
            "delivery_status",
            "delivery_error_code",
            "delivery_updated_at",
        ]
    )

    if registo.delivery_failed():
        logger.warning(
            "WhatsApp não entregue para %s: %s (erro %s)",
            registo.recipient_phone,
            registo.delivery_status,
            registo.delivery_error_code,
        )

    return registo
