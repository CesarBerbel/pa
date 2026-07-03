from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import IntegrityError

from notifications.models import WhatsAppMessageLog

logger = logging.getLogger(__name__)


@dataclass
class WhatsAppSendResult:
    # Represents the result of a WhatsApp Cloud API sending attempt.
    success: bool
    message: str
    skipped: bool = False
    log: WhatsAppMessageLog | None = None


def normalize_whatsapp_phone(phone: str) -> str:
    # Meta expects the recipient number with country code and without the plus sign.
    digits = re.sub(r"\D", "", phone or "")
    return digits


class WhatsAppAppointmentNotificationService:
    # Sends appointment-related WhatsApp notifications through Meta WhatsApp Cloud API.

    CONFIRMATION_EVENT_TYPE = WhatsAppMessageLog.EVENT_APPOINTMENT_CONFIRMED

    @staticmethod
    def send_confirmation(appointment) -> WhatsAppSendResult:
        template_name = settings.WHATSAPP_TEMPLATE_NAME

        if not settings.WHATSAPP_CLOUD_API_ENABLED:
            return WhatsAppSendResult(
                success=True,
                skipped=True,
                message="Envio de WhatsApp desativado nas configurações.",
            )

        existing_log = WhatsAppMessageLog.objects.filter(
            appointment=appointment,
            event_type=WhatsAppAppointmentNotificationService.CONFIRMATION_EVENT_TYPE,
            template_name=template_name,
            status=WhatsAppMessageLog.STATUS_SUCCESS,
        ).first()

        if existing_log:
            return WhatsAppSendResult(
                success=True,
                skipped=True,
                message="WhatsApp já enviado para esta confirmação.",
                log=existing_log,
            )

        validation_error = WhatsAppAppointmentNotificationService.validate_settings()

        if validation_error:
            return WhatsAppAppointmentNotificationService.create_error_result(
                appointment=appointment,
                recipient_phone=appointment.customer.phone,
                request_payload={},
                error_message=validation_error,
            )

        recipient_phone = normalize_whatsapp_phone(appointment.customer.phone)

        if not recipient_phone:
            return WhatsAppAppointmentNotificationService.create_error_result(
                appointment=appointment,
                recipient_phone=appointment.customer.phone,
                request_payload={},
                error_message="Telefone do cliente inválido para WhatsApp.",
            )

        payload = WhatsAppAppointmentNotificationService.build_template_payload(
            appointment=appointment,
            recipient_phone=recipient_phone,
        )

        try:
            response_payload = WhatsAppAppointmentNotificationService.post_message(payload)
            whatsapp_message_id = WhatsAppAppointmentNotificationService.extract_message_id(
                response_payload
            )

            try:
                log = WhatsAppMessageLog.objects.create(
                    appointment=appointment,
                    event_type=WhatsAppAppointmentNotificationService.CONFIRMATION_EVENT_TYPE,
                    status=WhatsAppMessageLog.STATUS_SUCCESS,
                    template_name=template_name,
                    recipient_phone=recipient_phone,
                    whatsapp_message_id=whatsapp_message_id,
                    request_payload=WhatsAppAppointmentNotificationService.safe_json_dump(
                        payload
                    ),
                    response_payload=WhatsAppAppointmentNotificationService.safe_json_dump(
                        response_payload
                    ),
                )
            except IntegrityError:
                existing_log = WhatsAppMessageLog.objects.filter(
                    appointment=appointment,
                    event_type=WhatsAppAppointmentNotificationService.CONFIRMATION_EVENT_TYPE,
                    template_name=template_name,
                    status=WhatsAppMessageLog.STATUS_SUCCESS,
                ).first()

                return WhatsAppSendResult(
                    success=True,
                    skipped=True,
                    message="WhatsApp já enviado para esta confirmação.",
                    log=existing_log,
                )

            return WhatsAppSendResult(
                success=True,
                message="WhatsApp de confirmação enviado com sucesso.",
                log=log,
            )

        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            error_message = WhatsAppAppointmentNotificationService.format_api_error(error)
            logger.exception(
                "Error sending WhatsApp confirmation for appointment %s",
                appointment.reference_code,
            )

            return WhatsAppAppointmentNotificationService.create_error_result(
                appointment=appointment,
                recipient_phone=recipient_phone,
                request_payload=payload,
                error_message=error_message,
            )

    @staticmethod
    def validate_settings() -> str:
        required_settings = {
            "WHATSAPP_PHONE_NUMBER_ID": settings.WHATSAPP_PHONE_NUMBER_ID,
            "WHATSAPP_ACCESS_TOKEN": settings.WHATSAPP_ACCESS_TOKEN,
            "WHATSAPP_TEMPLATE_NAME": settings.WHATSAPP_TEMPLATE_NAME,
            "WHATSAPP_TEMPLATE_LANGUAGE_CODE": settings.WHATSAPP_TEMPLATE_LANGUAGE_CODE,
        }

        missing_settings = [
            name for name, value in required_settings.items() if not str(value).strip()
        ]

        if missing_settings:
            return "Configuração WhatsApp incompleta: " + ", ".join(missing_settings)

        return ""

    @staticmethod
    def build_context(appointment) -> dict[str, str]:
        return {
            "customer_name": appointment.customer.full_name,
            "service_name": appointment.service.name,
            "service_category": appointment.service.category.name,
            "appointment_date": appointment.date.strftime("%d/%m/%Y"),
            "appointment_time": appointment.start_time.strftime("%H:%M"),
            "reference_code": appointment.reference_code,
            "business_name": getattr(settings, "SEO_SITE_NAME", "Priscila Arantes PA"),
            "business_phone": getattr(settings, "SEO_WHATSAPP_NUMBER", ""),
        }

    @staticmethod
    def build_template_payload(appointment, recipient_phone: str) -> dict[str, Any]:
        context = WhatsAppAppointmentNotificationService.build_context(appointment)
        body_parameter_names = settings.WHATSAPP_TEMPLATE_BODY_PARAMETERS

        template: dict[str, Any] = {
            "name": settings.WHATSAPP_TEMPLATE_NAME,
            "language": {
                "code": settings.WHATSAPP_TEMPLATE_LANGUAGE_CODE,
            },
        }

        if body_parameter_names:
            template["components"] = [
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": context.get(parameter_name, ""),
                        }
                        for parameter_name in body_parameter_names
                    ],
                }
            ]

        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_phone,
            "type": "template",
            "template": template,
        }

    @staticmethod
    def build_endpoint_url() -> str:
        api_version = settings.WHATSAPP_CLOUD_API_VERSION.strip().lstrip("/")
        phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID.strip()

        return f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"

    @staticmethod
    def post_message(payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            url=WhatsAppAppointmentNotificationService.build_endpoint_url(),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urlopen(request, timeout=settings.WHATSAPP_REQUEST_TIMEOUT) as response:
            response_body = response.read().decode("utf-8")

        if not response_body:
            return {}

        return json.loads(response_body)

    @staticmethod
    def extract_message_id(response_payload: dict[str, Any]) -> str:
        messages = response_payload.get("messages", [])

        if not messages:
            return ""

        first_message = messages[0]

        if not isinstance(first_message, dict):
            return ""

        return str(first_message.get("id", ""))

    @staticmethod
    def create_error_result(
        appointment,
        recipient_phone: str,
        request_payload: dict[str, Any],
        error_message: str,
    ) -> WhatsAppSendResult:
        log = WhatsAppMessageLog.objects.create(
            appointment=appointment,
            event_type=WhatsAppAppointmentNotificationService.CONFIRMATION_EVENT_TYPE,
            status=WhatsAppMessageLog.STATUS_ERROR,
            template_name=settings.WHATSAPP_TEMPLATE_NAME or "marcacao",
            recipient_phone=recipient_phone,
            request_payload=WhatsAppAppointmentNotificationService.safe_json_dump(
                request_payload
            ),
            error_message=error_message,
        )

        return WhatsAppSendResult(
            success=False,
            message=error_message,
            log=log,
        )

    @staticmethod
    def format_api_error(error: Exception) -> str:
        if isinstance(error, HTTPError):
            response_body = error.read().decode("utf-8", errors="replace")

            if response_body:
                return f"Meta API HTTP {error.code}: {response_body}"

            return f"Meta API HTTP {error.code}: {error.reason}"

        if isinstance(error, URLError):
            return f"Erro de ligação com a Meta API: {error.reason}"

        return str(error)

    @staticmethod
    def safe_json_dump(data: Any) -> str:
        return json.dumps(
            data,
            ensure_ascii=False,
            sort_keys=True,
        )
