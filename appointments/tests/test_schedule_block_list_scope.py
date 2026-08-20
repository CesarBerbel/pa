from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import ScheduleBlock

TODOS_OS_DIAS = "0,1,2,3,4,5,6"


class ScheduleBlockListScopeTests(TestCase):
    """Que bloqueios aparecem na lista.

    A lista é para agir sobre a agenda que aí vem. Os bloqueios antigos
    acumulam-se depressa — um almoço recorrente que acabou, umas férias do ano
    passado — e empurram para baixo o que ainda fecha a agenda.

    O que decide não é a data de início: um bloqueio que começou ontem e acaba
    amanhã continua a fechar a agenda hoje.
    """

    def setUp(self):
        # A migração de dados semeia um bloqueio para a pausa de almoço, que
        # traria ruído a estas contagens.
        ScheduleBlock.objects.all().delete()

        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.hoje = timezone.localdate()

        self.client.force_login(self.user)
        self.url = reverse("appointments:schedule_block_list")

    def bloquear(self, nome, **campos):
        return ScheduleBlock.objects.create(
            block_type=ScheduleBlock.BLOCK_TYPE_BREAK,
            start_time=time(13, 0),
            end_time=time(14, 0),
            notes=nome,
            **campos,
        )

    def listados(self, **params):
        return [
            bloco.notes for bloco in self.client.get(self.url, params).context["blocks"]
        ]

    def test_a_block_from_a_past_day_is_out(self):
        self.bloquear("ontem", date=self.hoje - timedelta(days=1))

        self.assertEqual(self.listados(), [])

    def test_today_and_the_future_stay(self):
        self.bloquear("hoje", date=self.hoje)
        self.bloquear("amanhã", date=self.hoje + timedelta(days=1))

        self.assertEqual(self.listados(), ["hoje", "amanhã"])

    def test_a_recurrence_that_started_before_today_but_has_not_ended_stays(self):
        # O caso do pedido: começou ontem, acaba amanhã, e hoje fecha a agenda.
        self.bloquear(
            "a decorrer",
            date=self.hoje - timedelta(days=1),
            is_recurring=True,
            recurring_weekdays=TODOS_OS_DIAS,
            recurrence_end_date=self.hoje + timedelta(days=1),
        )

        self.assertEqual(self.listados(), ["a decorrer"])

    def test_a_recurrence_that_ends_today_still_counts(self):
        # Acabar hoje é acabar no fim do dia, não no início.
        self.bloquear(
            "último dia",
            date=self.hoje - timedelta(days=30),
            is_recurring=True,
            recurring_weekdays=TODOS_OS_DIAS,
            recurrence_end_date=self.hoje,
        )

        self.assertEqual(self.listados(), ["último dia"])

    def test_a_recurrence_that_already_ended_is_out(self):
        self.bloquear(
            "acabou",
            date=self.hoje - timedelta(days=30),
            is_recurring=True,
            recurring_weekdays=TODOS_OS_DIAS,
            recurrence_end_date=self.hoje - timedelta(days=1),
        )

        self.assertEqual(self.listados(), [])

    def test_a_recurrence_without_an_end_never_leaves(self):
        # Sem data de fim, a repetição não acaba — é o caso da pausa de almoço.
        self.bloquear(
            "para sempre",
            date=self.hoje - timedelta(days=90),
            is_recurring=True,
            recurring_weekdays=TODOS_OS_DIAS,
        )

        self.assertEqual(self.listados(), ["para sempre"])

    def test_the_history_is_one_click_away(self):
        # Escondidos não é apagados: um bloqueio antigo ainda se pode querer
        # consultar ou apagar.
        self.bloquear("ontem", date=self.hoje - timedelta(days=1))
        self.bloquear("hoje", date=self.hoje)

        self.assertEqual(self.listados(), ["hoje"])
        self.assertEqual(sorted(self.listados(todos="1")), ["hoje", "ontem"])

    def test_the_screen_says_how_many_it_is_hiding(self):
        self.bloquear("ontem", date=self.hoje - timedelta(days=1))
        self.bloquear("anteontem", date=self.hoje - timedelta(days=2))

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.context["hidden_total"], 2)
        self.assertContains(resposta, "Ver também os 2 já terminados")

    def test_with_nothing_hidden_there_is_nothing_to_offer(self):
        self.bloquear("hoje", date=self.hoje)

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.context["hidden_total"], 0)
        self.assertNotContains(resposta, "já terminados")

    def test_an_empty_list_says_which_emptiness_it_is(self):
        # "Nenhum bloqueio registado" com bloqueios antigos na base seria falso.
        self.bloquear("ontem", date=self.hoje - timedelta(days=1))

        self.assertContains(self.client.get(self.url), "Nenhum bloqueio em vigor")
        self.assertContains(
            self.client.get(self.url, {"todos": "1"}), "Bloqueios de agenda"
        )
