import logging
from dataclasses import dataclass

from appointments.customer_services import normalize_email
from appointments.emails import send_open_appointments_lookup_email
from appointments.models import Appointment

logger = logging.getLogger(__name__)


@dataclass
class PublicAppointmentLookupEmailResult:
    # Represents the result of an email-based public appointment lookup.

    success: bool
    message: str
    matched_count: int = 0
    email_sent: bool = False


class PublicAppointmentLookupService:
    # Centralizes public lookup rules without exposing appointment existence on screen.

    OPEN_STATUSES = [
        Appointment.STATUS_SCHEDULED,
        Appointment.STATUS_CONFIRMED,
    ]

    @classmethod
    def get_open_appointments_by_email(cls, email):
        # Return open appointments for the normalized customer email.
        normalized_email = normalize_email(email)

        if not normalized_email:
            return Appointment.objects.none()

        return (
            Appointment.objects.filter(
                customer__email__iexact=normalized_email,
                status__in=cls.OPEN_STATUSES,
            )
            .select_related(
                "customer",
                "service",
            )
            .order_by(
                "date",
                "start_time",
                "id",
            )
        )

    @classmethod
    def send_lookup_email(cls, email):
        # Send appointment details to the email owner when open appointments exist.
        normalized_email = normalize_email(email)

        generic_message = (
            "Se existir alguma marcação em aberto para o email informado, "
            "enviaremos os detalhes e o código de referência para esse endereço."
        )

        appointments = list(cls.get_open_appointments_by_email(normalized_email))

        if not appointments:
            return PublicAppointmentLookupEmailResult(
                success=True,
                message=generic_message,
                matched_count=0,
                email_sent=False,
            )

        try:
            send_open_appointments_lookup_email(
                recipient_email=normalized_email,
                appointments=appointments,
            )
        except Exception:
            logger.exception(
                "Erro ao enviar email de consulta pública de marcações para %s.",
                normalized_email,
            )
            return PublicAppointmentLookupEmailResult(
                success=False,
                message=(
                    "Não foi possível enviar o email neste momento. "
                    "Tente novamente mais tarde ou consulte pelo código da marcação."
                ),
                matched_count=len(appointments),
                email_sent=False,
            )

        return PublicAppointmentLookupEmailResult(
            success=True,
            message=generic_message,
            matched_count=len(appointments),
            email_sent=True,
        )
