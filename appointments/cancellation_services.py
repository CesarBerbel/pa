from dataclasses import dataclass

from django.contrib.auth.models import AnonymousUser

from appointments.emails import send_appointment_cancelled_email
from appointments.models import Appointment


@dataclass
class CancellationResult:
    # Represents the result of an appointment cancellation attempt.
    success: bool
    message: str
    appointment: Appointment | None = None


class AppointmentCancellationService:
    # Centralizes all appointment cancellation business rules.

    @staticmethod
    def cancel(appointment, user=None):
        # Cancel an appointment only when business rules allow it.
        if not appointment:
            return CancellationResult(
                success=False,
                message="Marcação não encontrada.",
            )

        if appointment.status == Appointment.STATUS_CANCELLED:
            return CancellationResult(
                success=False,
                message="Esta marcação já foi cancelada.",
                appointment=appointment,
            )

        if appointment.status == Appointment.STATUS_COMPLETED:
            return CancellationResult(
                success=False,
                message="Marcações concluídas não podem ser canceladas.",
                appointment=appointment,
            )

        is_superuser = (
            user
            and not isinstance(user, AnonymousUser)
            and user.is_authenticated
            and user.is_superuser
        )

        if appointment.status == Appointment.STATUS_CONFIRMED and not is_superuser:
            return CancellationResult(
                success=False,
                message="Marcações confirmadas só podem ser canceladas pela equipa.",
                appointment=appointment,
            )

        appointment.status = Appointment.STATUS_CANCELLED
        appointment.save(update_fields=["status", "updated_at"])

        send_appointment_cancelled_email(appointment)

        return CancellationResult(
            success=True,
            message="Marcação cancelada com sucesso.",
            appointment=appointment,
        )