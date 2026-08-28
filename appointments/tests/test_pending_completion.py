"""Atendimentos confirmados cuja data já passou.

É a ponta que trava tudo o resto: enquanto uma marcação não for concluída, não
gera retorno, não entra no que está por receber e não conta para a receita. Era
trabalho parado que não aparecia em lado nenhum.

Vive no dashboard operacional e não no financeiro: concluir é trabalho de
agenda, e quem olha para as contas quer ver o que já aconteceu, não arrumar o
que falta registar.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments import selectors
from appointments.models import Appointment, Customer
from appointments.tests.factories import create_test_service, ensure_test_business_hour


class PendingCompletionBase(TestCase):
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
        self.hoje = timezone.localdate()

        for weekday in range(7):
            ensure_test_business_hour(
                weekday=weekday, start_time=time(9, 0), end_time=time(18, 0)
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

    def ontem(self, **extra):
        campos = {"date": self.hoje - timedelta(days=1), "start_time": time(11, 0)}
        campos.update(extra)

        return self.marcacao(**campos)


class WhatIsWaitingToBeCompletedTests(PendingCompletionBase):
    def test_a_confirmed_appointment_in_the_past_is_waiting(self):
        self.assertIn(self.ontem(), selectors.por_concluir())

    def test_one_still_to_come_is_not(self):
        futura = self.marcacao(
            date=self.hoje + timedelta(days=2), start_time=time(9, 30)
        )

        self.assertNotIn(futura, selectors.por_concluir())

    def test_today_is_not_late_yet(self):
        # O dia ainda não acabou: uma consulta das 17:00 não está atrasada às
        # 10:00 da manhã.
        hoje = self.marcacao(start_time=time(17, 0))

        self.assertNotIn(hoje, selectors.por_concluir())

    def test_one_only_scheduled_is_left_alone(self):
        """Uma marcação por confirmar cuja data passou é outra coisa.

        Provavelmente não aconteceu — um pedido a que ninguém respondeu, ou
        uma falta. Dá-la por concluída seria inventar um atendimento.
        """

        agendada = self.ontem(status=Appointment.STATUS_SCHEDULED)

        self.assertNotIn(agendada, selectors.por_concluir())

    def test_a_cancelled_one_too(self):
        cancelada = self.ontem(status=Appointment.STATUS_CANCELLED)

        self.assertNotIn(cancelada, selectors.por_concluir())

    def test_an_already_completed_one_is_done(self):
        concluida = self.ontem(status=Appointment.STATUS_COMPLETED)

        self.assertNotIn(concluida, selectors.por_concluir())


class OnTheOperationalDashboardTests(PendingCompletionBase):
    def painel(self):
        return self.client.get(reverse("accounts:dashboard"))

    def test_it_is_up_front(self):
        self.ontem()

        resposta = self.painel()

        self.assertEqual(resposta.context["pending_completion_total"], 1)
        self.assertContains(resposta, "por concluir")
        self.assertContains(resposta, "pending-completion")

    def test_with_nothing_waiting_the_section_is_not_drawn(self):
        # Uma secção sempre presente e vazia só ensina a passar os olhos por
        # cima dela.
        self.assertNotContains(self.painel(), "pending-completion")

    def test_it_is_not_on_the_finance_screen(self):
        # Concluir é trabalho de agenda. Quem olha para as contas quer ver o
        # que já aconteceu, não arrumar o que falta registar.
        self.ontem()

        self.assertNotContains(
            self.client.get(reverse("finance:dashboard")), "pending-completion"
        )

    def test_completing_from_here_comes_back_here(self):
        """Quem conclui a partir desta lista está a arrumá-la.

        Ser atirado para outro ecrã obriga a voltar atrás para a seguinte.
        """

        marcacao = self.ontem()

        resposta = self.client.post(
            reverse("appointments:appointment_complete", args=[marcacao.pk]),
            data={
                "send_message": "0",
                "return_mode": "none",
                "next": reverse("accounts:dashboard"),
            },
        )

        self.assertRedirects(resposta, reverse("accounts:dashboard"))

    def test_a_next_pointing_outside_is_ignored(self):
        # Um `next` para fora do site é um redirecionamento aberto, e esses
        # servem para levar quem clica a uma página que imita esta.
        marcacao = self.ontem()

        resposta = self.client.post(
            reverse("appointments:appointment_complete", args=[marcacao.pk]),
            data={
                "send_message": "0",
                "return_mode": "none",
                "next": "https://exemplo-malicioso.pt/",
            },
        )

        self.assertNotIn("exemplo-malicioso", resposta["Location"])

    def test_completing_takes_it_out_of_the_list(self):
        marcacao = self.ontem()

        self.client.post(
            reverse("appointments:appointment_complete", args=[marcacao.pk]),
            data={"send_message": "0", "return_mode": "none"},
        )

        self.assertNotIn(marcacao, selectors.por_concluir())
