"""Envio dos emails de seguimento pós-atendimento.

Duas portas de entrada para o mesmo email: o comando diário, que o envia no
prazo configurado, e o botão da área interna, que o envia agora. Ambas passam
por `send_followup`, para o registo de envios ficar igual nos dois casos e o
automático não repetir o que já foi enviado à mão.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from appointments.models import Appointment, AppointmentReminderLog
from notifications.models import ServiceFollowUp

# Um seguimento muito atrasado deixa de fazer sentido: instruções de cuidados
# "15 dias depois" que chegam dois meses depois confundem mais do que ajudam.
# Se o comando estiver parado mais do que isto, o envio é dado como perdido.
DEFAULT_MAX_DELAY_DAYS = 7


@dataclass
class FollowUpResult:
    success: bool
    message: str


def followups_for(appointment):
    """Mensagens configuradas para o serviço desta marcação.

    Todas, incluindo as manuais: é esta lista que o ecrã da marcação mostra a
    quem quer mandar alguma coisa à mão.
    """

    if not appointment.service_id:
        return ServiceFollowUp.objects.none()

    return ServiceFollowUp.objects.filter(
        service_id=appointment.service_id
    ).select_related("email_template", "service")


def completion_messages_for(appointment):
    """As mensagens que este serviço manda no fim do atendimento.

    Só as ativas: uma mensagem desligada é uma decisão de quem gere a clínica,
    e concluir um atendimento não a deve contornar.
    """

    return followups_for(appointment).filter(
        trigger=ServiceFollowUp.TRIGGER_COMPLETION,
        is_active=True,
    )


def was_sent(appointment, followup):
    return AppointmentReminderLog.objects.filter(
        appointment=appointment,
        reminder_type=followup.get_log_key(),
        status=AppointmentReminderLog.STATUS_SUCCESS,
    ).exists()


def last_sent_at(appointment, followup):
    registo = (
        AppointmentReminderLog.objects.filter(
            appointment=appointment,
            reminder_type=followup.get_log_key(),
            status=AppointmentReminderLog.STATUS_SUCCESS,
        )
        .order_by("-sent_at")
        .first()
    )

    return registo.sent_at if registo else None


def eligible_appointments(followup, today=None, max_delay_days=DEFAULT_MAX_DELAY_DAYS):
    """Marcações a que falta enviar este seguimento.

    Três limites, cada um a evitar um erro concreto:

    * mensagens que não são de prazo ficam de fora, porque não têm prazo
      nenhum a cumprir;
    * marcações canceladas ficam de fora — o atendimento não aconteceu;
    * marcações anteriores à criação da regra ficam de fora, senão ativar um
      seguimento hoje despejava o email em cima de toda a gente que fez o
      serviço no ano passado;
    * marcações cujo prazo já passou há muito ficam de fora, porque o email
      chegaria fora de tempo.
    """

    today = today or timezone.localdate()

    # Só as de prazo têm prazo. As do fim do atendimento saem quando a marcação
    # é concluída, e as manuais só saem quando alguém carregar no botão.
    if followup.trigger != ServiceFollowUp.TRIGGER_DELAYED:
        return Appointment.objects.none()

    fim = today - timedelta(days=followup.days_after)
    inicio = fim - timedelta(days=max_delay_days)

    return (
        Appointment.objects.filter(
            service_id=followup.service_id,
            date__gte=max(inicio, followup.created_at.date()),
            date__lte=fim,
        )
        .exclude(status=Appointment.STATUS_CANCELLED)
        .exclude(customer__email="")
        .exclude(
            reminder_logs__reminder_type=followup.get_log_key(),
            reminder_logs__status=AppointmentReminderLog.STATUS_SUCCESS,
        )
        .select_related("customer", "service")
        .order_by("date", "start_time")
    )


def send_followup(appointment, followup):
    """Envia o seguimento e regista o resultado.

    O registo é o mesmo que o comando diário consulta, portanto um envio
    manual impede o automático de repetir o email mais tarde.
    """

    from appointments.emails import send_service_followup_email

    if not appointment.customer.email:
        return FollowUpResult(False, "Este cliente não tem email registado.")

    try:
        send_service_followup_email(appointment=appointment, followup=followup)
    except Exception as error:
        AppointmentReminderLog.objects.create(
            appointment=appointment,
            reminder_type=followup.get_log_key(),
            status=AppointmentReminderLog.STATUS_ERROR,
            error_message=str(error),
        )

        return FollowUpResult(False, f"Não foi possível enviar: {error}")

    AppointmentReminderLog.objects.create(
        appointment=appointment,
        reminder_type=followup.get_log_key(),
        status=AppointmentReminderLog.STATUS_SUCCESS,
    )

    return FollowUpResult(True, f"Email enviado para {appointment.customer.email}.")
