from dataclasses import dataclass
from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from appointments.emails import send_appointment_confirmation_email
from appointments.audit_services import AppointmentAuditService
from appointments.models import Appointment, AppointmentLog, Service


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

        system_user = User.objects.filter(
            is_superuser=True,
        ).order_by("id").first()

        if not system_user:
            raise ValidationError(
                "Não existe usuário administrador para registrar marcações públicas."
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
    ):
        # Create an appointment safely using transaction and row-level locking.
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
                )

                AppointmentAuditService.log(
                    appointment=appointment,
                    action=AppointmentLog.ACTION_CREATE,
                    user=created_by,
                    description="Appointment created.",
                )

                if send_email:
                    send_appointment_confirmation_email(appointment)

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
            )

        except (Service.DoesNotExist, ValueError, ValidationError) as error:
            return AppointmentCreationResult(
                success=False,
                message=str(error) or "Não foi possível criar a marcação.",
            )