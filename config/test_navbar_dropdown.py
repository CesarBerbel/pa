"""O fundo das listas pendentes da barra, no telemóvel.

Havia uma regra a tirar o fundo a **todas** as listas pendentes da barra
abaixo dos 992px. Escrita para as que ficam encaixadas dentro do menu
recolhido — onde o fundo da própria barra já as cobre — apanhava também a
"Área do cliente", que não fica encaixada: essa flutua por cima da página, e
sem fundo via-se a página através dela.

A diferença não é nossa, é do Bootstrap. A regra dele que encaixa uma lista
pendente dentro da barra recolhida é

    .navbar-expand-lg .navbar-nav .dropdown-menu { position: static }

e o `.navbar-nav` no meio é o que separa as duas: os menus internos estão
dentro de um, a "Área do cliente" está em `.navbar-side-actions`.

Testado pela cascata e não pelo texto do ficheiro: uma media query não
acrescenta especificidade, e uma regra genérica escrita mais abaixo anula-a
sem deixar sinal. Procurar a regra no ficheiro encontrá-la-ia à mesma —
apenas não ganharia.
"""

from pathlib import Path

from django.conf import settings
from django.test import TestCase

from appointments.tests.css_cascade import Stylesheet

CSS = Path(settings.BASE_DIR) / "static" / "css" / "public.css"

TELEMOVEL = 390
COMPUTADOR = 1280


class NavbarDropdownBackgroundTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.folha = Stylesheet(CSS.read_text(encoding="utf-8"))

    def test_the_client_area_keeps_its_background_on_a_phone(self):
        # É a que flutua por cima da página. Sem fundo, lê-se a página através
        # dela.
        self.assertEqual(
            self.folha.resolve(
                ".public-navbar .dropdown-menu", "background", TELEMOVEL
            ),
            "#ffffff",
        )

    def test_the_collapsed_menus_still_lose_theirs(self):
        # Essas ficam encaixadas dentro da barra, e o fundo da barra já as
        # cobre: com moldura e sombra pareciam um painel solto por cima do
        # menu em vez da continuação dele.
        self.assertEqual(
            self.folha.resolve(
                ".public-navbar .navbar-nav .dropdown-menu", "background", TELEMOVEL
            ),
            "transparent",
        )

    def test_on_a_computer_every_dropdown_is_a_panel(self):
        for seletor in (
            ".public-navbar .dropdown-menu",
            ".public-navbar .navbar-nav .dropdown-menu",
        ):
            with self.subTest(seletor=seletor):
                self.assertNotEqual(
                    self.folha.resolve(seletor, "background", COMPUTADOR),
                    "transparent",
                )

    def test_the_client_area_keeps_its_frame_too(self):
        # O fundo sozinho não chega: sem contorno nem sombra, um painel branco
        # por cima de uma página branca não tem onde acabar.
        self.assertNotEqual(
            self.folha.resolve(".public-navbar .dropdown-menu", "border", TELEMOVEL),
            "0",
        )
        self.assertNotEqual(
            self.folha.resolve(
                ".public-navbar .dropdown-menu", "box-shadow", TELEMOVEL
            ),
            "none",
        )
