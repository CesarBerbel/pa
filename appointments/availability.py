from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from appointments.models import Appointment, BusinessHour, ScheduleBlock


@dataclass(frozen=True)
class AvailableSlot:
    value: str
    label: str

    def as_dict(self) -> dict[str, str]:
        return {"value": self.value, "label": self.label}


@dataclass
class _Lote:
    """O que já foi lido da base dentro de um `AvailabilityService.batch()`."""

    business_hours: dict[int, BusinessHour] | None = None
    active_blocks: list[ScheduleBlock] | None = None
    blocks_by_date: dict = field(default_factory=dict)
    appointments_by_date: dict = field(default_factory=dict)


# ContextVar e não uma variável de módulo: cada pedido corre na sua própria
# cópia, e um lote aberto num pedido nunca é visto por outro que corra ao mesmo
# tempo no mesmo processo.
_lote_ativo: ContextVar[_Lote | None] = ContextVar("availability_batch", default=None)


class AvailabilityService:
    """Centralizes schedule availability and conflict rules.

    This module is the single place for business-hour validation, schedule blocks,
    appointment overlap detection and public slot generation.
    """

    slot_minutes = 30

    @classmethod
    @contextmanager
    def batch(cls):
        """Lê horário, bloqueios e marcações uma vez só, para o bloco inteiro.

        Quem desenha uma agenda percorre dias: a faixa da agenda pública pede o
        estado de sete de cada vez, e cada dia repetia as mesmas consultas ao
        horário de funcionamento e aos bloqueios ativos — 45 consultas para
        desenhar uma página.

        **Só para leitura.** Dentro do bloco, o horário e os bloqueios ficam
        congelados no que foram no início; validar uma marcação aqui dentro
        arriscava aceitá-la contra dados que entretanto mudaram. Validação e
        gravação ficam de fora, e por isso continuam a ler tudo de fresco.
        """

        token = _lote_ativo.set(_Lote())

        try:
            yield
        finally:
            _lote_ativo.reset(token)

    @classmethod
    def get_business_hour(cls, selected_date):
        lote = _lote_ativo.get()

        if lote is None:
            return BusinessHour.objects.filter(
                weekday=selected_date.weekday(),
                is_active=True,
            ).first()

        if lote.business_hours is None:
            # São sete linhas no total: vale mais trazê-las todas do que voltar
            # à base por cada dia desenhado.
            lote.business_hours = {
                hora.weekday: hora
                for hora in BusinessHour.objects.filter(is_active=True)
            }

        return lote.business_hours.get(selected_date.weekday())

    @classmethod
    def get_business_periods(cls, selected_date, business_hour=None):
        """Períodos de trabalho do dia, como pares de datetime.

        Um dia com pausa de almoço tem dois períodos. Todo o cálculo de
        disponibilidade passa por aqui, para a pausa não depender de um
        bloqueio recorrente.
        """

        business_hour = business_hour or cls.get_business_hour(selected_date)

        if not business_hour:
            return []

        return [
            (
                datetime.combine(selected_date, inicio),
                datetime.combine(selected_date, fim),
            )
            for inicio, fim in business_hour.periods
        ]

    @classmethod
    def get_business_day_bounds(cls, selected_date, business_hour=None):
        # Início do primeiro período e fim do último, para comparações que
        # olham para o dia como um todo.
        periods = cls.get_business_periods(selected_date, business_hour)

        if not periods:
            return None, None

        return periods[0][0], periods[-1][1]

    @classmethod
    def get_active_blocks_for_date(cls, selected_date):
        # A consulta não depende da data — `applies_to_date` é que decide, já em
        # Python. Dentro de um lote, os bloqueios ativos são lidos uma vez e
        # filtrados tantas vezes quantas as datas pedidas.
        lote = _lote_ativo.get()

        if lote is None:
            ativos = ScheduleBlock.objects.filter(is_active=True).order_by("start_time")
        else:
            if selected_date in lote.blocks_by_date:
                return lote.blocks_by_date[selected_date]

            if lote.active_blocks is None:
                lote.active_blocks = list(
                    ScheduleBlock.objects.filter(is_active=True).order_by("start_time")
                )

            ativos = lote.active_blocks

        do_dia = [block for block in ativos if block.applies_to_date(selected_date)]

        if lote is not None:
            lote.blocks_by_date[selected_date] = do_dia

        return do_dia

    @classmethod
    def preload_appointments(cls, dates):
        """Traz as marcações de vários dias numa consulta só.

        A faixa da agenda pública mostra sete dias ao mesmo tempo. Sem isto,
        são sete consultas iguais em tudo menos na data. Fora de um lote não
        faz nada: sem onde guardar, adiantar a leitura não pouparia consulta
        nenhuma.
        """

        lote = _lote_ativo.get()

        if lote is None:
            return

        em_falta = {data for data in dates if data not in lote.appointments_by_date}

        if not em_falta:
            return

        por_data = {data: [] for data in em_falta}

        marcacoes = (
            Appointment.objects.filter(date__in=em_falta)
            .exclude(status=Appointment.STATUS_CANCELLED)
            .select_related("customer", "service")
            .order_by("start_time")
        )

        for marcacao in marcacoes:
            por_data[marcacao.date].append(marcacao)

        lote.appointments_by_date.update(por_data)

    @classmethod
    def get_active_appointments_for_date(cls, selected_date, exclude_pk=None):
        appointments = (
            Appointment.objects.filter(
                date=selected_date,
            )
            .exclude(
                status=Appointment.STATUS_CANCELLED,
            )
            .select_related(
                "customer",
                "service",
            )
            .order_by(
                "start_time",
            )
        )

        if exclude_pk:
            # Um pedido com exclusão é sempre sobre uma marcação concreta, e
            # nunca se repete dentro do mesmo desenho: não vale a pena guardar.
            return appointments.exclude(pk=exclude_pk)

        lote = _lote_ativo.get()

        if lote is None:
            return appointments

        if selected_date not in lote.appointments_by_date:
            # Avaliar aqui deixa o queryset com o resultado em memória: quem o
            # receber outra vez percorre-o sem voltar à base.
            len(appointments)
            lote.appointments_by_date[selected_date] = appointments

        return lote.appointments_by_date[selected_date]

    @staticmethod
    def overlaps(first_start, first_end, second_start, second_end):
        return first_start < second_end and first_end > second_start

    @classmethod
    def schedule_conflict(cls, service, selected_date, start_time):
        """Porque é que este horário está fora da agenda normal, ou None.

        Separado da validação porque a área interna precisa da mesma resposta
        sem que ela seja fatal: a profissional pode encaixar alguém fora do
        horário, mas convém dizer-lhe que foi isso que aconteceu.
        """

        if not service or not selected_date or not start_time:
            return None

        periods = cls.get_business_periods(selected_date)

        if not periods:
            return "Não há horário de funcionamento ativo para este dia."

        inicio = datetime.combine(selected_date, start_time)
        fim = inicio + timedelta(minutes=service.duration_minutes)

        # Tem de caber inteira num período: um atendimento que começasse antes
        # do almoço e terminasse depois atravessaria a pausa.
        cabe = any(
            inicio >= periodo_inicio and fim <= periodo_fim
            for periodo_inicio, periodo_fim in periods
        )

        if not cabe:
            return "A marcação está fora do horário de funcionamento."

        for block in cls.get_active_blocks_for_date(selected_date):
            block_start = block.get_start_datetime_for_date(selected_date)
            block_end = block.get_end_datetime_for_date(selected_date)

            if cls.overlaps(inicio, fim, block_start, block_end):
                return f"Este horário está bloqueado: {block.title}."

        return None

    @classmethod
    def appointment_conflict(cls, appointment):
        """Outra marcação ativa que se sobreponha a esta, ou None.

        Compara os intervalos completos, e não só a hora de início: um serviço
        de 60 minutos às 09:00 colide com outro às 09:30.
        """

        inicio = appointment.get_start_datetime()
        fim = appointment.get_end_datetime()

        for existing in cls.get_active_appointments_for_date(
            appointment.date,
            exclude_pk=appointment.pk,
        ):
            if cls.overlaps(
                inicio, fim, existing.get_start_datetime(), existing.get_end_datetime()
            ):
                return existing

        return None

    @classmethod
    def validate_appointment(cls, appointment):
        if appointment.status == Appointment.STATUS_CANCELLED:
            return

        # Testar service_id em vez de service: num formulário submetido sem
        # serviço, aceder a appointment.service levanta RelatedObjectDoesNotExist
        # e rebenta com 500 antes de o Django poder mostrar o erro de campo.
        if not appointment.service_id:
            return

        if not appointment.service.is_active:
            raise ValidationError(
                "Não é possível marcar horário para um serviço inativo."
            )

        if not appointment.date or not appointment.start_time:
            return

        # Num encaixe o horário e os bloqueios já foram dispensados de forma
        # deliberada na área interna. A sobreposição com outra marcação nunca é
        # dispensada: essa não é uma questão de política, é impossível de
        # cumprir.
        if not appointment.outside_schedule:
            motivo = cls.schedule_conflict(
                appointment.service,
                appointment.date,
                appointment.start_time,
            )

            if motivo:
                raise ValidationError(motivo)

        if cls.appointment_conflict(appointment):
            raise ValidationError(
                "Este horário entra em conflito com outra marcação existente."
            )

    @classmethod
    def get_availability_status(cls, service, selected_date, public_safe=False):
        business_hour = cls.get_business_hour(selected_date)

        if not business_hour:
            return {
                "type": "closed",
                "is_fully_blocked": True,
                "title": "Dia sem atendimento",
                "message": "Não existe horário de funcionamento ativo para esta data.",
                "icon": "bi-calendar-x",
                "block_title": "",
                "block_notes": "",
            }

        business_start, business_end = cls.get_business_day_bounds(
            selected_date, business_hour
        )

        for block in cls.get_active_blocks_for_date(selected_date):
            block_start = block.get_start_datetime_for_date(selected_date)
            block_end = block.get_end_datetime_for_date(selected_date)

            if block.is_full_day or (
                block_start <= business_start and block_end >= business_end
            ):
                status = {
                    "type": "full_day_blocked",
                    "is_fully_blocked": True,
                    "title": "Horários esgotados",
                    "message": "Horários esgotados, favor verificar outro dia.",
                    "icon": "bi-clock-history",
                    "block_title": "",
                    "block_notes": "",
                }

                if not public_safe:
                    status.update(
                        {
                            "title": "Dia totalmente bloqueado",
                            "message": "Esta data está indisponível para marcações.",
                            "icon": "bi-slash-circle",
                            "block_title": block.title,
                            "block_notes": block.notes,
                        }
                    )

                return status

        if service and public_safe:
            slots = cls.get_public_available_slots(service, selected_date)
        else:
            slots = cls.get_available_slots(service, selected_date) if service else []

        if service and not slots:
            return {
                "type": "no_slots",
                "is_fully_blocked": False,
                "title": "Horários esgotados",
                "message": "Horários esgotados, favor verificar outro dia.",
                "icon": "bi-clock-history",
                "block_title": "",
                "block_notes": "",
            }

        return {
            "type": "available",
            "is_fully_blocked": False,
            "title": "Horários disponíveis",
            "message": "Escolha um horário disponível para concluir a marcação.",
            "icon": "bi-calendar-check",
            "block_title": "",
            "block_notes": "",
        }

    @classmethod
    def get_full_day_block_for_date(cls, selected_date, business_hour=None):
        business_start, business_end = cls.get_business_day_bounds(
            selected_date, business_hour
        )

        if business_start is None:
            return None

        for block in cls.get_active_blocks_for_date(selected_date):
            block_start = block.get_start_datetime_for_date(selected_date)
            block_end = block.get_end_datetime_for_date(selected_date)

            if block.is_full_day or (
                block_start <= business_start and block_end >= business_end
            ):
                return block

        return None

    @classmethod
    def get_available_slots(
        cls,
        service,
        selected_date,
        enforce_minimum_advance=False,
    ):
        periods = cls.get_business_periods(selected_date)

        if not periods:
            return []

        public_cutoff_datetime = None

        if enforce_minimum_advance:
            public_cutoff_datetime = cls.get_public_booking_cutoff_datetime(
                selected_date
            )

        appointments = cls.get_active_appointments_for_date(selected_date)
        blocks = cls.get_active_blocks_for_date(selected_date)
        duration = timedelta(minutes=service.duration_minutes)
        available_slots = []

        for period_start, period_end in periods:
            current_datetime = period_start

            if public_cutoff_datetime:
                if public_cutoff_datetime >= period_end:
                    continue

                current_datetime = max(current_datetime, public_cutoff_datetime)

            current_datetime = cls.round_datetime_up_to_slot(current_datetime)

            # O atendimento tem de terminar dentro do mesmo período.
            while current_datetime + duration <= period_end:
                slot_start = current_datetime
                slot_end = slot_start + duration

                has_conflict = cls._has_conflict(
                    slot_start, slot_end, appointments, blocks, selected_date
                )

                if not has_conflict:
                    available_slots.append(
                        AvailableSlot(
                            value=slot_start.strftime("%H:%M"),
                            label=slot_start.strftime("%H:%M"),
                        ).as_dict()
                    )

                current_datetime += timedelta(minutes=cls.slot_minutes)

        return available_slots

    @classmethod
    def build_public_slots(cls, service, selected_date):
        """Grelha pública completa do dia, a partir do corte de antecedência.

        Ao contrário de get_public_available_slots(), devolve também os horários
        já ocupados, marcados com is_available=False. Mostrar a agenda cheia dá
        à cliente a noção do que resta, em vez de a deixar a adivinhar por que
        motivo o dia parece vazio.

        Horários passados continuam de fora: propor um horário que já não pode
        ser marcado seria pior do que não o mostrar.
        """

        periods = cls.get_business_periods(selected_date)

        if not periods or not service:
            return []

        cutoff = cls.get_public_booking_cutoff_datetime(selected_date)
        appointments = cls.get_active_appointments_for_date(selected_date)
        blocks = cls.get_active_blocks_for_date(selected_date)
        duration = timedelta(minutes=service.duration_minutes)

        slots = []

        for period_start, period_end in periods:
            current = period_start

            if cutoff:
                if cutoff >= period_end:
                    continue

                current = max(current, cutoff)

            current = cls.round_datetime_up_to_slot(current)

            while current + duration <= period_end:
                ocupado = cls._has_conflict(
                    current,
                    current + duration,
                    appointments,
                    blocks,
                    selected_date,
                )

                slots.append(
                    {
                        "value": current.strftime("%H:%M"),
                        "label": current.strftime("%H:%M"),
                        "is_available": not ocupado,
                    }
                )

                current += timedelta(minutes=cls.slot_minutes)

        return slots

    @classmethod
    def get_public_available_slots(cls, service, selected_date):
        # Public booking must never expose a slot in the past. It must also
        # respect the configured minimum lead time for same-day bookings.
        slots = cls.get_available_slots(
            service=service,
            selected_date=selected_date,
            enforce_minimum_advance=True,
        )

        return cls.filter_public_slots_by_cutoff(
            slots=slots,
            selected_date=selected_date,
        )

    @classmethod
    def filter_public_slots_by_cutoff(cls, slots, selected_date):
        # Last line of defence before returning public slots. Even if another
        # caller builds slots incorrectly, the public response cannot include
        # any slot before the current public booking cutoff.
        public_cutoff_datetime = cls.get_public_booking_cutoff_datetime(selected_date)

        if not public_cutoff_datetime:
            return slots

        filtered_slots = []

        for slot in slots:
            try:
                slot_time = datetime.strptime(slot["value"], "%H:%M").time()
            except (KeyError, TypeError, ValueError):
                continue

            slot_datetime = datetime.combine(selected_date, slot_time)

            if slot_datetime >= public_cutoff_datetime:
                filtered_slots.append(slot)

        return filtered_slots

    @classmethod
    def get_public_booking_cutoff_datetime(cls, selected_date):
        # Public bookings cannot show past slots. For today, the effective cutoff
        # is the latest value between now and now + PUBLIC_BOOKING_MIN_ADVANCE_HOURS.
        # Example: if now is 09:00 and the minimum advance is 3 hours, the cutoff
        # is 12:00. If 12:00 is blocked by lunch, normal conflict validation will
        # skip it and expose the next valid slot.
        now = cls.get_public_booking_now().replace(second=0, microsecond=0)

        if selected_date < now.date():
            return datetime.combine(selected_date, datetime.max.time())

        if selected_date > now.date():
            return None

        minimum_advance_hours = getattr(
            settings,
            "PUBLIC_BOOKING_MIN_ADVANCE_HOURS",
            3,
        )

        minimum_start = now + timedelta(hours=minimum_advance_hours)

        return max(now, minimum_start).replace(
            second=0,
            microsecond=0,
        )

    @classmethod
    def get_minimum_public_booking_start_datetime(cls, selected_date):
        # Backward-compatible alias for older callers.
        return cls.get_public_booking_cutoff_datetime(selected_date)

    @classmethod
    def public_slot_is_bookable(cls, selected_date, start_time_value):
        # Used by public form submission to block manual URL tampering such as
        # /marcar/?date=today&start_time=09:00 after 09:00 has already passed.
        public_cutoff_datetime = cls.get_public_booking_cutoff_datetime(selected_date)

        if not public_cutoff_datetime:
            return True

        if hasattr(start_time_value, "strftime"):
            slot_time = start_time_value
        else:
            try:
                slot_time = datetime.strptime(str(start_time_value), "%H:%M").time()
            except ValueError:
                return False

        slot_datetime = datetime.combine(selected_date, slot_time)

        return slot_datetime >= public_cutoff_datetime

    @classmethod
    def get_public_booking_now(cls):
        # Use the public booking timezone explicitly. This avoids exposing stale
        # same-day slots when the server timezone differs from the business
        # timezone used by the agenda.
        timezone_name = getattr(
            settings,
            "PUBLIC_BOOKING_TIME_ZONE",
            getattr(settings, "TIME_ZONE", "Europe/Lisbon"),
        )

        try:
            booking_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            booking_timezone = timezone.get_current_timezone()

        return timezone.now().astimezone(booking_timezone).replace(tzinfo=None)

    @classmethod
    def round_datetime_up_to_slot(cls, value):
        minute = value.minute
        remainder = minute % cls.slot_minutes

        if remainder:
            value += timedelta(minutes=cls.slot_minutes - remainder)

        return value.replace(second=0, microsecond=0)

    @classmethod
    def _has_conflict(cls, slot_start, slot_end, appointments, blocks, selected_date):
        for appointment in appointments:
            if cls.overlaps(
                slot_start,
                slot_end,
                appointment.get_start_datetime(),
                appointment.get_end_datetime(),
            ):
                return True

        for block in blocks:
            block_start = block.get_start_datetime_for_date(selected_date)
            block_end = block.get_end_datetime_for_date(selected_date)

            if cls.overlaps(slot_start, slot_end, block_start, block_end):
                return True

        return False

    @classmethod
    def _floor_to_slot(cls, value, slot_minutes):
        return value.replace(
            minute=value.minute - value.minute % slot_minutes,
            second=0,
            microsecond=0,
        )

    @classmethod
    def _ceil_to_slot(cls, value, slot_minutes):
        alinhado = cls._floor_to_slot(value, slot_minutes)

        if alinhado == value:
            return alinhado

        return alinhado + timedelta(minutes=slot_minutes)

    @classmethod
    def _periods_covering_appointments(cls, periods, appointments, slot_minutes):
        """Estende os períodos do dia para conterem todas as marcações.

        Um encaixe fora do horário existiria sem aparecer em lado nenhum: a
        grelha da agenda percorre os períodos de trabalho, e o que fica fora
        deles não é desenhado. Criar uma marcação invisível é pior do que não
        deixar criá-la.
        """

        intervalos = list(periods)

        for appointment in appointments:
            inicio = appointment.get_start_datetime()
            fim = appointment.get_end_datetime()

            if any(inicio >= p_inicio and fim <= p_fim for p_inicio, p_fim in periods):
                continue

            intervalos.append(
                (
                    cls._floor_to_slot(inicio, slot_minutes),
                    cls._ceil_to_slot(fim, slot_minutes),
                )
            )

        if not intervalos:
            return []

        # Juntar o que se toca, para não desenhar a mesma hora duas vezes
        # quando um encaixe começa antes do horário e entra por ele dentro.
        intervalos.sort()
        unidos = [intervalos[0]]

        for inicio, fim in intervalos[1:]:
            ultimo_inicio, ultimo_fim = unidos[-1]

            if inicio <= ultimo_fim:
                unidos[-1] = (ultimo_inicio, max(ultimo_fim, fim))
            else:
                unidos.append((inicio, fim))

        return unidos

    @classmethod
    def build_visual_slots(
        cls, selected_date, slot_minutes=30, appointments_only=False
    ):
        """Grelha da agenda interna.

        Com `appointments_only`, desenha apenas as horas que têm marcações. É o
        que o dia inteiramente bloqueado precisa: continua a esconder a grelha
        toda, mas sem esconder um encaixe que foi posto lá de propósito.
        """

        business_hour = cls.get_business_hour(selected_date)
        appointments = cls.get_active_appointments_for_date(selected_date)

        periods = (
            []
            if appointments_only
            else cls.get_business_periods(selected_date, business_hour)
        )
        periods = cls._periods_covering_appointments(
            periods, appointments, slot_minutes
        )

        if not periods:
            return business_hour, []

        blocks = cls.get_active_blocks_for_date(selected_date)
        slots = []

        for period_start, end_datetime in periods:
            slots.extend(
                cls._build_period_slots(
                    selected_date=selected_date,
                    period_start=period_start,
                    end_datetime=end_datetime,
                    appointments=appointments,
                    blocks=blocks,
                    slot_minutes=slot_minutes,
                )
            )

        return business_hour, slots

    @classmethod
    def _build_period_slots(
        cls,
        selected_date,
        period_start,
        end_datetime,
        appointments,
        blocks,
        slot_minutes,
    ):
        current_datetime = period_start
        slots = []

        while current_datetime < end_datetime:
            slot_start = current_datetime
            slot_data = {
                "time": slot_start.time(),
                "time_value": slot_start.strftime("%H:%M"),
                "appointment": None,
                "block": None,
                "is_appointment_start": False,
                "is_inside_appointment": False,
                "is_block_start": False,
                "is_inside_block": False,
                "block_slots": 1,
                "block_height": 70,
            }

            # A marcação vem primeiro. Antes as duas coisas nunca podiam
            # coexistir, mas um encaixe é precisamente uma marcação por cima de
            # um bloqueio: mostrar o bloqueio esconderia o atendimento.
            cls._mark_appointment_slot(
                slot_data, appointments, slot_start, slot_minutes
            )

            if not slot_data["appointment"]:
                cls._mark_block_slot(
                    slot_data,
                    blocks,
                    selected_date,
                    slot_start,
                    current_datetime,
                    end_datetime,
                    slot_minutes,
                )

            slots.append(slot_data)
            current_datetime += timedelta(minutes=slot_minutes)

        return slots

    @classmethod
    def _duration_to_slot_count(cls, duration_minutes, slot_minutes):
        block_slots = max(1, duration_minutes // slot_minutes)
        if duration_minutes % slot_minutes:
            block_slots += 1
        return block_slots

    @classmethod
    def _mark_block_slot(
        cls,
        slot_data,
        blocks,
        selected_date,
        slot_start,
        current_datetime,
        end_datetime,
        slot_minutes,
    ):
        for block in blocks:
            block_start = block.get_start_datetime_for_date(selected_date)
            block_end = block.get_end_datetime_for_date(selected_date)

            if slot_start == block_start or (
                block.is_full_day and slot_start == current_datetime
            ):
                duration_minutes = int((block_end - block_start).total_seconds() / 60)

                if block.is_full_day:
                    duration_minutes = int(
                        (end_datetime - current_datetime).total_seconds() / 60
                    )

                block_slots = cls._duration_to_slot_count(
                    duration_minutes, slot_minutes
                )
                slot_data.update(
                    {
                        "block": block,
                        "is_block_start": True,
                        "is_inside_block": True,
                        "block_slots": block_slots,
                        "block_height": block_slots * 70,
                    }
                )
                return

            if slot_start > block_start and slot_start < block_end:
                slot_data["block"] = block
                slot_data["is_inside_block"] = True
                return

    @classmethod
    def _mark_appointment_slot(cls, slot_data, appointments, slot_start, slot_minutes):
        for appointment in appointments:
            appointment_start = appointment.get_start_datetime()
            appointment_end = appointment.get_end_datetime()

            if slot_start == appointment_start:
                block_slots = cls._duration_to_slot_count(
                    appointment.service.duration_minutes,
                    slot_minutes,
                )
                slot_data.update(
                    {
                        "appointment": appointment,
                        "is_appointment_start": True,
                        "is_inside_appointment": True,
                        "block_slots": block_slots,
                        "block_height": block_slots * 70,
                    }
                )
                return

            if slot_start > appointment_start and slot_start < appointment_end:
                slot_data["appointment"] = appointment
                slot_data["is_inside_appointment"] = True
                return
