"""O horário de funcionamento, agora com uma só fonte.

Estava escrito em três sítios — o rodapé, os dados estruturados e os
`BusinessHour` — e nada garantia que dissessem o mesmo.
"""

import json
from datetime import time

from django.test import TestCase
from django.urls import reverse

from appointments.models import BusinessHour
from appointments.opening_hours import opening_hours, structured_data_specification
from config.test_utils import ResetLanguageMixin


class OpeningHoursReadingTests(TestCase):
    def setUp(self):
        # As migrações semeiam a semana toda; cada teste diz o seu horário.
        BusinessHour.objects.all().delete()

    def dia(self, weekday, inicio=9, fim=19, tarde=None, **extra):
        campos = {
            "weekday": weekday,
            "start_time": time(inicio),
            "end_time": time(fim),
            "second_start_time": time(tarde[0]) if tarde else None,
            "second_end_time": time(tarde[1]) if tarde else None,
        }
        campos.update(extra)

        return BusinessHour.objects.create(**campos)

    def test_the_whole_week_is_listed(self):
        # Sete linhas, aberto ou fechado: é assim que se procura um dia sem
        # ter de contar os que faltam.
        for weekday in range(5):
            self.dia(weekday)

        linhas = opening_hours()

        self.assertEqual(len(linhas), 7)
        self.assertEqual(linhas[0]["periods"], ["09:00 — 19:00"])

    def test_each_day_carries_its_own_hours(self):
        self.dia(0)
        self.dia(5, inicio=9, fim=13)

        linhas = opening_hours()

        self.assertEqual(linhas[0]["periods"], ["09:00 — 19:00"])
        self.assertEqual(linhas[5]["periods"], ["09:00 — 13:00"])

    def test_the_lunch_break_shows_as_two_periods(self):
        self.dia(0, inicio=9, fim=13, tarde=(14, 19))

        self.assertEqual(
            opening_hours()[0]["periods"], ["09:00 — 13:00", "14:00 — 19:00"]
        )

    def test_two_periods_that_touch_become_one(self):
        # É como o sábado está gravado: a manhã acaba à hora a que a tarde
        # começa. Escrito como dois períodos lê-se como um lapso.
        self.dia(5, inicio=8, fim=12, tarde=(12, 14))

        self.assertEqual(opening_hours()[5]["periods"], ["08:00 — 14:00"])

    def test_a_closed_day_is_listed_as_closed(self):
        # Estava de fora, e quem procurasse o domingo tinha de o concluir
        # pela ausência.
        self.dia(0)
        self.dia(6, is_active=False)

        linhas = opening_hours()

        self.assertFalse(linhas[0]["closed"])
        self.assertTrue(linhas[6]["closed"])
        self.assertEqual(linhas[6]["periods"], [])

    def test_a_day_never_configured_is_closed_too(self):
        self.dia(0)

        self.assertTrue(opening_hours()[3]["closed"])

    def test_the_day_names_drop_the_repeated_suffix(self):
        # "Segunda-feira" sete vezes é uma coluna de sufixos iguais.
        self.dia(0)

        nomes = [linha["day"] for linha in opening_hours()]

        self.assertEqual(nomes[0], "Segunda")
        self.assertEqual(nomes[5], "Sábado")
        self.assertEqual(nomes[6], "Domingo")

    def test_nothing_configured_gives_nothing(self):
        # Sem um único dia aberto não é um horário todo fechado: é um horário
        # que ainda não foi escrito, e o rodapé não o mostra.
        self.assertEqual(opening_hours(), [])


class OpeningHoursStructuredDataTests(TestCase):
    def setUp(self):
        BusinessHour.objects.all().delete()

    def test_google_gets_the_hours_the_professional_configured(self):
        for weekday in range(5):
            BusinessHour.objects.create(
                weekday=weekday,
                start_time=time(9),
                end_time=time(13),
                second_start_time=time(14),
                second_end_time=time(19),
            )

        especificacao = structured_data_specification()

        self.assertEqual(len(especificacao), 2)
        self.assertEqual(
            especificacao[0]["dayOfWeek"],
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        )
        self.assertEqual(especificacao[0]["opens"], "09:00")
        self.assertEqual(especificacao[1]["closes"], "19:00")

    def test_a_day_without_a_break_is_one_specification(self):
        # O mesmo que o rodapé mostra: dois períodos que se tocam são um dia
        # corrido, e ao Google anuncia-se o que se atende.
        BusinessHour.objects.create(
            weekday=5,
            start_time=time(8),
            end_time=time(12),
            second_start_time=time(12),
            second_end_time=time(14),
        )

        especificacao = structured_data_specification()

        self.assertEqual(len(especificacao), 1)
        self.assertEqual(especificacao[0]["opens"], "08:00")
        self.assertEqual(especificacao[0]["closes"], "14:00")

    def test_without_any_day_configured_it_falls_back_to_the_settings(self):
        # Uma ficha sem horário nenhum é pior do que uma com um genérico.
        self.assertIsNone(structured_data_specification())

        html = self.client.get(reverse("home")).content.decode()
        dados = json.loads(
            html.split('type="application/ld+json">')[1].split("</script>")[0]
        )

        self.assertTrue(dados["openingHoursSpecification"])


class OpeningHoursInTheFooterTests(ResetLanguageMixin, TestCase):
    def setUp(self):
        super().setUp()
        BusinessHour.objects.all().delete()

    def rodape(self):
        html = self.client.get(reverse("home")).content.decode()

        return html[html.index("<footer") : html.index("</footer>")]

    def test_the_footer_shows_what_the_professional_configured(self):
        # Estava escrito à mão e ficava a mentir a cada mudança de horário.
        BusinessHour.objects.create(
            weekday=0, start_time=time(10), end_time=time(16, 30)
        )

        rodape = self.rodape()

        self.assertIn("10:00 — 16:30", rodape)
        self.assertNotIn("Todos os dias: 08:00", rodape)

    def test_without_hours_the_block_is_not_there(self):
        self.assertNotIn("footer-hours", self.rodape())

    def test_the_footer_lists_the_seven_days(self):
        for weekday in range(6):
            BusinessHour.objects.create(
                weekday=weekday, start_time=time(8), end_time=time(18)
            )

        rodape = self.rodape()

        for dia in ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"):
            with self.subTest(dia=dia):
                self.assertIn(dia, rodape)

    def test_the_day_nobody_configured_says_it_is_closed(self):
        BusinessHour.objects.create(
            weekday=0, start_time=time(8), end_time=time(18)
        )

        self.assertIn("Encerrado", self.rodape())
