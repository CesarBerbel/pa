from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.availability import AvailabilityService
from appointments.forms import AppointmentForm
from appointments.models import Appointment, Customer, ScheduleBlock
from appointments.tests.factories import create_test_service, ensure_test_business_hour


class InternalScheduleOverrideBase(TestCase):
    """Encaixes: marcações postas fora do horário, a partir da área interna.

    A profissional tem a agenda à frente e decide encaixar alguém. O que o
    sistema não pode deixar passar é duas pessoas ao mesmo tempo.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.client.force_login(self.user)

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@example.com",
            phone="+351910000000",
        )

        self.service = create_test_service(duration_minutes=60)

        self.date = timezone.localdate() + timedelta(days=14)
        while self.date.weekday() != 0:
            self.date += timedelta(days=1)

        ensure_test_business_hour(
            weekday=self.date.weekday(),
            start_time=time(9, 0),
            end_time=time(17, 0),
        )

    def dados(self, start_time, **extra):
        dados = {
            "customer_mode": AppointmentForm.CUSTOMER_MODE_EXISTING,
            "customer": self.customer.pk,
            "service": self.service.pk,
            "date": self.date.strftime("%Y-%m-%d"),
            "start_time": start_time,
            "status": Appointment.STATUS_SCHEDULED,
            "notes": "",
        }
        dados.update(extra)
        return dados

    def marcar(self, start_time, follow=False, **extra):
        return self.client.post(
            reverse("appointments:appointment_create"),
            data=self.dados(start_time, **extra),
            follow=follow,
        )

    def existente(self, start_time, service=None, outside_schedule=False):
        return Appointment.objects.create(
            customer=self.customer,
            service=service or self.service,
            date=self.date,
            start_time=start_time,
            status=Appointment.STATUS_SCHEDULED,
            created_by=self.user,
            outside_schedule=outside_schedule,
        )


class BookingOutsideBusinessHoursTests(InternalScheduleOverrideBase):
    def test_after_closing_time_is_accepted(self):
        resposta = self.marcar("19:00")

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Appointment.objects.filter(start_time=time(19, 0)).exists())

    def test_it_is_recorded_as_an_encaixe(self):
        self.marcar("19:00")

        self.assertTrue(Appointment.objects.get().outside_schedule)

    def test_a_normal_time_is_not_recorded_as_an_encaixe(self):
        self.marcar("10:00")

        self.assertFalse(Appointment.objects.get().outside_schedule)

    def test_the_professional_is_told(self):
        # Aceitar em silêncio esconderia um engano de digitação: 19:00 em vez
        # de 09:00 passaria sem uma palavra.
        resposta = self.marcar("19:00", follow=True)
        avisos = [str(m) for m in resposta.context["messages"]]

        self.assertTrue(
            any("Encaixe" in aviso for aviso in avisos),
            f"nenhum aviso de encaixe em {avisos}",
        )

    def test_a_day_without_business_hours_still_accepts_bookings(self):
        domingo = self.date
        while domingo.weekday() != 6:
            domingo += timedelta(days=1)

        ensure_test_business_hour(weekday=6, is_active=False)

        resposta = self.client.post(
            reverse("appointments:appointment_create"),
            data=self.dados("10:00", date=domingo.strftime("%Y-%m-%d")),
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Appointment.objects.get().outside_schedule)

    def test_during_the_lunch_break_is_accepted(self):
        ensure_test_business_hour(
            weekday=self.date.weekday(),
            start_time=time(8, 0),
            end_time=time(12, 0),
        )
        hora = AvailabilityService.get_business_hour(self.date)
        hora.second_start_time = time(14, 0)
        hora.second_end_time = time(18, 0)
        hora.save()

        resposta = self.marcar("12:30")

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Appointment.objects.get().outside_schedule)


class BookingOverABlockTests(InternalScheduleOverrideBase):
    def setUp(self):
        super().setUp()

        self.block = ScheduleBlock.objects.create(
            title="Formação",
            date=self.date,
            start_time=time(10, 0),
            end_time=time(12, 0),
            is_active=True,
        )

    def test_a_blocked_hour_is_accepted(self):
        resposta = self.marcar("10:00")

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Appointment.objects.get().outside_schedule)

    def test_a_full_day_block_is_accepted(self):
        self.block.start_time = None
        self.block.end_time = None
        self.block.is_full_day = True
        self.block.save()

        resposta = self.marcar("10:00")

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Appointment.objects.get().outside_schedule)


class AppointmentConflictIsNeverWaivedTests(InternalScheduleOverrideBase):
    """A sobreposição não é uma questão de política: é impossível de cumprir."""

    def test_the_same_hour_is_refused(self):
        self.existente(time(10, 0))

        resposta = self.marcar("10:00")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_a_later_start_inside_the_previous_service_is_refused(self):
        # Uma consulta de 60 minutos às 10:00 ocupa até às 11:00.
        self.existente(time(10, 0))

        resposta = self.marcar("10:30")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_an_earlier_start_that_runs_into_the_next_is_refused(self):
        self.existente(time(10, 0))

        resposta = self.marcar("09:30")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_touching_without_overlapping_is_accepted(self):
        self.existente(time(10, 0))

        resposta = self.marcar("11:00")

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Appointment.objects.count(), 2)

    def test_conflict_is_refused_outside_business_hours_too(self):
        # O encaixe dispensa o horário, não a outra pessoa que lá está.
        self.existente(time(19, 0), outside_schedule=True)

        resposta = self.marcar("19:30")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_a_cancelled_appointment_frees_the_hour(self):
        marcacao = self.existente(time(10, 0))
        marcacao.status = Appointment.STATUS_CANCELLED
        marcacao.save()

        resposta = self.marcar("10:00")

        self.assertEqual(resposta.status_code, 302)

    def test_the_error_says_what_happened(self):
        self.existente(time(10, 0))

        resposta = self.marcar("10:30")

        self.assertContains(resposta, "conflito com outra marcação")


class EncaixeStaysUsableTests(InternalScheduleOverrideBase):
    """Um encaixe tem de continuar a poder ser confirmado, concluído e editado.

    É por isto que a marca fica gravada em vez de decidida no momento: cada um
    destes passos volta a passar pela validação do modelo.
    """

    def setUp(self):
        super().setUp()

        self.marcar("19:00")
        self.encaixe = Appointment.objects.get()

    def test_it_can_be_confirmed(self):
        resposta = self.client.post(
            reverse("appointments:appointment_confirm", args=[self.encaixe.pk])
        )

        self.encaixe.refresh_from_db()

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self.encaixe.status, Appointment.STATUS_CONFIRMED)

    def test_it_can_be_completed(self):
        self.encaixe.status = Appointment.STATUS_CONFIRMED
        self.encaixe.save()

        self.client.post(
            reverse("appointments:appointment_complete", args=[self.encaixe.pk])
        )

        self.encaixe.refresh_from_db()

        self.assertEqual(self.encaixe.status, Appointment.STATUS_COMPLETED)

    def test_it_can_be_saved_again_without_the_form(self):
        self.encaixe.notes = "Cliente pediu para ser atendida depois do trabalho."
        self.encaixe.save()

        self.assertTrue(Appointment.objects.get().outside_schedule)

    def test_moving_it_back_into_working_hours_clears_the_mark(self):
        self.client.post(
            reverse("appointments:appointment_update", args=[self.encaixe.pk]),
            data=self.dados("10:00"),
        )

        self.encaixe.refresh_from_db()

        self.assertEqual(self.encaixe.start_time, time(10, 0))
        self.assertFalse(self.encaixe.outside_schedule)


class EncaixeIsVisibleTests(InternalScheduleOverrideBase):
    """Uma marcação que existe sem aparecer é pior do que não a deixar criar."""

    def agenda(self):
        return self.client.get(
            reverse("appointments:visual_schedule"),
            {"date": self.date.strftime("%Y-%m-%d")},
        )

    def horas_na_grelha(self, resposta):
        return [slot["time_value"] for slot in resposta.context["slots"]]

    def test_an_appointment_after_closing_time_appears(self):
        self.marcar("19:00")

        resposta = self.agenda()

        self.assertIn("19:00", self.horas_na_grelha(resposta))
        self.assertContains(resposta, "Encaixe")

    def test_the_grid_still_covers_the_normal_day(self):
        self.marcar("19:00")

        horas = self.horas_na_grelha(self.agenda())

        self.assertIn("09:00", horas)
        self.assertIn("16:30", horas)

    def test_the_full_duration_is_shown_as_occupied(self):
        self.marcar("19:00")

        horas = self.horas_na_grelha(self.agenda())

        self.assertIn("19:00", horas)
        self.assertIn("19:30", horas)

    def test_an_appointment_before_opening_appears(self):
        self.marcar("07:00")

        self.assertIn("07:00", self.horas_na_grelha(self.agenda()))

    def test_it_appears_on_a_fully_blocked_day(self):
        ScheduleBlock.objects.create(
            title="Férias",
            date=self.date,
            is_full_day=True,
            is_active=True,
        )

        self.marcar("10:00")

        resposta = self.agenda()

        self.assertIn("10:00", self.horas_na_grelha(resposta))
        self.assertContains(resposta, "Férias")

    def test_a_fully_blocked_day_without_bookings_shows_no_grid(self):
        # O comportamento antigo mantém-se: a grelha continua escondida.
        ScheduleBlock.objects.create(
            title="Férias",
            date=self.date,
            is_full_day=True,
            is_active=True,
        )

        self.assertEqual(self.horas_na_grelha(self.agenda()), [])

    def test_a_booking_over_a_block_shows_the_booking(self):
        ScheduleBlock.objects.create(
            title="Formação",
            date=self.date,
            start_time=time(10, 0),
            end_time=time(12, 0),
            is_active=True,
        )

        self.marcar("10:00")

        slots = {s["time_value"]: s for s in self.agenda().context["slots"]}

        self.assertIsNotNone(slots["10:00"]["appointment"])
        self.assertIsNone(slots["10:00"]["block"])


class PublicBookingIsUnaffectedTests(InternalScheduleOverrideBase):
    """Nada disto pode chegar ao site público."""

    def test_the_public_cannot_book_outside_business_hours(self):
        marcacao = Appointment(
            customer=self.customer,
            service=self.service,
            date=self.date,
            start_time=time(19, 0),
            status=Appointment.STATUS_SCHEDULED,
            created_by=self.user,
        )

        with self.assertRaises(ValidationError):
            marcacao.full_clean()

    def test_the_public_cannot_book_over_a_block(self):
        ScheduleBlock.objects.create(
            title="Formação",
            date=self.date,
            start_time=time(10, 0),
            end_time=time(12, 0),
            is_active=True,
        )

        marcacao = Appointment(
            customer=self.customer,
            service=self.service,
            date=self.date,
            start_time=time(10, 0),
            status=Appointment.STATUS_SCHEDULED,
            created_by=self.user,
        )

        with self.assertRaises(ValidationError):
            marcacao.full_clean()

    def test_an_encaixe_does_not_create_a_public_slot(self):
        self.marcar("19:00")

        horarios = [
            slot["value"]
            for slot in AvailabilityService.build_public_slots(self.service, self.date)
        ]

        self.assertNotIn("19:00", horarios)

    def test_an_encaixe_inside_working_hours_takes_the_public_slot(self):
        ScheduleBlock.objects.create(
            title="Formação",
            date=self.date,
            start_time=time(10, 0),
            end_time=time(12, 0),
            is_active=True,
        )

        self.marcar("10:00")

        disponiveis = [
            slot["value"]
            for slot in AvailabilityService.build_public_slots(self.service, self.date)
            if slot["is_available"]
        ]

        self.assertNotIn("10:00", disponiveis)
