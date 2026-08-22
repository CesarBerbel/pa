"""A agenda interna de uma semana, em grelha.

Sete colunas de dias, uma linha por intervalo, e cada marcação a ocupar tantas
linhas quantas a sua duração — a forma como toda a gente já leu uma agenda,
incluindo a do Google.

O intervalo vem das regras de agenda: 15, 30 ou 60 minutos, conforme a forma de
trabalhar. Tudo o que aqui se calcula depende dele, por isso atravessa o módulo
em vez de ficar numa constante.

O que aqui se calcula é só a posição: em que linha começa cada coisa e quantas
ocupa. Quem decide o que existe em cada dia continua a ser o
`AvailabilityService`, para a semana não poder discordar do dia nem da agenda
pública.

A janela de horas não é fixa. Vem do horário de funcionamento dos sete dias, e
alarga-se para caber um encaixe posto fora dele: uma marcação que existe e não
aparece na agenda é pior do que uma grelha com uma linha a mais.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as Date, time, timedelta

from django.utils import timezone

from appointments.availability import AvailabilityService

# Usada quando não há horário de funcionamento nenhum na semana. Sem isto, uma
# semana de férias abria uma grelha sem altura nenhuma.
DEFAULT_START = time(8, 0)
DEFAULT_END = time(20, 0)


@dataclass
class WeekCell:
    """Uma célula da grelha: a hora que representa e se está livre.

    Livre é o que a torna clicável — carregar nela abre uma marcação nova já
    com o dia e a hora preenchidos, que é a razão de a grelha existir.
    """

    time: time
    row: int
    is_free: bool
    is_open: bool
    # A linha da hora certa leva um traço mais forte, como num calendário.
    is_hour: bool


@dataclass
class WeekDay:
    date: Date
    is_today: bool
    is_open: bool
    cells: list = field(default_factory=list)
    events: list = field(default_factory=list)


@dataclass
class WeeklySchedule:
    days: list
    row_labels: list
    first_slot: time
    slot_minutes: int

    @property
    def rows(self):
        return len(self.row_labels)


def week_start(selected_date):
    """A segunda-feira da semana desta data.

    Segunda e não domingo: é como o calendário é lido em Portugal, e é o que a
    faixa de dias da agenda pública já assume.
    """

    return selected_date - timedelta(days=selected_date.weekday())


def _minutos(momento):
    return momento.hour * 60 + momento.minute


def _limites_do_dia(dia, marcacoes, bloqueios):
    """A hora mais cedo e a mais tarde que este dia precisa de mostrar."""

    inicios = []
    fins = []

    for inicio, fim in AvailabilityService.get_business_periods(dia):
        inicios.append(_minutos(inicio.time()))
        fins.append(_minutos(fim.time()))

    for marcacao in marcacoes:
        inicios.append(_minutos(marcacao.start_time))
        fins.append(_minutos(marcacao.get_end_datetime().time()))

    for bloqueio in bloqueios:
        if bloqueio.is_full_day:
            continue

        inicios.append(_minutos(bloqueio.start_time))
        fins.append(_minutos(bloqueio.end_time))

    return inicios, fins


def _linha(minutos, primeiro_minuto, intervalo):
    """Em que linha da grelha cai este instante, a contar de 1."""

    return max(0, (minutos - primeiro_minuto)) // intervalo + 1


def _evento(kind, objeto, inicio, fim, primeiro_minuto, ultimo_minuto, intervalo):
    linha = _linha(inicio, primeiro_minuto, intervalo)
    # Pelo menos uma linha: um serviço de 15 minutos numa grelha de 30 ficaria
    # com altura zero e desaparecia.
    altura = max(1, _linha(min(fim, ultimo_minuto), primeiro_minuto, intervalo) - linha)

    return {
        "kind": kind,
        "row": linha,
        "span": altura,
        "appointment": objeto if kind == "appointment" else None,
        "block": objeto if kind == "block" else None,
        "_inicio": inicio,
        "_fim": fim,
    }


def _celulas_do_dia(dia, eventos, etiquetas, primeiro_minuto, intervalo):
    """As células deste dia, já a saber quais estão livres.

    Ocupada é qualquer célula que caia dentro de uma marcação ou de um
    bloqueio; fechada é a que fica fora do horário de funcionamento. Só as
    livres e abertas convidam a marcar.
    """

    periodos = [
        (_minutos(inicio.time()), _minutos(fim.time()))
        for inicio, fim in AvailabilityService.get_business_periods(dia)
    ]

    ocupados = [(evento["_inicio"], evento["_fim"]) for evento in eventos]

    celulas = []

    for indice, etiqueta in enumerate(etiquetas):
        inicio = primeiro_minuto + indice * intervalo
        fim = inicio + intervalo

        dentro = any(
            inicio >= abertura and fim <= fecho for abertura, fecho in periodos
        )
        livre = not any(
            inicio < ocupado_fim and fim > ocupado_inicio
            for ocupado_inicio, ocupado_fim in ocupados
        )

        celulas.append(
            WeekCell(
                time=etiqueta,
                row=indice + 1,
                is_free=livre and dentro,
                is_open=dentro,
                is_hour=etiqueta.minute == 0,
            )
        )

    return celulas


def build_week(selected_date):
    """A grelha da semana a que esta data pertence."""

    inicio_da_semana = week_start(selected_date)
    dias = [inicio_da_semana + timedelta(days=indice) for indice in range(7)]
    hoje = timezone.localdate()

    # Um lote só para a semana toda: sem isto seriam três consultas por dia.
    with AvailabilityService.batch():
        intervalo = AvailabilityService.get_slot_minutes()

        AvailabilityService.preload_appointments(dias)

        conteudo = {}
        inicios = []
        fins = []

        for dia in dias:
            marcacoes = list(AvailabilityService.get_active_appointments_for_date(dia))
            bloqueios = AvailabilityService.get_active_blocks_for_date(dia)

            conteudo[dia] = (marcacoes, bloqueios)

            dia_inicios, dia_fins = _limites_do_dia(dia, marcacoes, bloqueios)
            inicios.extend(dia_inicios)
            fins.extend(dia_fins)

        primeiro_minuto = min(inicios) if inicios else _minutos(DEFAULT_START)
        ultimo_minuto = max(fins) if fins else _minutos(DEFAULT_END)

        # Alinhar ao intervalo, para as linhas caírem em horas certas.
        primeiro_minuto -= primeiro_minuto % intervalo

        if ultimo_minuto % intervalo:
            ultimo_minuto += intervalo - (ultimo_minuto % intervalo)

        if ultimo_minuto <= primeiro_minuto:
            ultimo_minuto = primeiro_minuto + intervalo

        etiquetas = []
        minuto = primeiro_minuto

        while minuto < ultimo_minuto:
            etiquetas.append(time(minuto // 60, minuto % 60))
            minuto += intervalo

        semana = []

        for dia in dias:
            marcacoes, bloqueios = conteudo[dia]

            eventos = [
                _evento(
                    "block",
                    bloqueio,
                    (
                        primeiro_minuto
                        if bloqueio.is_full_day
                        else _minutos(bloqueio.start_time)
                    ),
                    (
                        ultimo_minuto
                        if bloqueio.is_full_day
                        else _minutos(bloqueio.end_time)
                    ),
                    primeiro_minuto,
                    ultimo_minuto,
                    intervalo,
                )
                for bloqueio in bloqueios
            ] + [
                _evento(
                    "appointment",
                    marcacao,
                    _minutos(marcacao.start_time),
                    _minutos(marcacao.get_end_datetime().time()),
                    primeiro_minuto,
                    ultimo_minuto,
                    intervalo,
                )
                for marcacao in marcacoes
            ]

            semana.append(
                WeekDay(
                    date=dia,
                    is_today=dia == hoje,
                    is_open=bool(AvailabilityService.get_business_periods(dia)),
                    cells=_celulas_do_dia(
                        dia, eventos, etiquetas, primeiro_minuto, intervalo
                    ),
                    events=eventos,
                )
            )

    return WeeklySchedule(
        days=semana,
        row_labels=etiquetas,
        first_slot=time(primeiro_minuto // 60, primeiro_minuto % 60),
        slot_minutes=intervalo,
    )


def day_agenda(day):
    """O mesmo dia, mas em lista, para quem o lê num telemóvel.

    A grelha da semana não cabe num ecrã de telemóvel — nem esticada, nem
    encolhida. O que cabe é um dia de cada vez, de cima para baixo, que é
    também como se lê uma agenda em papel.

    Não há dados novos: é a mesma informação que a coluna deste dia mostra,
    virada ao contrário. As linhas cobertas por uma marcação não se repetem —
    uma consulta de uma hora é uma linha, não quatro.
    """

    por_linha = {evento["row"]: evento for evento in day.events}

    linhas = []
    saltar_ate = 0

    for celula in day.cells:
        if celula.row < saltar_ate:
            continue

        evento = por_linha.get(celula.row)

        if evento:
            saltar_ate = celula.row + evento["span"]

        # Fora do horário e sem nada marcado não é informação nenhuma: numa
        # lista vertical, mostrá-lo era encher o ecrã de vazio.
        if not evento and not celula.is_open:
            continue

        linhas.append({"cell": celula, "event": evento})

    return linhas
