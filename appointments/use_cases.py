from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from appointments.audit_services import AppointmentAuditService
from appointments.emails import (
    deliver_after_commit,
    send_appointment_confirmation_email,
)
from appointments.models import Appointment, AppointmentLog
from notifications.whatsapp import WhatsAppAppointmentNotificationService


@dataclass
class UseCaseResult:
    success: bool
    message: str
    appointment: Appointment | None = None


class ConfirmAppointmentUseCase:
    @staticmethod
    def execute(*, appointment, user, send_email=True, send_whatsapp=True):
        if appointment.status == Appointment.STATUS_CANCELLED:
            return UseCaseResult(
                False, "Marcações canceladas não podem ser confirmadas.", appointment
            )

        if appointment.status == Appointment.STATUS_COMPLETED:
            return UseCaseResult(
                False, "Marcações concluídas não podem ser confirmadas novamente.", appointment
            )

        if appointment.status == Appointment.STATUS_CONFIRMED:
            return UseCaseResult(True, "Esta marcação já estava confirmada.", appointment)

        with transaction.atomic():
            appointment = (
                Appointment.objects.select_for_update()
                .select_related("customer", "service", "service__category")
                .get(pk=appointment.pk)
            )

            if appointment.status == Appointment.STATUS_CANCELLED:
                return UseCaseResult(
                    False, "Marcações canceladas não podem ser confirmadas.", appointment
                )

            if appointment.status == Appointment.STATUS_COMPLETED:
                return UseCaseResult(
                    False,
                    "Marcações concluídas não podem ser confirmadas novamente.",
                    appointment,
                )

            if appointment.status == Appointment.STATUS_CONFIRMED:
                return UseCaseResult(
                    True,
                    "Esta marcação já estava confirmada.",
                    appointment,
                )

            appointment.status = Appointment.STATUS_CONFIRMED
            appointment.save(update_fields=["status", "updated_at"])

            AppointmentAuditService.log(
                appointment=appointment,
                action=AppointmentLog.ACTION_CONFIRM,
                user=user,
                description="Appointment confirmed.",
            )

            if send_email:
                deliver_after_commit(
                    send_appointment_confirmation_email,
                    appointment,
                )

        result_message = "Marcação confirmada com sucesso."

        if send_whatsapp:
            whatsapp_result = WhatsAppAppointmentNotificationService.send_confirmation(
                appointment
            )

            should_show_skip_message = (
                whatsapp_result.skipped and settings.WHATSAPP_CLOUD_API_ENABLED
            )

            if should_show_skip_message or (
                whatsapp_result.success and not whatsapp_result.skipped
            ):
                result_message = f"{result_message} {whatsapp_result.message}"
            elif not whatsapp_result.success:
                result_message = (
                    f"{result_message} Não foi possível enviar o WhatsApp: "
                    f"{whatsapp_result.message}"
                )

        return UseCaseResult(True, result_message, appointment)


class CompleteAppointmentUseCase:
    @staticmethod
    def execute(*, appointment, user):
        if appointment.status != Appointment.STATUS_CONFIRMED:
            return UseCaseResult(
                False, "Só é possível concluir marcações confirmadas.", appointment
            )

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
