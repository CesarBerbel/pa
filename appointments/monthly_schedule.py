"""O mês inteiro em grelha, com quem vem em cada dia.

A semana mostra as horas; o mês mostra os nomes. São perguntas diferentes:
na semana pergunta-se "onde há espaço", no mês pergunta-se "como está o mês"
— quantos dias estão cheios, onde há buracos, e quem vem em cada um.

Cada célula lista as marcações do dia pela hora. Como uma célula de um sétimo
da largura não leva doze nomes, mostra as primeiras e diz quantas ficaram por
mostrar; o dia inteiro está sempre a um clique.

Uma consulta para o mês todo, e não uma por dia: 35 ou 42 células dariam 42
consultas, e a página abre-se muitas vezes ao dia.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils import timezone

from django.urls import reverse

from appointments.availability import AvailabilityService
from appointments.models import Appointment

# Quantas marcações cabem numa célula antes de a lista passar a "+N".
MAX_POR_DIA = 3


@dataclass
class MonthEntry:
    """Uma marcação, reduzida ao que a célula do mês mostra."""

    time: str
    name: str
    status: str
    is_cancelled: bool
    url: str


@dataclass
class MonthDay:
    date: date
    in_month: bool
    is_today: bool
    is_blocked: bool
    entries: list[MonthEntry] = field(default_factory=list)

    @property
    def visible_entries(self):
        return self.entries[:MAX_POR_DIA]

    @property
    def hidden_count(self):
        return max(0, len(self.entries) - MAX_POR_DIA)


@dataclass
class MonthlySchedule:
    year: int
    month: int
    weeks: list[list[MonthDay]]
    previous_month: date
    next_month: date

    @property
    def first_day(self):
        return date(self.year, self.month, 1)

    @property
    def days_with_appointments(self):
        return [dia for semana in self.weeks for dia in semana if dia.entries]


def month_start(selected_date):
    return selected_date.replace(day=1)


def _grelha(ano, mes):
    """Os dias que a grelha mostra, semanas completas de segunda a domingo.

    Inclui os dias do mês anterior e do seguinte que caem nas semanas das
    pontas: uma grelha com buracos nos cantos lê-se pior do que uma cheia,
    e esses dias vão marcados como fora do mês.
    """

    calendario = calendar.Calendar(firstweekday=0)

    return calendario.monthdatescalendar(ano, mes)


def _marcacoes_do_mes(primeiro, ultimo):
    return (
        Appointment.objects.filter(date__gte=primeiro, date__lte=ultimo)
        .select_related("customer", "service")
        .order_by("date", "start_time")
    )


def _dias_bloqueados(dias):
    """Dias fechados por um bloqueio de dia inteiro.

    Um bloqueio de duas horas não muda a leitura do mês — vê-se no dia. Um dia
    inteiro fechado muda, porque é um dia onde não se marca nada.

    Quem responde é o `AvailabilityService`, e não uma consulta feita aqui: os
    bloqueios podem ser recorrentes, e reimplementar essa regra ao lado dela
    era garantir que as duas divergiam à primeira alteração.
    """

    return {dia for dia in dias if AvailabilityService.get_full_day_block_for_date(dia)}


def build_month(selected_date):
    """A grelha do mês de `selected_date`, pronta para o template."""

    primeiro_do_mes = month_start(selected_date)
    semanas = _grelha(primeiro_do_mes.year, primeiro_do_mes.month)

    primeiro = semanas[0][0]
    ultimo = semanas[-1][-1]

    por_dia = {}

    for marcacao in _marcacoes_do_mes(primeiro, ultimo):
        por_dia.setdefault(marcacao.date, []).append(
            MonthEntry(
                time=marcacao.start_time.strftime("%H:%M"),
                name=marcacao.customer.full_name,
                status=marcacao.status,
                is_cancelled=marcacao.status == Appointment.STATUS_CANCELLED,
                url=reverse("appointments:appointment_detail", args=[marcacao.pk]),
            )
        )

    todos_os_dias = [dia for semana in semanas for dia in semana]

    # Um lote para o mês todo: sem ele, cada dia repetia as consultas dos
    # horários de funcionamento e dos bloqueios — 42 vezes.
    with AvailabilityService.batch():
        bloqueados = _dias_bloqueados(todos_os_dias)

    hoje = timezone.localdate()

    grelha = [
        [
            MonthDay(
                date=dia,
                in_month=dia.month == primeiro_do_mes.month,
                is_today=dia == hoje,
                is_blocked=dia in bloqueados,
                entries=por_dia.get(dia, []),
            )
            for dia in semana
        ]
        for semana in semanas
    ]

    return MonthlySchedule(
        year=primeiro_do_mes.year,
        month=primeiro_do_mes.month,
        weeks=grelha,
        previous_month=(primeiro_do_mes - timedelta(days=1)).replace(day=1),
        next_month=(
            primeiro_do_mes + timedelta(days=calendar.monthrange(
                primeiro_do_mes.year, primeiro_do_mes.month
            )[1])
        ),
    )
