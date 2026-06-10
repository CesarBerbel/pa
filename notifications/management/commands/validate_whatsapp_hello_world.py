from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from notifications.whatsapp import (
    WhatsAppAppointmentNotificationService,
    normalize_whatsapp_phone,
)


class Command(BaseCommand):
    help = (
        "Valida a WhatsApp Cloud API enviando o template padrão hello_world. "
        "Use este comando antes de testar templates personalizados como marcacao."
    )

    DEFAULT_TEMPLATE_NAME = "hello_world"
    DEFAULT_LANGUAGE_CODE = "en_US"

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            dest="recipient_phone",
            required=True,
            help=(
                "Número de destino com indicativo do país. "
                "Exemplo: +351910000000 ou 351910000000."
            ),
        )
        parser.add_argument(
            "--template",
            default=Command.DEFAULT_TEMPLATE_NAME,
            help=(
                "Nome do template de validação. "
                "Por padrão usa hello_world, que é o template padrão da Meta."
            ),
        )
        parser.add_argument(
            "--language",
            default=Command.DEFAULT_LANGUAGE_CODE,
            help=(
                "Código de idioma do template hello_world. "
                "Por padrão usa en_US."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra endpoint, validações e payload, mas não envia mensagem.",
        )
        parser.add_argument(
            "--show-token",
            action="store_true",
            help="Mostra o token completo no diagnóstico. Use apenas localmente.",
        )
        parser.add_argument(
            "--skip-phone-check",
            action="store_true",
            help=(
                "Não faz a validação GET do Phone Number ID antes do envio. "
                "Use apenas se quiser testar diretamente o endpoint /messages."
            ),
        )

    def handle(self, *args, **options):
        recipient_phone = normalize_whatsapp_phone(options["recipient_phone"])
        template_name = str(options["template"] or self.DEFAULT_TEMPLATE_NAME).strip()
        language_code = str(options["language"] or self.DEFAULT_LANGUAGE_CODE).strip()
        dry_run = bool(options["dry_run"])
        show_token = bool(options["show_token"])
        skip_phone_check = bool(options["skip_phone_check"])

        if not recipient_phone:
            raise CommandError(
                "Número de destino inválido. Informe --to com indicativo do país."
            )

        settings_error = self.validate_minimum_settings()

        if settings_error:
            raise CommandError(settings_error)

        payload = self.build_hello_world_payload(
            recipient_phone=recipient_phone,
            template_name=template_name,
            language_code=language_code,
        )

        self.print_debug_summary(
            recipient_phone=recipient_phone,
            template_name=template_name,
            language_code=language_code,
            payload=payload,
            dry_run=dry_run,
            show_token=show_token,
            skip_phone_check=skip_phone_check,
        )

        if not skip_phone_check:
            phone_number_payload = self.validate_phone_number_id()
            self.stdout.write(self.style.SUCCESS("Phone Number ID validado com sucesso."))
            self.stdout.write("Resposta do Phone Number ID:")
            self.stdout.write(self.format_json(phone_number_payload))
            self.stdout.write("")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "DRY-RUN ativo: nenhuma mensagem foi enviada para a Meta."
                )
            )
            return

        try:
            response_payload = WhatsAppAppointmentNotificationService.post_message(payload)
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            formatted_error = WhatsAppAppointmentNotificationService.format_api_error(error)
            raise CommandError(f"Falha no envio hello_world pela Meta API: {formatted_error}")

        self.stdout.write(self.style.SUCCESS("Template hello_world enviado para a Meta API."))
        self.stdout.write("Resposta da Meta:")
        self.stdout.write(self.format_json(response_payload))

    def validate_minimum_settings(self) -> str:
        required_settings = {
            "WHATSAPP_PHONE_NUMBER_ID": settings.WHATSAPP_PHONE_NUMBER_ID,
            "WHATSAPP_ACCESS_TOKEN": settings.WHATSAPP_ACCESS_TOKEN,
            "WHATSAPP_CLOUD_API_VERSION": settings.WHATSAPP_CLOUD_API_VERSION,
        }

        missing_settings = [
            name for name, value in required_settings.items() if not str(value).strip()
        ]

        if missing_settings:
            return "Configuração WhatsApp incompleta: " + ", ".join(missing_settings)

        token = settings.WHATSAPP_ACCESS_TOKEN.strip()

        if token.lower().startswith("bearer "):
            return (
                "WHATSAPP_ACCESS_TOKEN não deve começar com 'Bearer '. "
                "Coloque apenas o token no .env; o código adiciona o Bearer automaticamente."
            )

        return ""

    def validate_phone_number_id(self) -> dict[str, Any]:
        request = Request(
            url=self.build_phone_number_info_url(),
            headers={
                "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            },
            method="GET",
        )

        try:
            with urlopen(request, timeout=settings.WHATSAPP_REQUEST_TIMEOUT) as response:
                response_body = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError) as error:
            formatted_error = WhatsAppAppointmentNotificationService.format_api_error(error)
            raise CommandError(
                "Falha ao validar WHATSAPP_PHONE_NUMBER_ID com a Meta API: "
                f"{formatted_error}"
            )

        if not response_body:
            return {}

        try:
            return json.loads(response_body)
        except json.JSONDecodeError as error:
            raise CommandError(
                "A Meta retornou uma resposta inválida ao validar o Phone Number ID."
            ) from error

    def build_phone_number_info_url(self) -> str:
        api_version = settings.WHATSAPP_CLOUD_API_VERSION.strip().lstrip("/")
        phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID.strip()

        return (
            f"https://graph.facebook.com/{api_version}/{phone_number_id}"
            "?fields=display_phone_number,verified_name"
        )

    def build_hello_world_payload(
        self,
        *,
        recipient_phone: str,
        template_name: str,
        language_code: str,
    ) -> dict[str, Any]:
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language_code,
                },
            },
        }

    def print_debug_summary(
        self,
        *,
        recipient_phone: str,
        template_name: str,
        language_code: str,
        payload: dict[str, Any],
        dry_run: bool,
        show_token: bool,
        skip_phone_check: bool,
    ) -> None:
        token = settings.WHATSAPP_ACCESS_TOKEN if show_token else self.mask_secret(
            settings.WHATSAPP_ACCESS_TOKEN
        )

        self.stdout.write(self.style.NOTICE("Validação WhatsApp hello_world"))
        self.stdout.write(f"Data/hora do teste: {self.format_now()}")
        self.stdout.write(f"Modo: {'DRY-RUN' if dry_run else 'ENVIO REAL'}")
        self.stdout.write(f"Endpoint de envio: {WhatsAppAppointmentNotificationService.build_endpoint_url()}")
        self.stdout.write(f"Endpoint Phone Number ID: {self.build_phone_number_info_url()}")
        self.stdout.write(f"Phone Number ID: {settings.WHATSAPP_PHONE_NUMBER_ID or '[vazio]'}")
        self.stdout.write(f"Access Token: {token or '[vazio]'}")
        self.stdout.write(f"Template: {template_name}")
        self.stdout.write(f"Idioma: {language_code}")
        self.stdout.write(f"Destino normalizado: {recipient_phone}")
        self.stdout.write(f"Validação prévia do Phone Number ID: {'não' if skip_phone_check else 'sim'}")
        self.stdout.write("")
        self.stdout.write("Payload JSON:")
        self.stdout.write(self.format_json(payload))
        self.stdout.write("")

    def mask_secret(self, secret: str) -> str:
        if not secret:
            return ""

        if len(secret) <= 12:
            return "***"

        return f"{secret[:6]}...{secret[-4:]}"

    def format_now(self) -> str:
        current = timezone.localtime(timezone.now())

        if isinstance(current, datetime):
            return current.strftime("%Y-%m-%d %H:%M:%S %Z")

        return str(current)

    def format_json(self, data: Any) -> str:
        return json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
