from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from appointments.availability import AvailabilityService
from appointments.models import Appointment, BusinessHour, Customer
from appointments.tests.factories import create_test_service


class SplitWorkingDayTests(TestCase):
    """O dia de trabalho pode ter dois períodos, com a pausa implícita.

    Antes, o almoço era um bloqueio recorrente que tinha de ser mantido em
    sintonia com o horário. Agora é a ausência de um período.
    """

    def setUp(self):
        self.admin_user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@example.com",
            phone="+351910000000",
        )

        self.service = create_test_service(duration_minutes=60)

        self.selected_date = timezone.localdate() + timedelta(days=14)
        while self.selected_date.weekday() != 0:
            self.selected_date += timedelta(days=1)

        self.business_hour, _ = BusinessHour.objects.update_or_create(
            weekday=self.selected_date.weekday(),
            defaults={
                "start_time": time(8, 0),
                "end_time": time(12, 0),
                "second_start_time": time(14, 0),
                "second_end_time": time(18, 0),
                "is_active": True,
            },
        )

    def slot_values(self):
        return [
            slot["value"]
            for slot in AvailabilityService.get_available_slots(
                self.service, self.selected_date
            )
        ]

    def test_periods_are_reported_in_order(self):
        self.assertEqual(
            self.business_hour.periods,
            [(time(8, 0), time(12, 0)), (time(14, 0), time(18, 0))],
        )
        self.assertTrue(self.business_hour.has_second_period)

    def test_duration_excludes_the_break(self):
        # 4h de manhã + 4h de tarde, sem contar as duas horas de pausa.
        self.assertEqual(self.business_hour.duration_minutes, 480)
        self.assertEqual(self.business_hour.duration_display, "8h")

    def test_no_slots_during_the_break(self):
        valores = self.slot_values()

        self.assertIn("08:00", valores)
        self.assertIn("14:00", valores)

        for hora in ["12:00", "12:30", "13:00", "13:30"]:
            self.assertNotIn(hora, valores)

    def test_no_slot_starts_if_it_would_cross_the_break(self):
        # Um serviço de 60 min às 11:30 terminaria às 12:30, já na pausa.
        self.assertNotIn("11:30", self.slot_values())
        self.assertIn("11:00", self.slot_values())

    def test_last_slot_of_each_period_fits_inside_it(self):
        valores = self.slot_values()

        self.assertEqual(valores[0], "08:00")
        self.assertIn("11:00", valores)
        self.assertIn("17:00", valores)
        self.assertNotIn("17:30", valores)

    def test_appointment_crossing_the_break_is_rejected(self):
        appointment = Appointment(
            customer=self.customer,
            service=self.service,
            created_by=self.admin_user,
            date=self.selected_date,
            start_time=time(11, 30),
            status=Appointment.STATUS_SCHEDULED,
        )

        with self.assertRaises(ValidationError):
            appointment.full_clean()

    def test_appointment_inside_the_break_is_rejected(self):
        appointment = Appointment(
            customer=self.customer,
            service=self.service,
            created_by=self.admin_user,
            date=self.selected_date,
            start_time=time(13, 0),
            status=Appointment.STATUS_SCHEDULED,
        )

        with self.assertRaises(ValidationError):
            appointment.full_clean()

    def test_appointment_inside_a_period_is_accepted(self):
        Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            created_by=self.admin_user,
            date=self.selected_date,
            start_time=time(14, 0),
            status=Appointment.STATUS_SCHEDULED,
        )

        self.assertEqual(Appointment.objects.count(), 1)

    def test_single_period_day_still_works(self):
        # Um dia sem tarde continua a comportar-se como antes.
        self.business_hour.second_start_time = None
        self.business_hour.second_end_time = None
        self.business_hour.save()

        valores = self.slot_values()

        self.assertEqual(valores[-1], "11:00")
        self.assertNotIn("14:00", valores)

    def test_public_grid_skips_the_break(self):
        grelha = [
            slot["value"]
            for slot in AvailabilityService.build_public_slots(
                self.service, self.selected_date
            )
        ]

        self.assertIn("11:00", grelha)
        self.assertNotIn("12:00", grelha)
        self.assertIn("14:00", grelha)

    def test_internal_agenda_skips_the_break(self):
        _hora, slots = AvailabilityService.build_visual_slots(self.selected_date)
        valores = [slot["time_value"] for slot in slots]

        self.assertIn("11:30", valores)
        self.assertNotIn("12:30", valores)
        self.assertIn("14:00", valores)


class BusinessHourValidationTests(TestCase):
    # validate_unique=False: as migrations já semeiam todos os dias da semana,
    # e o que está a ser testado é a validação dos períodos, não a unicidade.
    def build(self, **overrides):
        dados = {
            "weekday": 0,
            "start_time": time(8, 0),
            "end_time": time(12, 0),
            "second_start_time": time(14, 0),
            "second_end_time": time(18, 0),
        }
        dados.update(overrides)
        return BusinessHour(**dados)

    def test_valid_two_period_day(self):
        self.build().full_clean(validate_unique=False)

    def test_afternoon_needs_both_fields(self):
        with self.assertRaises(ValidationError):
            self.build(second_end_time=None).full_clean(validate_unique=False)

    def test_afternoon_must_end_after_it_starts(self):
        with self.assertRaises(ValidationError):
            self.build(
                second_start_time=time(18, 0), second_end_time=time(14, 0)
            ).full_clean(validate_unique=False)

    def test_afternoon_cannot_start_before_the_morning_ends(self):
        with self.assertRaises(ValidationError):
            self.build(second_start_time=time(11, 0)).full_clean(validate_unique=False)

    def test_single_period_day_is_valid(self):
        self.build(second_start_time=None, second_end_time=None).full_clean(
            validate_unique=False
        )
