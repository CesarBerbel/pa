from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.forms import AppointmentForm
from appointments.models import Appointment, Customer, ScheduleBlock
from appointments.tests.factories import create_test_service, ensure_test_business_hour


class BlockAndAppointmentBase(TestCase):
    """Bloqueios e marcações a disputar o mesmo horário.

    Duas regras que se completam: um bloqueio não pode tapar quem já está
    marcado, e uma marcação feita por dentro pode ser colocada em cima de um
    bloqueio — nesse caso fica registada como encaixe.
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

        # Uma segunda-feira futura, como no exemplo do pedido.
        self.segunda = timezone.localdate() + timedelta(days=14)
        while self.segunda.weekday() != 0:
            self.segunda += timedelta(days=1)

        ensure_test_business_hour(
            weekday=0,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

    def marcar(self, hora=time(10, 0), dia=None, outside_schedule=False):
        return Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=dia or self.segunda,
            start_time=hora,
            status=Appointment.STATUS_SCHEDULED,
            created_by=self.user,
            outside_schedule=outside_schedule,
        )

    def bloqueio(self, **extra):
        dados = {
            "block_type": ScheduleBlock.BLOCK_TYPE_VACATION,
            "date": self.segunda,
            "is_full_day": True,
            "is_active": True,
        }
        dados.update(extra)

        return ScheduleBlock(**dados)

    def criar_pelo_formulario(self, **extra):
        dados = {
            "block_type": ScheduleBlock.BLOCK_TYPE_VACATION,
            "date": self.segunda.strftime("%Y-%m-%d"),
            "start_time": "",
            "end_time": "",
            "is_full_day": "on",
            "is_recurring": "",
            "recurring_weekdays": "",
            "recurrence_end_date": "",
            "is_active": "on",
            "notes": "",
        }
        dados.update(extra)

        return self.client.post(
            reverse("appointments:schedule_block_create"), data=dados
        )


class BlockingADayWithAppointmentsTests(BlockAndAppointmentBase):
    def test_a_full_day_block_is_refused_when_someone_is_booked(self):
        # O caso do pedido: bloquear a segunda inteira com alguém marcado.
        self.marcar()

        with self.assertRaises(ValidationError):
            self.bloqueio().full_clean()

    def test_the_form_refuses_it_and_creates_nothing(self):
        self.marcar()

        resposta = self.criar_pelo_formulario()

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            ScheduleBlock.objects.filter(
                block_type=ScheduleBlock.BLOCK_TYPE_VACATION,
                date=self.segunda,
            ).count(),
            0,
        )

    def test_the_message_says_who_is_booked(self):
        # Sem o nome e a hora, quem bloqueia não sabe o que tem de desmarcar.
        self.marcar()

        resposta = self.criar_pelo_formulario()

        self.assertContains(resposta, "Maria Silva")
        self.assertContains(resposta, "10:00")

    def test_a_partial_block_that_overlaps_is_refused(self):
        self.marcar(hora=time(10, 0))

        with self.assertRaises(ValidationError):
            self.bloqueio(
                is_full_day=False, start_time=time(9, 30), end_time=time(11, 0)
            ).full_clean()

    def test_a_partial_block_that_does_not_overlap_is_allowed(self):
        self.marcar(hora=time(10, 0))

        bloco = self.bloqueio(
            is_full_day=False, start_time=time(14, 0), end_time=time(16, 0)
        )
        bloco.full_clean()
        bloco.save()

        self.assertTrue(ScheduleBlock.objects.filter(pk=bloco.pk).exists())

    def test_a_block_that_ends_when_the_appointment_starts_is_allowed(self):
        # Encostado não é sobreposto.
        self.marcar(hora=time(10, 0))

        self.bloqueio(
            is_full_day=False, start_time=time(9, 0), end_time=time(10, 0)
        ).full_clean()

    def test_an_empty_day_can_still_be_blocked(self):
        bloco = self.bloqueio()
        bloco.full_clean()
        bloco.save()

        self.assertTrue(bloco.is_full_day)

    def test_another_day_is_not_affected(self):
        self.marcar(dia=self.segunda + timedelta(days=7))

        self.bloqueio().full_clean()

    def test_a_cancelled_appointment_does_not_stop_the_block(self):
        # O horário está livre outra vez.
        marcacao = self.marcar()
        marcacao.status = Appointment.STATUS_CANCELLED
        marcacao.save()

        self.bloqueio().full_clean()

    def test_an_inactive_block_is_not_checked(self):
        # Um bloqueio desligado não tapa nada, portanto não há o que validar.
        self.marcar()

        self.bloqueio(is_active=False).full_clean()

    def test_a_completed_appointment_still_blocks_it(self):
        # Já aconteceu, mas continua a fazer parte do registo do dia.
        marcacao = self.marcar()
        marcacao.status = Appointment.STATUS_CONFIRMED
        marcacao.save()

        with self.assertRaises(ValidationError):
            self.bloqueio().full_clean()


class RecurringBlockTests(BlockAndAppointmentBase):
    def test_a_recurring_block_is_refused_over_a_future_appointment(self):
        # A recorrência apanha a segunda-feira seguinte, onde há alguém.
        self.marcar(dia=self.segunda + timedelta(days=7))

        with self.assertRaises(ValidationError):
            self.bloqueio(is_recurring=True, recurring_weekdays="0").full_clean()

    def test_it_ignores_weekdays_it_does_not_cover(self):
        terca = self.segunda + timedelta(days=1)
        ensure_test_business_hour(
            weekday=1, start_time=time(9, 0), end_time=time(18, 0)
        )

        self.marcar(dia=terca)

        self.bloqueio(is_recurring=True, recurring_weekdays="0").full_clean()

    def test_it_ignores_appointments_after_the_recurrence_ends(self):
        self.marcar(dia=self.segunda + timedelta(days=21))

        self.bloqueio(
            is_recurring=True,
            recurring_weekdays="0",
            recurrence_end_date=self.segunda + timedelta(days=7),
        ).full_clean()

    def test_it_ignores_appointments_before_it_starts(self):
        anterior = self.segunda - timedelta(days=7)

        self.marcar(dia=anterior)

        self.bloqueio(is_recurring=True, recurring_weekdays="0").full_clean()


class EncaixeOverABlockedDayTests(BlockAndAppointmentBase):
    """O outro lado da regra: por dentro, pode marcar em cima do bloqueio."""

    def setUp(self):
        super().setUp()

        self.bloco = ScheduleBlock.objects.create(
            block_type=ScheduleBlock.BLOCK_TYPE_VACATION,
            date=self.segunda,
            is_full_day=True,
            is_active=True,
        )

    def marcar_pelo_formulario(self, hora="10:00"):
        return self.client.post(
            reverse("appointments:appointment_create"),
            data={
                "customer_mode": AppointmentForm.CUSTOMER_MODE_EXISTING,
                "customer": self.customer.pk,
                "service": self.service.pk,
                "date": self.segunda.strftime("%Y-%m-%d"),
                "start_time": hora,
                "status": Appointment.STATUS_SCHEDULED,
                "notes": "",
            },
        )

    def test_the_appointment_is_accepted_on_a_blocked_day(self):
        resposta = self.marcar_pelo_formulario()

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_it_is_recorded_as_an_encaixe(self):
        self.marcar_pelo_formulario()

        self.assertTrue(Appointment.objects.get().outside_schedule)

    def test_the_professional_is_told_which_block_was_overridden(self):
        resposta = self.marcar_pelo_formulario()
        avisos = [str(m) for m in self.client.get(resposta.url).context["messages"]]

        self.assertTrue(any("Férias" in aviso for aviso in avisos), avisos)

    def test_the_public_cannot_do_the_same(self):
        marcacao = Appointment(
            customer=self.customer,
            service=self.service,
            date=self.segunda,
            start_time=time(10, 0),
            status=Appointment.STATUS_SCHEDULED,
            created_by=self.user,
        )

        with self.assertRaises(ValidationError):
            marcacao.full_clean()

    def test_the_encaixe_shows_up_in_the_internal_agenda(self):
        # Um encaixe invisível seria pior do que não o deixar criar.
        self.marcar_pelo_formulario()

        resposta = self.client.get(
            reverse("appointments:visual_schedule"),
            {"date": self.segunda.strftime("%Y-%m-%d")},
        )

        horas = [slot["time_value"] for slot in resposta.context["slots"]]

        self.assertIn("10:00", horas)
        self.assertContains(resposta, "Encaixe")

    def test_the_block_can_still_be_edited_afterwards(self):
        """O encaixe não pode trancar o bloqueio que o acolheu.

        Se contasse como conflito, mudar as notas do bloqueio passaria a ser
        impossível a partir do momento em que alguém fosse encaixado nele.
        """

        self.marcar_pelo_formulario()

        self.bloco.notes = "Férias de verão"
        self.bloco.full_clean()
        self.bloco.save()

        self.bloco.refresh_from_db()

        self.assertEqual(self.bloco.notes, "Férias de verão")

    def test_a_normal_appointment_added_later_does_lock_the_block(self):
        # Só o encaixe é dispensado. Uma marcação normal no dia continua a
        # impedir que o bloqueio seja alterado por cima dela.
        outra_segunda = self.segunda + timedelta(days=7)
        self.marcar(dia=outra_segunda)

        self.bloco.date = outra_segunda

        with self.assertRaises(ValidationError):
            self.bloco.full_clean()
