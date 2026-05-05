from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

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
            for block in ScheduleBlock.objects.filter(is_active=True).order_by("start_time")
            if block.applies_to_date(selected_date)
        ]

    @classmethod
    def get_active_appointments_for_date(cls, selected_date, exclude_pk=None):
        appointments = Appointment.objects.filter(
            date=selected_date,
        ).exclude(
            status=Appointment.STATUS_CANCELLED,
        ).select_related(
            "customer",
            "service",
        ).order_by(
            "start_time",
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

        if appointment.service and not appointment.service.is_active:
            raise ValidationError("Não é possível marcar horário para um serviço inativo.")

        if not appointment.date or not appointment.start_time or not appointment.service:
            return

        business_hour = cls.get_business_hour(appointment.date)

        if not business_hour:
            raise ValidationError("Não há horário de funcionamento ativo para este dia.")

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

            if cls.overlaps(appointment_start, appointment_end, existing_start, existing_end):
                raise ValidationError(
                    "Este horário entra em conflito com outra marcação existente."
                )

    @classmethod
    def get_available_slots(cls, service, selected_date):
        business_hour = cls.get_business_hour(selected_date)

        if not business_hour:
            return []

        now = timezone.localtime()
        current_datetime = datetime.combine(selected_date, business_hour.start_time)
        business_end_datetime = datetime.combine(selected_date, business_hour.end_time)

        if selected_date == now.date():
            current_datetime = max(
                current_datetime,
                now.replace(second=0, microsecond=0).replace(tzinfo=None),
            )

            minute = current_datetime.minute
            if minute % cls.slot_minutes != 0:
                current_datetime += timedelta(minutes=cls.slot_minutes - (minute % cls.slot_minutes))

        appointments = cls.get_active_appointments_for_date(selected_date)
        blocks = cls.get_active_blocks_for_date(selected_date)
        available_slots = []

        while current_datetime + timedelta(minutes=service.duration_minutes) <= business_end_datetime:
            slot_start = current_datetime
            slot_end = slot_start + timedelta(minutes=service.duration_minutes)

            has_conflict = cls._has_conflict(slot_start, slot_end, appointments, blocks, selected_date)

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
    def _has_conflict(cls, slot_start, slot_end, appointments, blocks, selected_date):
        for appointment in appointments:
            if cls.overlaps(slot_start, slot_end, appointment.get_start_datetime(), appointment.get_end_datetime()):
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

            cls._mark_block_slot(slot_data, blocks, selected_date, slot_start, current_datetime, end_datetime, slot_minutes)

            if not slot_data["block"]:
                cls._mark_appointment_slot(slot_data, appointments, slot_start, slot_minutes)

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
    def _mark_block_slot(cls, slot_data, blocks, selected_date, slot_start, current_datetime, end_datetime, slot_minutes):
        for block in blocks:
            block_start = block.get_start_datetime_for_date(selected_date)
            block_end = block.get_end_datetime_for_date(selected_date)

            if slot_start == block_start or (block.is_full_day and slot_start == current_datetime):
                duration_minutes = int((block_end - block_start).total_seconds() / 60)

                if block.is_full_day:
                    duration_minutes = int((end_datetime - current_datetime).total_seconds() / 60)

                block_slots = cls._duration_to_slot_count(duration_minutes, slot_minutes)
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
