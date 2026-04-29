from dataclasses import dataclass

from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from appointments.emails import send_appointment_cancelled_email
from appointments.audit_services import AppointmentAuditService
from appointments.models import Appointment, AppointmentLog


@dataclass
class CancellationResult:
    # Represents the result of an appointment cancellation attempt.
    success: bool
    message: str
    appointment: Appointment | None = None


class AppointmentCancellationService:
    # Centralizes all appointment cancellation business rules.

    @staticmethod
    def cancel(appointment, user=None, cancellation_reason=""):
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

        cancellation_reason = (cancellation_reason or "").strip()

        if not cancellation_reason:
            return CancellationResult(
                success=False,
                message="Informe o motivo do cancelamento.",
                appointment=appointment,
            )

        appointment.status = Appointment.STATUS_CANCELLED
        appointment.cancellation_reason = cancellation_reason
        appointment.cancelled_at = timezone.now()
        appointment.save(
            update_fields=[
                "status",
                "cancellation_reason",
                "cancelled_at",
                "updated_at",
            ]
        )

        AppointmentAuditService.log(
            appointment=appointment,
            action=AppointmentLog.ACTION_CANCEL,
            user=user,
            description=f"Appointment cancelled. Reason: {cancellation_reason}",
        )

        send_appointment_cancelled_email(
            appointment=appointment,
            cancellation_reason=cancellation_reason,
        )

        return CancellationResult(
            success=True,
            message="Marcação cancelada com sucesso.",
            appointment=appointment,
        )