from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.tests.factories import create_test_service, ensure_test_business_hour


class PublicDayStripTests(TestCase):
    """A faixa de dias da agenda pública corre para a frente a partir de hoje.

    Antes começava na segunda-feira da semana escolhida: numa quinta-feira,
    metade da faixa eram dias já passados, que nunca teriam horários.
    """

    def setUp(self):
        self.service = create_test_service(duration_minutes=60)
        self.today = timezone.localdate()

        # Todos os dias abertos, para a faixa não depender do dia em que os
        # testes correrem.
        for weekday in range(7):
            ensure_test_business_hour(
                weekday=weekday,
                start_time=time(8, 0),
                end_time=time(18, 0),
            )

    def strip_dates(self, query=""):
        response = self.client.get(
            reverse("appointments:public_visual_schedule") + query
        )

        return [day["date"] for day in response.context["week_days"]]

    def selected_date(self, query=""):
        response = self.client.get(
            reverse("appointments:public_visual_schedule") + query
        )

        return response.context["selected_date"]

    def test_strip_starts_today_by_default(self):
        datas = self.strip_dates()

        self.assertEqual(datas[0], self.today)
        self.assertEqual(len(datas), 7)

    def test_strip_never_contains_past_days(self):
        datas = self.strip_dates()

        self.assertTrue(all(data >= self.today for data in datas))

    def test_strip_crosses_into_the_next_week(self):
        # Sete dias seguidos a partir de hoje, independentemente do dia da
        # semana em que hoje calha.
        datas = self.strip_dates()

        self.assertEqual(datas[-1], self.today + timedelta(days=6))
        self.assertEqual(datas, [self.today + timedelta(days=i) for i in range(7)])

    def test_past_date_in_the_url_falls_back_to_today(self):
        passado = (self.today - timedelta(days=10)).isoformat()

        self.assertEqual(self.selected_date(f"?date={passado}"), self.today)
        self.assertEqual(self.strip_dates(f"?date={passado}")[0], self.today)

    def test_invalid_date_falls_back_to_today(self):
        self.assertEqual(self.selected_date("?date=nao-e-data"), self.today)

    def test_near_future_date_keeps_the_strip_anchored_on_today(self):
        # Escolher depois de amanhã não deve empurrar a faixa: o dia escolhido
        # já lá está.
        futuro = (self.today + timedelta(days=2)).isoformat()
        datas = self.strip_dates(f"?date={futuro}")

        self.assertEqual(datas[0], self.today)
        self.assertIn(self.today + timedelta(days=2), datas)

    def test_far_future_date_moves_the_strip_to_it(self):
        futuro = self.today + timedelta(days=30)
        datas = self.strip_dates(f"?date={futuro.isoformat()}")

        self.assertEqual(datas[0], futuro)
        self.assertEqual(datas[-1], futuro + timedelta(days=6))

    def test_selected_day_is_marked(self):
        futuro = (self.today + timedelta(days=3)).isoformat()
        response = self.client.get(
            reverse("appointments:public_visual_schedule") + f"?date={futuro}"
        )

        marcados = [
            day["date"] for day in response.context["week_days"] if day["is_selected"]
        ]

        self.assertEqual(len(marcados), 1)
        self.assertEqual(marcados[0].isoformat(), futuro)

    def test_the_strip_never_offers_a_past_day(self):
        # A proteção estava no `min` do campo de data, que era do browser e
        # saiu com o campo. Passou para onde já devia estar: o servidor, que
        # nunca constrói a faixa a começar antes de hoje.
        response = self.client.get(reverse("appointments:public_visual_schedule"))

        dias = [dia["date"] for dia in response.context["week_days"]]

        self.assertEqual(dias[0], self.today)

    def test_a_past_date_in_the_url_falls_back_to_today(self):
        # Sem o `min` do browser, um endereço escrito à mão é a via que sobra.
        passado = (self.today - timedelta(days=5)).isoformat()

        response = self.client.get(
            reverse("appointments:public_visual_schedule"), {"date": passado}
        )

        self.assertEqual(response.context["selected_date"], self.today)
