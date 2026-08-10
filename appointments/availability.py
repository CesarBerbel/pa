from __future__ import annotations

from dataclasses import dataclass
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


class AvailabilityService:
    """Centralizes schedule availability and conflict rules.

    This module is the single place for business-hour validation, schedule blocks,
    appointment overlap detection and public slot generation.
    """

    slot_minutes = 30

    @classmethod
    def get_business_hour(cls, selected_date):
        return BusinessHour.objects.filter(
            weekday=selected_date.weekday(),
            is_active=True,
        ).first()

    @classmethod
    def get_active_blocks_for_date(cls, selected_date):
        return [
            block
            for block in ScheduleBlock.objects.filter(is_active=True).order_by(
                "start_time"
            )
            if block.applies_to_date(selected_date)
        ]

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
            appointments = appointments.exclude(pk=exclude_pk)

        return appointments

    @staticmethod
    def overlaps(first_start, first_end, second_start, second_end):
        return first_start < second_end and first_end > second_start

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

        business_hour = cls.get_business_hour(appointment.date)

        if not business_hour:
            raise ValidationError(
                "Não há horário de funcionamento ativo para este dia."
            )

        appointment_start = appointment.get_start_datetime()
        appointment_end = appointment.get_end_datetime()

        business_start = datetime.combine(appointment.date, business_hour.start_time)
        business_end = datetime.combine(appointment.date, business_hour.end_time)

        if appointment_start < business_start or appointment_end > business_end:
            raise ValidationError("A marcação está fora do horário de funcionamento.")

        for block in cls.get_active_blocks_for_date(appointment.date):
            block_start = block.get_start_datetime_for_date(appointment.date)
            block_end = block.get_end_datetime_for_date(appointment.date)

            if cls.overlaps(appointment_start, appointment_end, block_start, block_end):
                raise ValidationError(f"Este horário está bloqueado: {block.title}.")

        for existing in cls.get_active_appointments_for_date(
            appointment.date,
            exclude_pk=appointment.pk,
        ):
            existing_start = existing.get_start_datetime()
            existing_end = existing.get_end_datetime()

            if cls.overlaps(
                appointment_start, appointment_end, existing_start, existing_end
            ):
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

        business_start = datetime.combine(selected_date, business_hour.start_time)
        business_end = datetime.combine(selected_date, business_hour.end_time)

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
        business_hour = business_hour or cls.get_business_hour(selected_date)

        if not business_hour:
            return None

        business_start = datetime.combine(selected_date, business_hour.start_time)
        business_end = datetime.combine(selected_date, business_hour.end_time)

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
        business_hour = cls.get_business_hour(selected_date)

        if not business_hour:
            return []

        current_datetime = datetime.combine(selected_date, business_hour.start_time)
        business_end_datetime = datetime.combine(selected_date, business_hour.end_time)
        public_cutoff_datetime = None

        if enforce_minimum_advance:
            public_cutoff_datetime = cls.get_public_booking_cutoff_datetime(
                selected_date
            )

            if public_cutoff_datetime:
                if public_cutoff_datetime > business_end_datetime:
                    return []

                current_datetime = max(
                    current_datetime,
                    public_cutoff_datetime,
                )

        current_datetime = cls.round_datetime_up_to_slot(current_datetime)

        appointments = cls.get_active_appointments_for_date(selected_date)
        blocks = cls.get_active_blocks_for_date(selected_date)
        available_slots = []

        while (
            current_datetime + timedelta(minutes=service.duration_minutes)
            <= business_end_datetime
        ):
            slot_start = current_datetime
            slot_end = slot_start + timedelta(minutes=service.duration_minutes)

            has_conflict = cls._has_conflict(
                slot_start, slot_end, appointments, blocks, selected_date
            )

            violates_public_cutoff = (
                enforce_minimum_advance
                and public_cutoff_datetime
                and slot_start < public_cutoff_datetime
            )

            if not has_conflict and not violates_public_cutoff:
                available_slots.append(
                    AvailableSlot(
                        value=slot_start.strftime("%H:%M"),
                        label=slot_start.strftime("%H:%M"),
                    ).as_dict()
                )

            current_datetime += timedelta(minutes=cls.slot_minutes)

        return available_slots

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
    def build_visual_slots(cls, selected_date, slot_minutes=30):
        business_hour = cls.get_business_hour(selected_date)

        if not business_hour:
            return business_hour, []

        current_datetime = datetime.combine(selected_date, business_hour.start_time)
        end_datetime = datetime.combine(selected_date, business_hour.end_time)
        appointments = cls.get_active_appointments_for_date(selected_date)
        blocks = cls.get_active_blocks_for_date(selected_date)
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

            cls._mark_block_slot(
                slot_data,
                blocks,
                selected_date,
                slot_start,
                current_datetime,
                end_datetime,
                slot_minutes,
            )

            if not slot_data["block"]:
                cls._mark_appointment_slot(
                    slot_data, appointments, slot_start, slot_minutes
                )

            slots.append(slot_data)
            current_datetime += timedelta(minutes=slot_minutes)

        return business_hour, slots

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
