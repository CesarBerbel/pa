from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from appointments.audit_services import AppointmentAuditService
from appointments.emails import send_appointment_confirmation_email
from appointments.models import Appointment, AppointmentLog


@dataclass
class UseCaseResult:
    success: bool
    message: str
    appointment: Appointment | None = None


class ConfirmAppointmentUseCase:
    @staticmethod
    def execute(*, appointment, user, send_email=True):
        if appointment.status == Appointment.STATUS_CANCELLED:
            return UseCaseResult(False, "Marcações canceladas não podem ser confirmadas.", appointment)

        with transaction.atomic():
            appointment.status = Appointment.STATUS_CONFIRMED
            appointment.save(update_fields=["status", "updated_at"])

            AppointmentAuditService.log(
                appointment=appointment,
                action=AppointmentLog.ACTION_CONFIRM,
                user=user,
                description="Appointment confirmed.",
            )

            if send_email:
                send_appointment_confirmation_email(appointment)

        return UseCaseResult(True, "Marcação confirmada com sucesso.", appointment)


class CompleteAppointmentUseCase:
    @staticmethod
    def execute(*, appointment, user):
        if appointment.status != Appointment.STATUS_CONFIRMED:
            return UseCaseResult(False, "Só é possível concluir marcações confirmadas.", appointment)

        with transaction.atomic():
            appointment.status = Appointment.STATUS_COMPLETED
            appointment.save(update_fields=["status", "updated_at"])

            AppointmentAuditService.log(
                appointment=appointment,
                action=AppointmentLog.ACTION_COMPLETE,
                user=user,
                description="Appointment completed.",
            )

        return UseCaseResult(True, "Marcação concluída com sucesso.", appointment)
