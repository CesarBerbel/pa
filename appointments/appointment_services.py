from dataclasses import dataclass
from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from appointments.emails import (
    send_professional_notification_email,
    deliver_after_commit,
    send_appointment_confirmation_email,
)
from appointments.audit_services import AppointmentAuditService
from appointments.customer_services import current_language
from appointments.models import Appointment, AppointmentLog, Service
from notifications.models import EmailEventSetting, WhatsAppEventSetting
from notifications.whatsapp_dispatch import notify as notify_whatsapp


@dataclass
class AppointmentCreationResult:
    # Represents the result of an appointment creation attempt.
    success: bool
    message: str
    appointment: Appointment | None = None


class AppointmentService:
    # Centralizes appointment creation rules.

    @staticmethod
    def get_system_user():
        # Get the first superuser to register public appointments.
        User = get_user_model()

        system_user = (
            User.objects.filter(
                is_superuser=True,
            )
            .order_by("id")
            .first()
        )

        if not system_user:
            raise ValidationError(
                "Não existe utilizador administrador para registar marcações públicas."
            )

        return system_user

    @staticmethod
    def create_appointment(
        customer,
        service,
        date,
        start_time,
        created_by=None,
        status=Appointment.STATUS_SCHEDULED,
        notes="",
        send_email=True,
        origin=Appointment.ORIGIN_INTERNAL,
    ):
        # Create an appointment safely using transaction and row-level locking.
        #
        # `origin` vem de quem chama e não é deduzido do `created_by`: uma
        # marcação feita no site é gravada em nome do primeiro administrador, o
        # que a tornaria indistinguível de uma marcada pela equipa.
        if not created_by:
            created_by = AppointmentService.get_system_user()

        try:
            with transaction.atomic():
                # Lock appointments from the same day to prevent concurrent double booking.
                existing_appointments = (
                    Appointment.objects.select_for_update()
                    .filter(date=date)
                    .exclude(status=Appointment.STATUS_CANCELLED)
                    .select_related("service")
                )

                # Force query evaluation so PostgreSQL applies the lock before creating.
                list(existing_appointments)

                appointment = Appointment.objects.create(
                    customer=customer,
                    service=service,
                    date=date,
                    start_time=start_time,
                    status=status,
                    notes=notes or "",
                    created_by=created_by,
                    origin=origin,
                    # A língua da página onde a marcação foi feita. Quem marcou
                    # em /en/ recebe as mensagens desta marcação em inglês,
                    # mesmo que mais tarde volte a marcar em português.
                    customer_speaks_english=current_language() == "en",
                )

                AppointmentAuditService.log(
                    appointment=appointment,
                    action=AppointmentLog.ACTION_CREATE,
                    user=created_by,
                    description="Marcação criada.",
                    changes=AppointmentAuditService.creation_changes(appointment),
                )

                if send_email:
                    deliver_after_commit(
                        send_appointment_confirmation_email,
                        appointment,
                    )

                # Depois do commit, como os emails: uma falha do WhatsApp não
                # pode desfazer uma marcação que já está gravada.
                deliver_after_commit(
                    notify_whatsapp,
                    appointment,
                    WhatsAppEventSetting.EVENT_APPOINTMENT_REQUESTED,
                )

                # O aviso interno não depende do WhatsApp estar de pé: um
                # pedido por confirmar que passa despercebido é um horário
                # perdido, e o email fica lá até alguém o ler.
                if origin == Appointment.ORIGIN_PUBLIC:
                    deliver_after_commit(
                        send_professional_notification_email,
                        appointment,
                        EmailEventSetting.EVENT_APPOINTMENT_CREATED,
                        "appointment_created_professional",
                    )

            return AppointmentCreationResult(
                success=True,
                message="Marcação criada com sucesso.",
                appointment=appointment,
            )

        except ValidationError as error:
            return AppointmentCreationResult(
                success=False,
                message=error.messages[0] if hasattr(error, "messages") else str(error),
            )

        except IntegrityError:
            # Last line of defence against a concurrent double booking that
            # passed validation. The database constraint rejects the insert.
            return AppointmentCreationResult(
                success=False,
                message="Este horário já não está disponível. Escolha outro horário.",
            )

    @staticmethod
    def create_public_appointment(
        customer,
        service_id,
        date_value,
        start_time_value,
        notes="",
        send_email=True,
    ):
        # Create a public appointment from request/query string values.
        try:
            service = Service.objects.get(
                pk=service_id,
                is_active=True,
            )

            selected_date = datetime.strptime(
                date_value,
                "%Y-%m-%d",
            ).date()

            selected_time = datetime.strptime(
                start_time_value,
                "%H:%M",
            ).time()

            return AppointmentService.create_appointment(
                customer=customer,
                service=service,
                date=selected_date,
                start_time=selected_time,
                created_by=AppointmentService.get_system_user(),
                status=Appointment.STATUS_SCHEDULED,
                notes=notes,
                send_email=send_email,
                origin=Appointment.ORIGIN_PUBLIC,
            )

        except (Service.DoesNotExist, ValueError, ValidationError) as error:
            return AppointmentCreationResult(
                success=False,
                message=str(error) or "Não foi possível criar a marcação.",
            )
