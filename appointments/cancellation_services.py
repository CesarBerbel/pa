from dataclasses import dataclass

from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from notifications.models import EmailEventSetting, WhatsAppEventSetting
from notifications.whatsapp_dispatch import notify as notify_whatsapp

from appointments.emails import (
    send_professional_notification_email,
    deliver_after_commit,
    send_appointment_cancelled_email,
)
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
    def cancel(
        appointment,
        user=None,
        cancellation_reason="",
        source=None,
        send_message=True,
    ):
        """Cancela a marcação, se as regras o permitirem.

        `source` diz se o cancelamento partiu do site ou da área interna. Sem
        isso, um cancelamento feito pela cliente com o código ficava registado
        como se tivesse sido a equipa a desmarcar.

        `send_message` responde à pergunta feita no ecrã interno. Com ela em
        falso, a marcação é cancelada em silêncio — é para o caso de já se ter
        falado com a cliente, que é como a maioria dos cancelamentos acontece.
        Vem ligado por omissão porque o cancelamento pelo site tem sempre de
        avisar: aí ninguém combinou nada.
        """
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
                message="Indique o motivo do cancelamento.",
                appointment=appointment,
            )

        anterior = AppointmentAuditService.snapshot(appointment)

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
            description=f"Marcação cancelada. Motivo: {cancellation_reason}",
            source=source,
            changes=AppointmentAuditService.diff(
                anterior, AppointmentAuditService.snapshot(appointment)
            ),
        )

        if send_message:
            deliver_after_commit(
                send_appointment_cancelled_email,
                appointment=appointment,
                cancellation_reason=cancellation_reason,
            )

            deliver_after_commit(
                notify_whatsapp,
                appointment,
                WhatsAppEventSetting.EVENT_APPOINTMENT_CANCELLED,
            )

            # Um horário que vaga é um horário que se pode voltar a oferecer. O
            # aviso vale sobretudo quando o cancelamento vem do site, fora de
            # horas.
            deliver_after_commit(
                send_professional_notification_email,
                appointment,
                EmailEventSetting.EVENT_APPOINTMENT_CANCELLED,
                "appointment_cancelled_professional",
            )

        if not send_message:
            return CancellationResult(
                success=True,
                message="Marcação cancelada. Não foi enviada mensagem à cliente.",
                appointment=appointment,
            )

        return CancellationResult(
            success=True,
            message="Marcação cancelada com sucesso.",
            appointment=appointment,
        )
