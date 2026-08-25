"""Retornos: a intenção de voltar, e o que se faz com ela.

Um retorno nasce no fim de um atendimento — que é o único momento em que quem
atende sabe se é preciso voltar — e vive até ser marcado, dispensado, ou até a
data-alvo passar sem que nada aconteça.

O que este módulo guarda é a diferença entre um retorno e um lembrete escrito
nas observações: um retorno tem estado, tem data-alvo e aparece numa lista.
Uma frase nas observações não tem nada disso, e por isso não volta a ser lida.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from appointments.models import Appointment, ReturnVisit

# Quantos dias antes da data-alvo é que a cliente é avisada.
#
# Uma semana: dá tempo de escolher um horário que preste, e não é tão cedo que
# a mensagem se perca antes de a data chegar.
DIAS_DE_AVISO = 7

# Um retorno cuja data-alvo passou há muito não se avisa: a mensagem chegaria
# a dizer que estava na altura de voltar há dois meses. Fica na lista, como
# atrasado, para alguém decidir o que fazer.
DIAS_DE_ATRASO_ACEITAVEL = 30


def suggested_days(appointment):
    """O prazo que o serviço deste atendimento propõe. Zero é não propor."""

    return getattr(appointment.service, "return_days", 0) or 0


def create_from_appointment(appointment, days, user=None, notes=""):
    """Abre um retorno a partir do atendimento que acabou.

    A data-alvo conta-se a partir do dia do atendimento e não de hoje: uma
    marcação concluída com atraso — no dia seguinte, ao arrumar a agenda — não
    pode empurrar o retorno um dia para a frente.
    """

    if days <= 0:
        return None

    return ReturnVisit.objects.create(
        customer=appointment.customer,
        origin=appointment,
        service=appointment.service,
        target_date=appointment.date + timedelta(days=days),
        created_by=user if user and user.is_authenticated else None,
        notes=notes,
    )


def attach_appointment(return_visit, appointment):
    """Dá o retorno por marcado, com a marcação que o cumpre."""

    return_visit.appointment = appointment
    return_visit.status = ReturnVisit.STATUS_SCHEDULED
    return_visit.save(update_fields=["appointment", "status", "updated_at"])

    return return_visit


def dismiss(return_visit):
    """Dispensa o retorno sem o apagar.

    Apagá-lo perdia a decisão: no mês seguinte ninguém sabia se aquela pessoa
    tinha sido dispensada ou se o retorno nunca chegou a existir.
    """

    return_visit.status = ReturnVisit.STATUS_DISMISSED
    return_visit.save(update_fields=["status", "updated_at"])

    return return_visit


def pending(today=None):
    """Os retornos por marcar, do mais antigo para o mais recente.

    Os atrasados vêm primeiro por serem os mais antigos: é essa a ordem em que
    interessa telefonar.
    """

    return (
        ReturnVisit.objects.filter(status=ReturnVisit.STATUS_PENDING)
        .select_related("customer", "service", "origin")
        .order_by("target_date", "customer__full_name")
    )


def late(today=None):
    today = today or timezone.localdate()

    return pending().filter(target_date__lt=today)


def due_for_notice(today=None, lead_days=DIAS_DE_AVISO):
    """Os retornos a quem está na altura de mandar a mensagem.

    Três condições, e cada uma evita um erro concreto:

    * ainda por marcar — quem já marcou não precisa de ser convidada a marcar;
    * dentro da janela — nem antes de tempo, nem tão atrasado que a mensagem
      chegue a falar de uma data que passou há meses;
    * ainda não avisada — o comando corre todos os dias e não pode repetir.
    """

    today = today or timezone.localdate()

    return (
        pending()
        .filter(
            notified_at__isnull=True,
            target_date__lte=today + timedelta(days=lead_days),
            target_date__gte=today - timedelta(days=DIAS_DE_ATRASO_ACEITAVEL),
        )
        .exclude(customer__email="", customer__phone="")
    )


def already_booked(return_visit, today=None):
    """A cliente já marcou por si, sem passar pelo retorno?

    Acontece: recebe a mensagem, entra no site e marca. Mandar-lhe outra a
    dizer que está na altura de voltar seria falar com quem já voltou.
    """

    today = today or timezone.localdate()

    return (
        Appointment.objects.filter(
            customer=return_visit.customer,
            date__gte=today,
        )
        .exclude(status=Appointment.STATUS_CANCELLED)
        .filter(Q(service=return_visit.service) | Q(service__isnull=True))
        .exists()
    )


def mark_notified(return_visit):
    return_visit.notified_at = timezone.now()
    return_visit.save(update_fields=["notified_at", "updated_at"])

    return return_visit
