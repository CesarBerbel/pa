"""Retornos: a intenção de voltar, desde que nasce até a mensagem sair.

O que isto protege é a diferença entre um retorno e um lembrete escrito nas
observações: um retorno tem estado, tem data-alvo e aparece numa lista. Uma
frase nas observações não tem nada disso, e por isso não volta a ser lida.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
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
        self.assertEqual(inicial["date"], retorno.target_date.isoformat())

        # Pelo contexto e não pela frase do aviso: o texto reescreve-se, e um
        # teste amarrado à redação falha quando ela melhora.
        self.assertEqual(resposta.context["retorno"], retorno)

    def test_the_person_and_the_treatment_come_as_labels(self):
        """Já foram decididos quando o retorno foi aberto.

        Mostrá-los como listas era convidar a mudá-los — e mudá-los aqui fazia
        a marcação deixar de cumprir o retorno que a trouxe.
        """

        retorno = self.retorno()

        resposta = self.client.get(
            reverse("appointments:appointment_create") + f"?retorno={retorno.pk}"
        )
        corpo = resposta.content.decode()

        self.assertIn("appointment-fixed-fields", corpo)
        self.assertIn(self.customer.full_name, corpo)
        self.assertIn(self.service.name, corpo)

        # Escondidos e não desativados: um campo desativado não é submetido, e
        # o formulário perdia a pessoa pelo caminho.
        self.assertIn('type="hidden" name="customer"', corpo)
        self.assertNotIn("customer-mode-switch", corpo)

    def test_the_date_stays_editable(self):
        # A data combinada ao telefone raramente é a que estava prevista.
        retorno = self.retorno()

        resposta = self.client.get(
            reverse("appointments:appointment_create") + f"?retorno={retorno.pk}"
        )

        self.assertContains(resposta, 'name="date"')
        self.assertNotContains(resposta, 'name="date" type="hidden"')

    def test_the_person_cannot_be_swapped_from_outside(self):
        """O campo escondido é um campo que se pode trocar por fora.

        Apertar a lista a uma opção é o que fecha isso: com outra pessoa no
        pedido, o formulário recusa em vez de gravar uma marcação que não
        cumpre o retorno nenhum.
        """

        retorno = self.retorno()

        outra = Customer.objects.create(
            full_name="Outra Pessoa",
            email="outra@exemplo.pt",
            phone="+351910000001",
        )

        resposta = self.client.post(
            reverse("appointments:appointment_create") + f"?retorno={retorno.pk}",
            data={
                "customer_mode": "existing",
                "customer": outra.pk,
                "service": self.service.pk,
                "date": (self.hoje + timedelta(days=21)).isoformat(),
                "start_time": "14:00",
                "status": Appointment.STATUS_CONFIRMED,
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Appointment.objects.filter(customer=outra).exists())

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


class OpeningAReturnByHandTests(ReturnVisitBase):
    """A porta da frente: abrir um retorno escolhendo o atendimento.

    Os outros dois caminhos — a conclusão de um atendimento e o botão da ficha
    da pessoa — servem quem já está no meio de outra coisa. Este serve quem
    abre a lista porque alguém ligou a pedir revisão, e era o caso que não
    tinha por onde entrar.
    """

    def setUp(self):
        super().setUp()

        self.concluida = self.marcacao(status=Appointment.STATUS_COMPLETED)

    def dados(self, **extra):
        campos = {
            "origin": self.concluida.pk,
            "target_date": (self.hoje + timedelta(days=21)).isoformat(),
            "notes": "",
        }
        campos.update(extra)

        return campos

    def test_the_screen_offers_completed_appointments(self):
        resposta = self.client.get(reverse("appointments:return_visit_new"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Maria Silva")

    def test_an_appointment_that_has_not_happened_is_not_offered(self):
        # Um retorno é o seguimento de algo que aconteceu. Propor um
        # agendamento futuro como origem seria propor o retorno de uma consulta
        # que ainda não houve.
        futura = self.marcacao(
            date=self.hoje + timedelta(days=3),
            start_time=time(11, 0),
            status=Appointment.STATUS_CONFIRMED,
        )

        resposta = self.client.get(reverse("appointments:return_visit_new"))
        opcoes = resposta.context["form"].fields["origin"].queryset

        self.assertIn(self.concluida, opcoes)
        self.assertNotIn(futura, opcoes)

    def test_an_appointment_that_already_has_a_return_is_not_offered(self):
        """A lista é para escolher, não para procurar.

        Com os já tratados lá dentro, quem abre o ecrã tinha de se lembrar de
        cor quais é que já fez — e a lista cresce todos os dias.
        """

        self.retorno(origin=self.concluida)

        resposta = self.client.get(reverse("appointments:return_visit_new"))

        self.assertNotIn(
            self.concluida, resposta.context["form"].fields["origin"].queryset
        )

    def test_a_dismissed_return_frees_the_appointment_again(self):
        # Dispensar é decidir que desta vez não se volta, não é fechar a porta
        # para sempre.
        aberto = self.retorno(origin=self.concluida)
        return_services.dismiss(aberto)

        resposta = self.client.get(reverse("appointments:return_visit_new"))

        self.assertIn(
            self.concluida, resposta.context["form"].fields["origin"].queryset
        )

    def test_a_booked_return_keeps_the_appointment_out(self):
        # Já marcado continua a ser um retorno que existe: reabri-lo daria dois
        # retornos para a mesma consulta.
        aberto = self.retorno(origin=self.concluida)
        cumprida = self.marcacao(
            date=self.hoje + timedelta(days=21), start_time=time(15, 0)
        )
        return_services.attach_appointment(aberto, cumprida)

        resposta = self.client.get(reverse("appointments:return_visit_new"))

        self.assertNotIn(
            self.concluida, resposta.context["form"].fields["origin"].queryset
        )

    def test_the_return_is_born_tied_to_the_appointment(self):
        # É isto que dá o histórico: com a origem guardada, a marcação de
        # daqui a um mês sabe dizer de que consulta veio.
        self.client.post(reverse("appointments:return_visit_new"), data=self.dados())

        retorno = ReturnVisit.objects.latest("id")

        self.assertEqual(retorno.origin, self.concluida)
        self.assertEqual(retorno.customer, self.concluida.customer)
        self.assertEqual(retorno.service, self.concluida.service)

    def test_the_person_is_never_asked_for_twice(self):
        # A pessoa vem do atendimento. Pedi-la à parte abria a porta a um
        # retorno cujo cliente não é o do atendimento de origem.
        resposta = self.client.get(reverse("appointments:return_visit_new"))

        self.assertNotContains(resposta, 'name="customer"')

    def test_a_date_in_the_past_is_refused(self):
        resposta = self.client.post(
            reverse("appointments:return_visit_new"),
            data=self.dados(target_date=(self.hoje - timedelta(days=1)).isoformat()),
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(ReturnVisit.objects.exists())

    def test_it_lands_on_the_list_and_says_so(self):
        resposta = self.client.post(
            reverse("appointments:return_visit_new"), data=self.dados(), follow=True
        )

        self.assertRedirects(resposta, reverse("appointments:return_visit_list"))
        self.assertContains(resposta, "Maria Silva")

    def test_coming_from_an_appointment_it_arrives_filled_in(self):
        # O serviço propõe 21 dias, e a data conta-se do dia do atendimento.
        resposta = self.client.get(
            reverse("appointments:return_visit_new")
            + f"?atendimento={self.concluida.pk}"
        )

        inicial = resposta.context["form"].initial

        self.assertEqual(inicial["origin"], self.concluida.pk)
        self.assertEqual(
            inicial["target_date"], self.concluida.date + timedelta(days=21)
        )

    def test_a_customer_cannot_open_returns(self):
        cliente = get_user_model().objects.create_user(
            email="cliente@exemplo.pt",
            password="StrongPassword123",
            full_name="Cliente",
        )

        self.client.force_login(cliente)

        self.assertNotEqual(
            self.client.get(reverse("appointments:return_visit_new")).status_code, 200
        )


class TheHistoryBetweenAppointmentsTests(ReturnVisitBase):
    """As duas pontas: de onde o retorno veio e o que o cumpriu.

    A ligação já existia na base de dados e não se via em lado nenhum: abrir
    uma consulta não dizia que ela vinha de outra, nem que outra tinha nascido
    dela. Um histórico que não se lê não é um histórico.
    """

    def setUp(self):
        super().setUp()

        self.origem = self.marcacao(status=Appointment.STATUS_COMPLETED)
        self.retorno_aberto = self.retorno(origin=self.origem)

    def detalhe(self, appointment):
        return self.client.get(
            reverse("appointments:appointment_detail", args=[appointment.pk])
        )

    def test_the_origin_says_it_generated_a_return(self):
        resposta = self.detalhe(self.origem)

        self.assertContains(resposta, "Retorno gerado")

    def test_the_booked_appointment_says_where_it_came_from(self):
        cumprida = self.marcacao(
            date=self.hoje + timedelta(days=21), start_time=time(15, 0)
        )

        return_services.attach_appointment(self.retorno_aberto, cumprida)

        resposta = self.detalhe(cumprida)

        self.assertContains(resposta, "Retorno de")
        self.assertContains(
            resposta,
            reverse("appointments:appointment_detail", args=[self.origem.pk]),
        )

    def test_an_ordinary_appointment_says_neither(self):
        # Sem retorno pelo meio, os dois campos não existem: um rótulo vazio
        # é ruído no ecrã que se lê todos os dias.
        solta = self.marcacao(
            date=self.hoje + timedelta(days=2), start_time=time(16, 0)
        )

        resposta = self.detalhe(solta)

        self.assertNotContains(resposta, "Retorno gerado")
        self.assertNotContains(resposta, "Retorno de")

    def test_the_card_links_to_both_ends(self):
        cumprida = self.marcacao(
            date=self.hoje + timedelta(days=21), start_time=time(15, 0)
        )

        return_services.attach_appointment(self.retorno_aberto, cumprida)

        resposta = self.client.get(
            reverse("appointments:return_visit_list") + "?estado=todos"
        )

        self.assertContains(
            resposta,
            reverse("appointments:appointment_detail", args=[self.origem.pk]),
        )
        self.assertContains(
            resposta,
            reverse("appointments:appointment_detail", args=[cumprida.pk]),
        )


class TheThreeChoicesAtCompletionTests(ReturnVisitBase):
    """Ao concluir, a profissional decide entre três coisas e não duas.

    Entre "não volta" e "volta daqui a três semanas" faltava o caso de quem
    combina a data ali mesmo, com a pessoa à frente. Esse virava um "prever" e
    alguém tinha de o marcar outra vez a partir de uma lista, repetindo uma
    decisão já tomada.
    """

    def concluir(self, marcacao, **extra):
        dados = {"send_message": "0"}
        dados.update(extra)

        return self.client.post(
            reverse("appointments:appointment_complete", args=[marcacao.pk]),
            data=dados,
        )

    def test_choosing_none_creates_nothing(self):
        self.concluir(self.marcacao(), return_mode="none", return_days="21")

        self.assertEqual(ReturnVisit.objects.count(), 0)

    def test_choosing_predicted_opens_a_return_without_booking(self):
        self.concluir(self.marcacao(), return_mode="predicted", return_days="21")

        retorno = ReturnVisit.objects.get()

        self.assertEqual(retorno.status, ReturnVisit.STATUS_PENDING)
        self.assertIsNone(retorno.appointment)

    def test_choosing_scheduled_books_it_there_and_then(self):
        quando = self.hoje + timedelta(days=21)

        self.concluir(
            self.marcacao(),
            return_mode="scheduled",
            return_date=quando.isoformat(),
            return_time="14:30",
        )

        retorno = ReturnVisit.objects.get()

        self.assertEqual(retorno.status, ReturnVisit.STATUS_SCHEDULED)
        self.assertIsNotNone(retorno.appointment)
        self.assertEqual(retorno.appointment.date, quando)
        self.assertEqual(retorno.appointment.start_time, time(14, 30))
        self.assertEqual(retorno.appointment.status, Appointment.STATUS_CONFIRMED)

    def test_the_booked_return_keeps_both_ends(self):
        marcacao = self.marcacao()

        self.concluir(
            marcacao,
            return_mode="scheduled",
            return_date=(self.hoje + timedelta(days=21)).isoformat(),
            return_time="14:30",
        )

        retorno = ReturnVisit.objects.get()

        self.assertEqual(retorno.origin, marcacao)
        self.assertEqual(retorno.customer, marcacao.customer)

    def test_the_language_follows_the_person(self):
        # Quem foi atendido em inglês da primeira vez não passa a receber
        # português na segunda.
        self.concluir(
            self.marcacao(customer_speaks_english=True),
            return_mode="scheduled",
            return_date=(self.hoje + timedelta(days=21)).isoformat(),
            return_time="14:30",
        )

        self.assertTrue(ReturnVisit.objects.get().appointment.customer_speaks_english)

    def test_a_taken_slot_leaves_the_return_predicted(self):
        """A conclusão já aconteceu: uma hora ocupada não pode desfazê-la.

        Fica o retorno previsto — a intenção não se perde — e quem marcar
        escolhe outra hora.
        """

        quando = self.hoje + timedelta(days=21)

        self.marcacao(date=quando, start_time=time(14, 30))

        self.concluir(
            self.marcacao(start_time=time(9, 0)),
            return_mode="scheduled",
            return_date=quando.isoformat(),
            return_time="14:30",
        )

        retorno = ReturnVisit.objects.get()

        self.assertEqual(retorno.status, ReturnVisit.STATUS_PENDING)
        self.assertIsNone(retorno.appointment)
        self.assertEqual(retorno.target_date, quando)

    def test_a_form_from_before_this_change_still_works(self):
        # Sem `return_mode`, o que o pedido traz é o número de dias — e é assim
        # que continua a ser lido.
        self.concluir(self.marcacao(), return_days="21")

        self.assertEqual(ReturnVisit.objects.count(), 1)


class WhereYouLandAfterTests(ReturnVisitBase):
    """Quem veio dos retornos volta aos retornos.

    Era uma lista de telefonemas por fazer; atirar a pessoa para a lista geral
    de marcações obrigava-a a procurar o caminho de volta.
    """

    MOTIVO = {
        "cancellation_reason": "A pessoa avisou que nao pode vir.",
        "send_message": "0",
    }

    def test_completing_a_return_lands_on_the_returns(self):
        retorno = self.retorno()
        cumprida = self.marcacao()
        return_services.attach_appointment(retorno, cumprida)

        resposta = self.client.post(
            reverse("appointments:appointment_complete", args=[cumprida.pk]),
            data={"send_message": "0"},
        )

        self.assertRedirects(resposta, reverse("appointments:return_visit_list"))

    def test_completing_an_appointment_that_opens_a_return_lands_there_too(self):
        resposta = self.client.post(
            reverse("appointments:appointment_complete", args=[self.marcacao().pk]),
            data={
                "send_message": "0",
                "return_mode": "predicted",
                "return_days": "21",
            },
        )

        self.assertRedirects(resposta, reverse("appointments:return_visit_list"))

    def test_an_ordinary_completion_still_lands_on_the_appointments(self):
        # Sem retorno pelo meio, o assunto em mãos continua a ser a marcação.
        resposta = self.client.post(
            reverse("appointments:appointment_complete", args=[self.marcacao().pk]),
            data={"send_message": "0", "return_mode": "none"},
        )

        self.assertRedirects(resposta, reverse("appointments:appointment_list"))

    def test_cancelling_a_return_lands_on_the_returns(self):
        retorno = self.retorno()
        cumprida = self.marcacao(date=self.hoje + timedelta(days=21))
        return_services.attach_appointment(retorno, cumprida)

        resposta = self.client.post(
            reverse("appointments:appointment_cancel", args=[cumprida.pk]),
            data=self.MOTIVO,
        )

        self.assertRedirects(resposta, reverse("appointments:return_visit_list"))

    def test_cancelling_puts_the_person_back_on_the_list(self):
        """A marcação caiu, mas a pessoa continua a precisar de ser vista.

        Sem isto, o retorno ficava dado como cumprido para sempre e
        desaparecia da lista — a marcação cancelada, o retorno a dizer-se
        marcado, e ninguém voltava a ligar àquela pessoa.
        """

        retorno = self.retorno()
        cumprida = self.marcacao(date=self.hoje + timedelta(days=21))
        return_services.attach_appointment(retorno, cumprida)

        self.client.post(
            reverse("appointments:appointment_cancel", args=[cumprida.pk]),
            data=self.MOTIVO,
        )

        retorno.refresh_from_db()

        self.assertEqual(retorno.status, ReturnVisit.STATUS_PENDING)
        self.assertIsNone(retorno.appointment)

    def test_a_dismissed_return_is_not_revived_by_a_cancellation(self):
        # Dispensar foi uma decisão de quem atende, e um cancelamento não a
        # revoga.
        retorno = self.retorno()
        cumprida = self.marcacao(date=self.hoje + timedelta(days=21))
        return_services.attach_appointment(retorno, cumprida)
        return_services.dismiss(retorno)

        self.client.post(
            reverse("appointments:appointment_cancel", args=[cumprida.pk]),
            data=self.MOTIVO,
        )

        retorno.refresh_from_db()

        self.assertEqual(retorno.status, ReturnVisit.STATUS_DISMISSED)


class TheButtonOnTheCardTests(ReturnVisitBase):
    def test_a_pending_return_offers_marcar(self):
        self.retorno()

        corpo = self.client.get(
            reverse("appointments:return_visit_list")
        ).content.decode()

        self.assertIn(reverse("appointments:appointment_create"), corpo)

    def test_a_booked_return_offers_remarcar_instead(self):
        # Um "Marcar" aqui criava uma segunda marcação para o mesmo retorno.
        retorno = self.retorno()
        cumprida = self.marcacao(date=self.hoje + timedelta(days=21))
        return_services.attach_appointment(retorno, cumprida)

        corpo = self.client.get(
            reverse("appointments:return_visit_list") + "?estado=todos"
        ).content.decode()

        self.assertIn("Remarcar", corpo)
        self.assertIn(
            reverse("appointments:appointment_update", args=[cumprida.pk]), corpo
        )


class TheLockedFieldsWhenBookingTests(ReturnVisitBase):
    """Vindo de um retorno, o que ainda é uma escolha é a data e a hora."""

    def ecra(self, retorno):
        return self.client.get(
            reverse("appointments:appointment_create") + f"?retorno={retorno.pk}"
        )

    def test_the_status_is_not_a_choice(self):
        # O estado de um retorno combinado é sempre confirmado.
        corpo = self.ecra(self.retorno()).content.decode()

        self.assertIn('type="hidden" name="status"', corpo)

    def test_the_language_is_not_a_choice(self):
        corpo = self.ecra(self.retorno()).content.decode()

        self.assertIn('type="hidden" name="customer_speaks_english"', corpo)

    def test_the_language_comes_from_the_original_appointment(self):
        origem = self.marcacao(
            status=Appointment.STATUS_COMPLETED, customer_speaks_english=True
        )
        retorno = self.retorno(origin=origem)

        inicial = self.ecra(retorno).context["form"].initial

        self.assertTrue(inicial["customer_speaks_english"])


class TheReturnBadgeOnTheListTests(ReturnVisitBase):
    """Na lista de marcações, um retorno diz que é um retorno.

    Não é uma marcação nova: é a segunda metade de uma que já houve, e quem
    percorre a lista precisa de saber isso antes de abrir.
    """

    def lista(self):
        return self.client.get(reverse("appointments:appointment_list"))

    def cumprir(self, dias, hora=10):
        """Uma marcação que cumpre um retorno, daqui a `dias`."""

        retorno = self.retorno(target_date=self.hoje + timedelta(days=dias))
        cumprida = self.marcacao(
            date=self.hoje + timedelta(days=dias), start_time=time(hora, 0)
        )

        return return_services.attach_appointment(retorno, cumprida)

    def test_an_appointment_that_fulfils_a_return_is_marked(self):
        self.cumprir(21)

        self.assertContains(self.lista(), 'class="appointment-day-card-return"')

    def test_an_ordinary_appointment_is_not(self):
        self.marcacao()

        self.assertNotContains(self.lista(), 'class="appointment-day-card-return"')

    def test_the_badge_says_where_it_came_from(self):
        origem = self.marcacao(status=Appointment.STATUS_COMPLETED)
        retorno = self.retorno(origin=origem)
        cumprida = self.marcacao(date=self.hoje + timedelta(days=21))
        return_services.attach_appointment(retorno, cumprida)

        self.assertContains(
            self.lista(),
            f"Retorno do atendimento de {origem.date.strftime('%d/%m/%Y')}",
        )

    def test_the_appointment_that_generated_one_is_not_marked(self):
        # Quem gerou o retorno não é o retorno. Marcar as duas pontas com a
        # mesma etiqueta fazia a lista dizer "retorno" ao lado de consultas
        # que não o são.
        origem = self.marcacao(status=Appointment.STATUS_COMPLETED)
        self.retorno(origin=origem)

        self.assertNotContains(self.lista(), 'class="appointment-day-card-return"')

    def test_the_badge_does_not_cost_a_query_per_card(self):
        """Trinta marcações no ecrã não podem ser trinta idas à base de dados.

        Medido pelo que **não** muda: a página é pedida com um retorno na
        lista e depois com cinco, e o número de consultas tem de ser o mesmo.
        Comparar com um número escrito à mão falhava por razões erradas —
        o menu, a sessão e as contagens do cabeçalho também contam, e mudam
        por motivos que nada têm a ver com isto.
        """

        self.cumprir(21, hora=9)

        with CaptureQueriesContext(connection) as com_um:
            self.lista()

        for i in range(4):
            self.cumprir(30 + i, hora=10 + i)

        with CaptureQueriesContext(connection) as com_cinco:
            self.lista()

        self.assertEqual(len(com_cinco), len(com_um))
