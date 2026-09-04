"""As linhas da agenda interna: altura e o que se pode fazer com uma seleção.

Duas coisas, e as duas falham em silêncio.

**A altura.** Quem manda na altura da linha não é o `min-height` da linha: é o
`.calendar-empty-slot` lá dentro, mais o `padding` do conteúdo. Baixar o
primeiro sozinho não mexe um pixel — e o ficheiro fica com um número que
descreve uma coisa que não acontece. Estes testes resolvem a cascata como o
browser a resolveria e olham para o valor que ganha, não para o que está
escrito.

**A seleção.** Escolher vários horários já servia para bloquear. Passa a servir
também para marcar, a partir do primeiro escolhido.
"""

from datetime import time, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.tests.css_cascade import Stylesheet
from appointments.tests.factories import create_test_service, ensure_test_business_hour

CSS = Path(settings.BASE_DIR) / "static" / "css" / "public.css"

# As três larguras que interessam: portátil, tablet e telemóvel. A folha
# redefine os mesmos seletores em camadas, e uma media query não acrescenta
# especificidade — uma regra escrita para o telemóvel pode perder para uma
# genérica escrita mais abaixo, sem aviso nenhum.
LARGURAS = (1440, 768, 390)


def em_pixeis(valor):
    return int(valor.replace("px", "").strip())


class TheRowsAreThinTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.css = Stylesheet(CSS.read_text(encoding="utf-8"))

    def test_a_row_is_not_tall(self):
        for largura in LARGURAS:
            with self.subTest(largura=largura):
                altura = self.css.resolve(".internal-slot-row", "min-height", largura)

                self.assertIsNotNone(altura, "ninguém define a altura da linha")
                self.assertLessEqual(em_pixeis(altura), 48)

    def test_the_free_slot_inside_it_is_thin_too(self):
        """É este que decide, e é o que se esquece.

        Com o slot livre a 48px e 24px de padding à volta, a linha media 72px
        por mais baixo que o `min-height` dela dissesse. Se um dia alguém
        engordar este, a linha volta a crescer sem que o número da linha mude.
        """

        for largura in LARGURAS:
            with self.subTest(largura=largura):
                altura = self.css.resolve(".calendar-empty-slot", "min-height", largura)

                self.assertIsNotNone(altura)
                self.assertLessEqual(em_pixeis(altura), 34)

    def test_the_whole_row_really_adds_up_to_something_thin(self):
        # A conta que o browser faz: o slot livre mais o padding de cima e de
        # baixo do conteúdo que o envolve.
        for largura in LARGURAS:
            with self.subTest(largura=largura):
                slot = em_pixeis(
                    self.css.resolve(".calendar-empty-slot", "min-height", largura)
                )
                padding = self.css.resolve(".internal-slot-content", "padding", largura)
                vertical = em_pixeis(padding.split()[0]) * 2

                self.assertLessEqual(slot + vertical, 48)


class WhatASelectionCanDoTests(TestCase):
    def setUp(self):
        self.utilizador = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )
        self.client.force_login(self.utilizador)

        self.dia = timezone.localdate() + timedelta(days=14)

        ensure_test_business_hour(
            weekday=self.dia.weekday(),
            start_time=time(9, 0),
            end_time=time(17, 0),
        )

        create_test_service(duration_minutes=60)

        self.html = self.client.get(
            reverse("appointments:visual_schedule"),
            {"date": self.dia.strftime("%Y-%m-%d")},
        ).content.decode()

    def test_the_rows_still_offer_the_checkbox_that_selects_them(self):
        self.assertIn("data-slot-checkbox", self.html)

    def test_the_selection_can_still_block(self):
        # O que já existia não pode ter-se perdido pelo caminho.
        self.assertIn('id="slot-blocking-form"', self.html)
        self.assertIn("Bloquear", self.html)

    def test_the_selection_can_now_book_as_well(self):
        self.assertIn("data-slot-book", self.html)

    def test_the_booking_link_carries_the_day_being_looked_at(self):
        # Sem a data, o formulário de marcação abria no dia de hoje — que é
        # quase nunca o dia que se está a ver.
        self.assertIn(f"date={self.dia.strftime('%Y-%m-%d')}", self.html)

    def test_the_booking_link_is_ready_for_a_start_time(self):
        """O endereço termina em `start_time=` e o JavaScript acrescenta a hora.

        Escrito assim, um erro no JavaScript deixa o botão a abrir o
        formulário no dia certo sem hora — que é aborrecido mas correto — em
        vez de o mandar para um endereço partido.
        """

        self.assertIn("start_time=", self.html)

    def test_each_free_row_keeps_its_own_button(self):
        # Marcar um horário solto continua a ser um clique, sem ter de o
        # escolher primeiro.
        self.assertIn("+ Marcar", self.html)
