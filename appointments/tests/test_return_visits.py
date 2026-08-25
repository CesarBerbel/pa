"""Retornos: a intenção de voltar, desde que nasce até a mensagem sair.

O que isto protege é a diferença entre um retorno e um lembrete escrito nas
observações: um retorno tem estado, tem data-alvo e aparece numa lista. Uma
frase nas observações não tem nada disso, e por isso não volta a ser lida.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from io import StringIO

from appointments import return_services
from appointments.models import Appointment, Customer, ReturnVisit
from appointments.tests.factories import create_test_service, ensure_test_business_hour


class ReturnVisitBase(TestCase):
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

        self.service = create_test_service(duration_minutes=60)
        self.service.return_days = 21
        self.service.save(update_fields=["return_days"])

        self.hoje = timezone.localdate()

        for weekday in range(7):
            ensure_test_business_hour(
                weekday=weekday,
                start_time=time(9, 0),
                end_time=time(18, 0),
            )

        self.client.force_login(self.user)

    def marcacao(self, **campos):
        valores = {
            "customer": self.customer,
            "service": self.service,
            "date": self.hoje,
            "start_time": time(10, 0),
            "created_by": self.user,
            "status": Appointment.STATUS_CONFIRMED,
        }
        valores.update(campos)

        return Appointment.objects.create(**valores)

    def retorno(self, **campos):
        valores = {
            "customer": self.customer,
            "service": self.service,
            "target_date": self.hoje + timedelta(days=21),
        }
        valores.update(campos)

        return ReturnVisit.objects.create(**valores)


class WhenAReturnIsBornTests(ReturnVisitBase):
    """Nasce ao concluir o atendimento, que é quando se sabe se é preciso."""

    def concluir(self, marcacao, **extra):
        dados = {"send_message": "0"}
        dados.update(extra)

        return self.client.post(
            reverse("appointments:appointment_complete", args=[marcacao.pk]),
            data=dados,
        )

    def test_completing_without_asking_creates_nothing(self):
        self.concluir(self.marcacao())

        self.assertEqual(ReturnVisit.objects.count(), 0)

    def test_completing_with_days_opens_a_return(self):
        marcacao = self.marcacao()

        self.concluir(marcacao, return_days="21")

        retorno = ReturnVisit.objects.get()

        self.assertEqual(retorno.customer, self.customer)
        self.assertEqual(retorno.origin, marcacao)
        self.assertEqual(retorno.status, ReturnVisit.STATUS_PENDING)

    def test_the_target_date_counts_from_the_appointment(self):
        # Uma marcação concluída no dia seguinte — ao arrumar a agenda — não
        # pode empurrar o retorno um dia para a frente.
        marcacao = self.marcacao(date=self.hoje - timedelta(days=1))

        self.concluir(marcacao, return_days="21")

        self.assertEqual(
            ReturnVisit.objects.get().target_date,
            self.hoje - timedelta(days=1) + timedelta(days=21),
        )

    def test_the_service_carries_the_suggestion(self):
        marcacao = self.marcacao()

        self.assertEqual(return_services.suggested_days(marcacao), 21)

    def test_the_completion_window_offers_the_suggestion(self):
        marcacao = self.marcacao()

        html = self.client.get(
            reverse("appointments:appointment_detail", args=[marcacao.pk])
        ).content.decode()

        self.assertIn("data-ask-return", html)
        self.assertIn('data-return-suggested="21"', html)
        self.assertIn('name="return_days"', html)

    def test_it_can_also_be_opened_by_hand(self):
        # Para quem ligou depois a pedir revisão, sem ter havido conclusão.
        self.client.post(
            reverse("appointments:return_visit_create", args=[self.customer.pk]),
            data={"dias": "30", "notas": "Pediu revisão ao telefone."},
        )

        retorno = ReturnVisit.objects.get()

        self.assertEqual(retorno.target_date, self.hoje + timedelta(days=30))
        self.assertIn("revisão", retorno.notes)
        self.assertIsNone(retorno.origin)


class TheListOfReturnsTests(ReturnVisitBase):
    """A lista é a agenda de telefonemas. Sem ela, não há sistema nenhum."""

    def pagina(self, **params):
        return self.client.get(reverse("appointments:return_visit_list"), params)

    def test_a_pending_return_shows_up(self):
        self.retorno()

        self.assertContains(self.pagina(), "Maria Silva")

    def test_a_late_one_is_marked_as_late(self):
        self.retorno(target_date=self.hoje - timedelta(days=3))

        self.assertContains(self.pagina(), "Atrasado")

    def test_lateness_is_not_a_stored_state(self):
        # Seria um estado que envelhece sozinho e obrigava alguém a correr
        # atrás dele todos os dias.
        retorno = self.retorno(target_date=self.hoje - timedelta(days=1))

        self.assertEqual(retorno.status, ReturnVisit.STATUS_PENDING)
        self.assertTrue(retorno.is_late)

    def test_the_oldest_comes_first(self):
        self.retorno(target_date=self.hoje + timedelta(days=30))
        antigo = self.retorno(target_date=self.hoje - timedelta(days=5))

        self.assertEqual(return_services.pending().first(), antigo)

    def test_a_scheduled_one_leaves_the_list(self):
        retorno = self.retorno()
        return_services.attach_appointment(retorno, self.marcacao())

        self.assertNotContains(self.pagina(), "Por marcar")
        self.assertEqual(return_services.pending().count(), 0)

    def test_dismissing_keeps_the_decision(self):
        # Apagá-lo perdia a decisão: no mês seguinte ninguém sabia se aquela
        # pessoa tinha sido dispensada ou se o retorno nunca existiu.
        retorno = self.retorno()

        self.client.post(
            reverse("appointments:return_visit_dismiss", args=[retorno.pk])
        )

        retorno.refresh_from_db()

        self.assertEqual(retorno.status, ReturnVisit.STATUS_DISMISSED)
        self.assertEqual(ReturnVisit.objects.count(), 1)

    def test_the_dashboard_shows_how_many_are_waiting(self):
        self.retorno()

        html = self.client.get(reverse("dashboard")).content.decode()

        self.assertIn("1 por marcar", html)
        self.assertIn(reverse("appointments:return_visit_list"), html)

    def test_the_menu_leads_here(self):
        html = self.client.get(reverse("dashboard")).content.decode()

        self.assertIn("Retornos", html)


class BookingAReturnTests(ReturnVisitBase):
    """Marcar leva ao ecrã de sempre, com a cliente e o serviço já escolhidos."""

    def test_the_form_comes_prefilled(self):
        retorno = self.retorno()

        resposta = self.client.get(
            reverse("appointments:appointment_create") + f"?retorno={retorno.pk}"
        )

        inicial = resposta.context["form"].initial

        self.assertEqual(inicial["customer"], self.customer.pk)
        self.assertEqual(inicial["service"], self.service.pk)
        self.assertContains(resposta, "Retorno de")

    def test_saving_marks_the_return_as_scheduled(self):
        retorno = self.retorno()
        dia = self.hoje + timedelta(days=21)

        self.client.post(
            reverse("appointments:appointment_create") + f"?retorno={retorno.pk}",
            data={
                "customer_mode": "existing",
                "customer": self.customer.pk,
                "service": self.service.pk,
                "date": dia.strftime("%Y-%m-%d"),
                "start_time": "10:00",
                "status": Appointment.STATUS_CONFIRMED,
                "notes": "",
            },
        )

        retorno.refresh_from_db()

        self.assertEqual(retorno.status, ReturnVisit.STATUS_SCHEDULED)
        self.assertIsNotNone(retorno.appointment)
        self.assertEqual(retorno.appointment.date, dia)


class TheReminderTests(ReturnVisitBase):
    """A mensagem que traz a pessoa de volta."""

    def correr(self, **opcoes):
        saida = StringIO()
        call_command("send_return_reminders", stdout=saida, **opcoes)

        return saida.getvalue()

    def test_a_return_far_away_is_not_touched(self):
        self.retorno(target_date=self.hoje + timedelta(days=60))

        self.correr()

        self.assertEqual(mail.outbox, [])
        self.assertIsNone(ReturnVisit.objects.get().notified_at)

    def test_a_return_within_the_week_gets_the_message(self):
        self.retorno(target_date=self.hoje + timedelta(days=3))

        self.correr()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("maria@exemplo.pt", mail.outbox[0].to)
        self.assertIn("voltar", mail.outbox[0].subject.lower())

    def test_it_does_not_repeat_the_next_day(self):
        # O comando corre todos os dias.
        self.retorno(target_date=self.hoje + timedelta(days=3))

        self.correr()
        self.correr()

        self.assertEqual(len(mail.outbox), 1)

    def test_it_does_not_write_to_who_already_booked(self):
        # Recebe a mensagem, entra no site e marca. Mandar outra seria falar
        # com quem já voltou.
        self.retorno(target_date=self.hoje + timedelta(days=3))
        self.marcacao(date=self.hoje + timedelta(days=4))

        saida = self.correr()

        self.assertEqual(mail.outbox, [])
        self.assertIn("já tem marcação", saida)

    def test_a_long_forgotten_return_is_left_alone(self):
        # A mensagem chegaria a dizer que estava na altura de voltar há dois
        # meses. Fica na lista, como atrasado, para alguém decidir.
        self.retorno(target_date=self.hoje - timedelta(days=90))

        self.correr()

        self.assertEqual(mail.outbox, [])

    def test_a_scheduled_return_is_not_written_to(self):
        retorno = self.retorno(target_date=self.hoje + timedelta(days=3))
        return_services.attach_appointment(retorno, self.marcacao())

        self.correr()

        self.assertEqual(mail.outbox, [])

    def test_the_dry_run_sends_nothing(self):
        self.retorno(target_date=self.hoje + timedelta(days=3))

        saida = self.correr(dry_run=True)

        self.assertEqual(mail.outbox, [])
        self.assertIsNone(ReturnVisit.objects.get().notified_at)
        self.assertIn("simulação", saida)

    def test_the_message_invites_to_book(self):
        # É a única mensagem desta casa que fala de uma marcação que ainda não
        # existe: leva a ligação para a fazer.
        self.retorno(target_date=self.hoje + timedelta(days=3))

        self.correr()

        self.assertIn(
            reverse("appointments:public_visual_schedule"), mail.outbox[0].body
        )
