from __future__ import annotations

import json
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from appointments.models import Appointment
from notifications.whatsapp import (
    WhatsAppAppointmentNotificationService,
    normalize_whatsapp_phone,
)


class Command(BaseCommand):
    help = (
        "Debug manual do envio de template pela WhatsApp Cloud API. "
        "Por padrão usa o template configurado em WHATSAPP_TEMPLATE_NAME."
    )

    SAMPLE_CONTEXT = {
        "customer_name": "Cliente Teste",
        "service_name": "Serviço Teste",
        "service_category": "Categoria Teste",
        "appointment_date": "31/12/2026",
        "appointment_time": "10:00",
        "reference_code": "AGD-DEBUG",
        "business_name": "Priscila Arantes Pedicure Terapêutica",
        "business_phone": "+351938594367",
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            dest="recipient_phone",
            help=(
                "Número de destino com indicativo do país. "
                "Exemplo: +351910000000 ou 351910000000."
            ),
        )
        parser.add_argument(
            "--appointment-id",
            type=int,
            help=(
                "ID de uma marcação existente para montar os parâmetros reais "
                "do template. Se --to não for informado, usa o telefone do cliente."
            ),
        )
        parser.add_argument(
            "--template",
            default=None,
            help=(
                "Nome do template aprovado no Meta. "
                "Se omitido, usa WHATSAPP_TEMPLATE_NAME."
            ),
        )
        parser.add_argument(
            "--language",
            default=None,
            help=(
                "Código de idioma do template. "
                "Se omitido, usa WHATSAPP_TEMPLATE_LANGUAGE_CODE. Exemplo: pt_PT."
            ),
        )
        parser.add_argument(
            "--parameters",
            default=None,
            help=(
                "Lista de parâmetros do corpo na ordem do template. "
                "Exemplo: customer_name,service_name,appointment_date,appointment_time. "
                "Se omitido, usa WHATSAPP_TEMPLATE_BODY_PARAMETERS."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra endpoint e payload, mas não envia para a Meta.",
        )
        parser.add_argument(
            "--show-token",
            action="store_true",
            help="Mostra o token no diagnóstico. Use apenas localmente.",
        )
        parser.add_argument(
            "--customer-name",
            default=None,
            help="Valor manual para customer_name quando não usar --appointment-id.",
        )
        parser.add_argument(
            "--service-name",
            default=None,
            help="Valor manual para service_name quando não usar --appointment-id.",
        )
        parser.add_argument(
            "--service-category",
            default=None,
            help="Valor manual para service_category quando não usar --appointment-id.",
        )
        parser.add_argument(
            "--appointment-date",
            default=None,
            help="Valor manual para appointment_date quando não usar --appointment-id.",
        )
        parser.add_argument(
            "--appointment-time",
            default=None,
            help="Valor manual para appointment_time quando não usar --appointment-id.",
        )
        parser.add_argument(
            "--reference-code",
            default=None,
            help="Valor manual para reference_code quando não usar --appointment-id.",
        )
        parser.add_argument(
            "--business-name",
            default=None,
            help="Valor manual para business_name quando não usar --appointment-id.",
        )
        parser.add_argument(
            "--business-phone",
            default=None,
            help="Valor manual para business_phone quando não usar --appointment-id.",
        )

    def handle(self, *args, **options):
        appointment = self.get_appointment(options["appointment_id"])
        context = self.build_context(appointment, options)
        recipient_phone = self.get_recipient_phone(
            appointment, options["recipient_phone"]
        )
        template_name = (options["template"] or settings.WHATSAPP_TEMPLATE_NAME).strip()
        language_code = (
            options["language"] or settings.WHATSAPP_TEMPLATE_LANGUAGE_CODE
        ).strip()
        parameter_names = self.get_parameter_names(options["parameters"])
        payload = self.build_payload(
            recipient_phone=recipient_phone,
            template_name=template_name,
            language_code=language_code,
            parameter_names=parameter_names,
            context=context,
        )

        self.print_debug_summary(
            appointment=appointment,
            context=context,
            payload=payload,
            parameter_names=parameter_names,
            show_token=options["show_token"],
            dry_run=options["dry_run"],
        )

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    "DRY-RUN ativo: nenhum pedido foi enviado para a Meta."
                )
            )
            return

        settings_error = WhatsAppAppointmentNotificationService.validate_settings()

        if settings_error:
            raise CommandError(settings_error)

        try:
            response_payload = WhatsAppAppointmentNotificationService.post_message(
                payload
            )
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            formatted_error = WhatsAppAppointmentNotificationService.format_api_error(
                error
            )
            raise CommandError(f"Falha no envio pela Meta API: {formatted_error}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Mensagem enviada para a Meta API."))
        self.stdout.write("Resposta da Meta:")
        self.stdout.write(self.format_json(response_payload))

    def get_appointment(self, appointment_id: int | None) -> Appointment | None:
        if not appointment_id:
            return None

        try:
            return Appointment.objects.select_related(
                "customer",
                "service",
                "service__category",
            ).get(pk=appointment_id)
        except Appointment.DoesNotExist as error:
            raise CommandError(
                f"Não existe marcação com ID {appointment_id}."
            ) from error

    def get_recipient_phone(
        self,
        appointment: Appointment | None,
        recipient_phone: str | None,
    ) -> str:
        phone = recipient_phone

        if not phone and appointment:
            phone = appointment.customer.phone

        normalized_phone = normalize_whatsapp_phone(phone or "")

        if not normalized_phone:
            raise CommandError(
                "Informe --to ou use --appointment-id com cliente que tenha telefone."
            )

        return normalized_phone

    def get_parameter_names(self, raw_parameters: str | None) -> list[str]:
        if raw_parameters is None:
            return list(settings.WHATSAPP_TEMPLATE_BODY_PARAMETERS)

        return [item.strip() for item in raw_parameters.split(",") if item.strip()]

    def build_context(
        self,
        appointment: Appointment | None,
        options: dict[str, Any],
    ) -> dict[str, str]:
        if appointment:
            context = WhatsAppAppointmentNotificationService.build_context(appointment)
        else:
            context = dict(self.SAMPLE_CONTEXT)
            context["business_name"] = getattr(
                settings,
                "SEO_SITE_NAME",
                context["business_name"],
            )
            context["business_phone"] = getattr(
                settings,
                "SEO_WHATSAPP_NUMBER",
                context["business_phone"],
            )

        manual_overrides = {
            "customer_name": options["customer_name"],
            "service_name": options["service_name"],
            "service_category": options["service_category"],
            "appointment_date": options["appointment_date"],
            "appointment_time": options["appointment_time"],
            "reference_code": options["reference_code"],
            "business_name": options["business_name"],
            "business_phone": options["business_phone"],
        }

        for key, value in manual_overrides.items():
            if value is not None:
                context[key] = value

        return context

    def build_payload(
        self,
        *,
        recipient_phone: str,
        template_name: str,
        language_code: str,
        parameter_names: list[str],
        context: dict[str, str],
    ) -> dict[str, Any]:
        template: dict[str, Any] = {
            "name": template_name,
            "language": {
                "code": language_code,
            },
        }

        if parameter_names:
            template["components"] = [
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": context.get(parameter_name, ""),
                        }
                        for parameter_name in parameter_names
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

    def print_debug_summary(
        self,
        *,
        appointment: Appointment | None,
        context: dict[str, str],
        payload: dict[str, Any],
        parameter_names: list[str],
        show_token: bool,
        dry_run: bool,
    ) -> None:
        endpoint_url = WhatsAppAppointmentNotificationService.build_endpoint_url()
        token = (
            settings.WHATSAPP_ACCESS_TOKEN
            if show_token
            else self.mask_secret(settings.WHATSAPP_ACCESS_TOKEN)
        )

        self.stdout.write(self.style.NOTICE("Diagnóstico WhatsApp Cloud API"))
        self.stdout.write(f"Data do teste: {date.today().isoformat()}")
        self.stdout.write(f"Modo: {'DRY-RUN' if dry_run else 'ENVIO REAL'}")
        self.stdout.write(
            f"WhatsApp ativo no settings: {settings.WHATSAPP_CLOUD_API_ENABLED}"
        )
        self.stdout.write(f"Endpoint: {endpoint_url}")
        self.stdout.write(
            f"Phone Number ID: {settings.WHATSAPP_PHONE_NUMBER_ID or '[vazio]'}"
        )
        self.stdout.write(f"Access Token: {token or '[vazio]'}")
        self.stdout.write(f"Template: {payload['template']['name']}")
        self.stdout.write(f"Idioma: {payload['template']['language']['code']}")
        self.stdout.write(f"Destino normalizado: {payload['to']}")

        if appointment:
            self.stdout.write(
                f"Marcação usada: ID {appointment.pk} / {appointment.reference_code}"
            )
        else:
            self.stdout.write("Marcação usada: nenhuma; contexto manual/de exemplo")

        self.stdout.write("")
        self.stdout.write("Ordem dos parâmetros do body:")

        if parameter_names:
            for index, parameter_name in enumerate(parameter_names, start=1):
                self.stdout.write(
                    f"  {{{{{index}}}}} -> "
                    f"{parameter_name} = {context.get(parameter_name, '')}"
                )
        else:
            self.stdout.write("  Nenhum parâmetro de body configurado.")

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

    def format_json(self, data: Any) -> str:
        return json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
