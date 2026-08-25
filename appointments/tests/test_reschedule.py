"""Remarcar: mudar o dia, a hora, o serviço ou o estado de uma marcação.

Era "editar marcação" e abria o formulário inteiro, com a escolha da cliente e
tudo. Trocar a cliente ali seria transformar a marcação de uma pessoa na
marcação de outra, e o histórico ficava a dizer que a primeira tinha sido
atendida.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.forms import AppointmentRescheduleForm
from appointments.models import Appointment, Customer
from appointments.tests.factories import create_test_service, ensure_test_business_hour


class RescheduleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@exemplo.pt",
            phone="+351910000000",
        )

        self.outra = Customer.objects.create(
            full_name="Ana Ferreira",
            email="ana@exemplo.pt",
            phone="+351911111111",
        )

        self.service = create_test_service(duration_minutes=60)

        self.date = timezone.localdate() + timedelta(days=14)
        while self.date.weekday() != 0:
            self.date += timedelta(days=1)

        for weekday in range(7):
            ensure_test_business_hour(
                weekday=weekday,
                start_time=time(9, 0),
                end_time=time(18, 0),
            )

        self.appointment = Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=self.date,
            start_time=time(10, 0),
            created_by=self.user,
            status=Appointment.STATUS_SCHEDULED,
        )

        self.client.force_login(self.user)
        self.url = reverse(
            "appointments:appointment_update", args=[self.appointment.pk]
        )

    def dados(self, **campos):
        valores = {
            "service": self.service.pk,
            "date": (self.date + timedelta(days=1)).strftime("%Y-%m-%d"),
            "start_time": "11:00",
            "status": Appointment.STATUS_CONFIRMED,
        }
        valores.update(campos)

        return valores

    def html(self):
        return self.client.get(self.url).content.decode()

    def test_the_page_is_called_rescheduling(self):
        html = self.html()

        self.assertIn("Remarcação", html)
        self.assertNotIn("Editar marcação", html)

    def test_the_buttons_that_lead_here_say_reschedule(self):
        detalhe = self.client.get(
            reverse("appointments:appointment_detail", args=[self.appointment.pk])
        ).content.decode()

        self.assertIn("Remarcar", detalhe)

    def test_the_customer_shows_up_but_cannot_be_changed(self):
        html = self.html()

        self.assertIn("Maria Silva", html)
        self.assertIn("disabled", html)

        # Nada que permita escolher outra pessoa.
        self.assertNotIn('name="customer"', html)
        self.assertNotIn('name="customer_mode"', html)
        self.assertNotIn("Ana Ferreira", html)

    def test_only_four_things_can_change(self):
        campos = set(AppointmentRescheduleForm().fields)

        self.assertEqual(campos, {"service", "date", "start_time", "status"})

    def test_the_status_comes_confirmed(self):
        # Quem remarca está a combinar o horário novo com a cliente: fica
        # confirmado, e não volta a "Agendada" para ser confirmado noutro ecrã.
        resposta = self.client.get(self.url)

        self.assertEqual(
            resposta.context["form"].initial["status"],
            Appointment.STATUS_CONFIRMED,
        )

    def test_rescheduling_moves_the_appointment(self):
        novo_dia = self.date + timedelta(days=1)

        self.client.post(self.url, data=self.dados())

        self.appointment.refresh_from_db()

        self.assertEqual(self.appointment.date, novo_dia)
        self.assertEqual(self.appointment.start_time, time(11, 0))
        self.assertEqual(self.appointment.status, Appointment.STATUS_CONFIRMED)

    def test_the_customer_stays_the_same(self):
        # Mesmo que alguém submeta o endereço à mão com outra cliente lá.
        self.client.post(self.url, data=self.dados(customer=self.outra.pk))

        self.appointment.refresh_from_db()

        self.assertEqual(self.appointment.customer, self.customer)

    def test_the_home_visit_address_is_not_lost(self):
        # Não está no formulário, e um ModelForm só escreve os campos que tem:
        # o que já lá estava fica como estava.
        self.appointment.is_home_visit = True
        self.appointment.home_street = "Rua das Flores"
        self.appointment.home_number = "12"
        self.appointment.save()

        self.client.post(self.url, data=self.dados())

        self.appointment.refresh_from_db()

        self.assertTrue(self.appointment.is_home_visit)
        self.assertEqual(self.appointment.home_street, "Rua das Flores")

    def test_the_home_visit_is_shown_to_whoever_reschedules(self):
        # Um domicílio noutro dia continua a ser um domicílio, e a deslocação
        # conta para o horário.
        self.appointment.is_home_visit = True
        self.appointment.home_street = "Rua das Flores"
        self.appointment.save()

        self.assertIn("Atendimento em domicílio", self.html())

    def test_the_notes_are_not_lost_either(self):
        self.appointment.notes = "Levar material próprio."
        self.appointment.save()

        self.client.post(self.url, data=self.dados())

        self.appointment.refresh_from_db()

        self.assertEqual(self.appointment.notes, "Levar material próprio.")

    def test_an_out_of_hours_slot_is_accepted_and_flagged(self):
        # O encaixe continua a valer aqui: quem remarca está com a agenda à
        # frente e decidiu encaixar a pessoa.
        self.client.post(self.url, data=self.dados(start_time="20:00"))

        self.appointment.refresh_from_db()

        self.assertEqual(self.appointment.start_time, time(20, 0))
        self.assertTrue(self.appointment.outside_schedule)

    def test_a_clash_with_another_appointment_is_still_refused(self):
        Appointment.objects.create(
            customer=self.outra,
            service=self.service,
            date=self.date + timedelta(days=1),
            start_time=time(11, 0),
            created_by=self.user,
        )

        resposta = self.client.post(self.url, data=self.dados())

        self.assertEqual(resposta.status_code, 200)

        self.appointment.refresh_from_db()

        self.assertEqual(self.appointment.date, self.date)

    def test_a_completed_appointment_cannot_be_rescheduled(self):
        self.appointment.status = Appointment.STATUS_COMPLETED
        self.appointment.save(update_fields=["status"])

        resposta = self.client.get(self.url)

        self.assertRedirects(resposta, reverse("appointments:appointment_list"))
