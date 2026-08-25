"""Lembretes: avisar quem tem marcação a chegar.

Quem se esquece não avisa, e uma vaga que se perde por esquecimento perde-se
duas vezes — a pessoa não é atendida e mais ninguém ocupa a hora. O lembrete
existe sobretudo para isso: dar tempo de desmarcar.

**A antecedência é uma janela e não um instante.** O comando corre de meia em
meia hora, não ao segundo, e um servidor pode ter estado em baixo. Por isso a
regra é "está na hora, ou passou há pouco", com uma tolerância que apanha
algumas passagens falhadas sem nunca mandar um lembrete de uma marcação que já
começou.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from appointments.models import Appointment, AppointmentReminderLog

# Quanto tempo depois do momento certo é que ainda vale a pena avisar.
#
# Três horas cobrem seis passagens falhadas do comando. Mais do que isso, o
# lembrete chegaria tarde de mais para servir de alguma coisa — e a pessoa
# recebia um aviso de uma coisa que é daqui a bocado.
TOLERANCIA = timedelta(hours=3)


def log_key(hours):
    """O nome com que este lembrete fica registado.

    Leva as horas dentro: mudar a antecedência nas definições passa a ser um
    lembrete diferente, e quem já recebeu o de vinte e quatro horas pode
    receber o de duas sem que o registo os confunda.
    """

    return f"reminder_{hours}h"


def start_datetime(appointment):
    return timezone.make_aware(
        datetime.combine(appointment.date, appointment.start_time),
        timezone.get_current_timezone(),
    )


def due(hours, now=None):
    """As marcações a quem está na hora de mandar o lembrete.

    Quatro condições, e cada uma evita um erro concreto:

    * o momento certo já chegou, e não passou há mais do que a tolerância;
    * a marcação ainda não começou — um lembrete depois da hora não serve;
    * não está cancelada nem concluída;
    * ainda não foi avisada com esta antecedência.
    """

    if hours <= 0:
        return Appointment.objects.none()

    now = now or timezone.now()

    limite = now + timedelta(hours=hours)
    inicio = limite - TOLERANCIA

    candidatas = (
        Appointment.objects.filter(
            date__gte=inicio.date(),
            date__lte=limite.date(),
        )
        .exclude(status=Appointment.STATUS_CANCELLED)
        .exclude(status=Appointment.STATUS_COMPLETED)
        .exclude(
            reminder_logs__reminder_type=log_key(hours),
            reminder_logs__status=AppointmentReminderLog.STATUS_SUCCESS,
        )
        .select_related("customer", "service")
        .order_by("date", "start_time")
    )

    # A hora exata resolve-se em Python: a data é um campo e a hora é outro, e
    # compará-las juntas na base de dados obrigava a expressões que mudam de
    # sintaxe entre o SQLite dos testes e o PostgreSQL de produção.
    return [
        marcacao
        for marcacao in candidatas
        if now < start_datetime(marcacao) <= limite
        and start_datetime(marcacao) > inicio
    ]


def record(appointment, hours, error=""):
    return AppointmentReminderLog.objects.create(
        appointment=appointment,
        reminder_type=log_key(hours),
        status=(
            AppointmentReminderLog.STATUS_ERROR
            if error
            else AppointmentReminderLog.STATUS_SUCCESS
        ),
        error_message=error,
    )
