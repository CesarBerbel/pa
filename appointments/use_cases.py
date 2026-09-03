from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from appointments.audit_services import AppointmentAuditService
from appointments.emails import (
    deliver_after_commit,
    send_appointment_completed_email,
    send_appointment_confirmation_email,
)
from appointments.models import Appointment, AppointmentLog
from notifications.models import WhatsAppEventSetting
from notifications.whatsapp_dispatch import notify as notify_whatsapp
from notifications.whatsapp import WhatsAppAppointmentNotificationService


@dataclass
class UseCaseResult:
    success: bool
    message: str
    appointment: Appointment | None = None


def confirmation_event_for(appointment):
    """Qual dos dois textos de confirmação se aplica a esta marcação.

    Um pedido feito no site recebe uma resposta ao pedido; uma marcação
    combinada ao telefone recebe o registo do que ficou combinado. São coisas
    diferentes e por isso são dois acontecimentos, cada um com o seu texto e o
    seu interruptor.
    """

    if appointment.origin == Appointment.ORIGIN_INTERNAL:
        return WhatsAppEventSetting.EVENT_APPOINTMENT_CONFIRMED_INTERNAL

    return WhatsAppEventSetting.EVENT_APPOINTMENT_CONFIRMED


def deliver_confirmation_message(appointment, *, send_email=True, override=None):
    """Manda à cliente a confirmação da marcação: email e WhatsApp.

    Existe à parte do caso de uso porque a confirmação deixou de vir sempre do
    mesmo sítio: uma marcação criada na área interna já nasce confirmada, e a
    mensagem que a cliente recebe tem de ser exatamente a mesma que receberia
    se alguém carregasse depois no botão de confirmar.

    `override` é o que a janela de confirmação mudou — a língua, e o texto se
    alguém o reescreveu. Vale para este envio e não é gravado.
    """

    if send_email:
        deliver_after_commit(
            send_appointment_confirmation_email,
            appointment,
            override=override,
        )

    deliver_after_commit(
        notify_whatsapp,
        appointment,
        confirmation_event_for(appointment),
        override=override,
    )


def deliver_completion_message(appointment):
    """O que a cliente recebe no fim do atendimento.

    Um serviço pode ter mensagens próprias para este momento — as instruções
    de cuidados de uma remoção de calos não são as de uma manicure. Quando
    existem, são essas que saem; quando não existem, sai o agradecimento
    comum. O WhatsApp segue nos dois casos: é curto e não substitui o email.
    """

    from notifications.followup_services import completion_messages_for, send_followup

    proprias = list(completion_messages_for(appointment))

    if proprias:
        for mensagem in proprias:
            deliver_after_commit(send_followup, appointment, mensagem)
    else:
        deliver_after_commit(send_appointment_completed_email, appointment)

    deliver_after_commit(
        notify_whatsapp,
        appointment,
        WhatsAppEventSetting.EVENT_APPOINTMENT_COMPLETED,
    )


class ConfirmAppointmentUseCase:
    @staticmethod
    def execute(
        *,
        appointment,
        user,
        send_email=True,
        send_whatsapp=True,
        send_message=True,
        override=None,
    ):
        """Confirma a marcação e, se assim for pedido, avisa a cliente.

        `send_message` responde à pergunta feita no ecrã: com ela em falso, a
        marcação é confirmada em silêncio. Os outros dois continuam a existir
        para escolher canais dentro de um envio que já foi decidido.
        """

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
                True, "Esta marcação já estava confirmada.", appointment
            )

        with transaction.atomic():
            appointment = (
                Appointment.objects.select_for_update()
                .select_related("customer", "service", "service__category")
                .get(pk=appointment.pk)
            )

            if appointment.status == Appointment.STATUS_CANCELLED:
                return UseCaseResult(
                    False,
                    "Marcações canceladas não podem ser confirmadas.",
                    appointment,
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

            anterior = AppointmentAuditService.snapshot(appointment)

            appointment.status = Appointment.STATUS_CONFIRMED
            appointment.save(update_fields=["status", "updated_at"])

            alteracoes = AppointmentAuditService.diff(
                anterior, AppointmentAuditService.snapshot(appointment)
            )

            AppointmentAuditService.log(
                appointment=appointment,
                action=AppointmentLog.ACTION_CONFIRM,
                user=user,
                description="Marcação confirmada.",
                source=AppointmentLog.SOURCE_INTERNAL,
                changes=alteracoes,
            )

            if send_message:
                deliver_confirmation_message(
                    appointment, send_email=send_email, override=override
                )

        if not send_message:
            return UseCaseResult(
                True,
                "Marcação confirmada. Não foi enviada mensagem à cliente.",
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
    def execute(*, appointment, user, send_message=True):
        if appointment.status != Appointment.STATUS_CONFIRMED:
            return UseCaseResult(
                False, "Só é possível concluir marcações confirmadas.", appointment
            )

        with transaction.atomic():
            anterior = AppointmentAuditService.snapshot(appointment)

            appointment.status = Appointment.STATUS_COMPLETED
            appointment.save(update_fields=["status", "updated_at"])

            alteracoes = AppointmentAuditService.diff(
                anterior, AppointmentAuditService.snapshot(appointment)
            )

            AppointmentAuditService.log(
                appointment=appointment,
                action=AppointmentLog.ACTION_COMPLETE,
                user=user,
                description="Atendimento concluído.",
                source=AppointmentLog.SOURCE_INTERNAL,
                changes=alteracoes,
            )

            if send_message:
                deliver_completion_message(appointment)

        if not send_message:
            return UseCaseResult(
                True,
                "Marcação concluída. Não foi enviada mensagem à cliente.",
                appointment,
            )

        return UseCaseResult(True, "Marcação concluída com sucesso.", appointment)
