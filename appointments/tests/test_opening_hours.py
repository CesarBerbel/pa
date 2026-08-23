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

    def test_days_in_a_row_with_the_same_hours_become_one_line(self):
        # Cinco linhas iguais não é como se escreve um horário.
        for weekday in range(5):
            self.dia(weekday)

        linhas = opening_hours()

        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["periods"], ["09:00 — 19:00"])

    def test_a_different_day_breaks_the_group(self):
        for weekday in range(5):
            self.dia(weekday)

        self.dia(5, inicio=9, fim=13)

        linhas = opening_hours()

        self.assertEqual(len(linhas), 2)
        self.assertEqual(linhas[1]["periods"], ["09:00 — 13:00"])

    def test_the_lunch_break_shows_as_two_periods(self):
        self.dia(0, inicio=9, fim=13, tarde=(14, 19))

        self.assertEqual(
            opening_hours()[0]["periods"], ["09:00 — 13:00", "14:00 — 19:00"]
        )

    def test_a_closed_day_is_not_listed(self):
        self.dia(0)
        self.dia(6, is_active=False)

        self.assertEqual(len(opening_hours()), 1)

    def test_nothing_configured_gives_nothing(self):
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
