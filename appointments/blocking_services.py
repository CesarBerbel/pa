from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.db import transaction

from appointments.availability import AvailabilityService
from appointments.models import ScheduleBlock


@dataclass
class SlotBlockingResult:
    # Resultado de um bloqueio feito a partir da seleção visual da agenda.
    success: bool
    message: str
    created_blocks: int = 0
    skipped_slots: int = 0


class ScheduleBlockingService:
    """Cria bloqueios a partir de horários escolhidos na agenda visual.

    Slots contíguos são fundidos num único ScheduleBlock: escolher 14:00, 14:30
    e 15:00 produz um bloqueio das 14:00 às 15:30, e não três registos soltos.
    """

    slot_minutes = 30

    DEFAULT_TITLE = "Agenda fechada"

    @classmethod
    def parse_slot_times(cls, raw_values):
        # Converte "HH:MM" para time, ignorando valores inválidos vindos do POST.
        parsed = set()

        for raw_value in raw_values:
            try:
                parsed.add(datetime.strptime(raw_value.strip(), "%H:%M").time())
            except (AttributeError, ValueError):
                continue

        return sorted(parsed)

    @classmethod
    def get_free_slot_times(cls, selected_date):
        # Só é possível bloquear o que está efetivamente livre. Impede que um
        # POST manipulado tape uma marcação já existente.
        _business_hour, slots = AvailabilityService.build_visual_slots(
            selected_date=selected_date,
            slot_minutes=cls.slot_minutes,
        )

        return {
            slot["time"]
            for slot in slots
            if not slot["appointment"] and not slot["block"]
        }

    @classmethod
    def merge_contiguous(cls, selected_date, times):
        # Devolve [(início, fim)] juntando slots encostados uns aos outros.
        ranges = []
        step = timedelta(minutes=cls.slot_minutes)

        for slot_time in sorted(times):
            start = datetime.combine(selected_date, slot_time)
            end = start + step

            if ranges and ranges[-1][1] == start:
                ranges[-1] = (ranges[-1][0], end)
            else:
                ranges.append((start, end))

        merged = []

        for start, end in ranges:
            # Um bloco que passe da meia-noite teria end_time <= start_time e
            # seria rejeitado pela validação do modelo.
            end_time = time.max if end.date() != start.date() else end.time()
            merged.append((start.time(), end_time))

        return merged

    @classmethod
    def block_slots(cls, selected_date, times, title=""):
        title = (title or "").strip() or cls.DEFAULT_TITLE

        if not times:
            return SlotBlockingResult(
                success=False,
                message="Selecione pelo menos um horário para bloquear.",
            )

        free_times = cls.get_free_slot_times(selected_date)
        valid_times = [slot_time for slot_time in times if slot_time in free_times]
        skipped = len(times) - len(valid_times)

        if not valid_times:
            return SlotBlockingResult(
                success=False,
                message=(
                    "Nenhum dos horários selecionados está livre. "
                    "Atualize a agenda e tente novamente."
                ),
                skipped_slots=skipped,
            )

        ranges = cls.merge_contiguous(selected_date, valid_times)

        with transaction.atomic():
            for start_time, end_time in ranges:
                ScheduleBlock.objects.create(
                    title=title,
                    block_type=ScheduleBlock.BLOCK_TYPE_OTHER,
                    date=selected_date,
                    start_time=start_time,
                    end_time=end_time,
                    is_full_day=False,
                    is_recurring=False,
                    is_active=True,
                )

        if len(ranges) == 1:
            message = "1 bloqueio criado."
        else:
            message = f"{len(ranges)} bloqueios criados."

        if skipped:
            message = (
                f"{message} {skipped} horário(s) foram ignorados por já não "
                "estarem livres."
            )

        return SlotBlockingResult(
            success=True,
            message=message,
            created_blocks=len(ranges),
            skipped_slots=skipped,
        )
