"""As âncoras da página inicial: onde caem e qual delas fica acesa.

O menu de cima não muda de página — leva a secções da mesma. Três coisas
podem estar erradas sem nunca dar erro: a âncora não ter onde cair, o salto
deixar o título por trás da barra `sticky`, e o item aceso não ser o da
secção que se está a ver.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from appointments.tests.css_cascade import Stylesheet
from config.test_utils import ResetLanguageMixin

CSS = Path(settings.BASE_DIR) / "static" / "css" / "public.css"

TELEMOVEL = 390
COMPUTADOR = 1280


class HomeAnchorTargetsTests(ResetLanguageMixin, TestCase):
    def pagina(self):
        return self.client.get(reverse("home")).content.decode()

    def test_every_anchor_lands_somewhere(self):
        """Nenhuma ligação para `#alguma-coisa` sem essa `alguma-coisa`.

        Um `href` para uma âncora que não existe não dá erro nenhum: o
        browser fica onde está, e quem clicou julga que o site não responde.
        """

        html = self.pagina()
        existentes = set(re.findall(r'\sid="([^"]+)"', html))

        # Sem `:` antes do cardinal: o que se procura são as âncoras desta
        # página, e não o fragmento de um endereço para fora do site.
        alvos = set(re.findall(r'href="[^":]*#([A-Za-z][^"]*)"', html))

        self.assertEqual(sorted(alvos - existentes), [])

    def test_the_menu_sections_are_all_there(self):
        # As do menu de cima, uma a uma: um `id` mudado no `home.html` sem
        # mudar o menu passaria despercebido no teste geral se a ligação
        # também desaparecesse.
        html = self.pagina()

        for ancora in ("servicos", "sobre", "marcacao", "contato"):
            with self.subTest(ancora=ancora):
                self.assertIn(f'href="/#{ancora}"', html)
                self.assertIn(f'id="{ancora}"', html)

    def test_tapping_a_section_closes_the_menu_on_a_phone(self):
        """No telemóvel o menu abre por cima da página.

        Sem nada que o feche, tocar numa secção rolava até lá por trás do
        menu aberto — chegava-se ao sítio certo a olhar para o menu.
        """

        html = self.pagina()

        self.assertIn("bootstrap.Collapse.getOrCreateInstance", html)


class StickyBarClearanceTests(TestCase):
    """A folga por baixo da barra que fica colada ao topo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.folha = Stylesheet(CSS.read_text(encoding="utf-8"))

    def test_a_section_keeps_its_distance_from_the_bar(self):
        # Sem isto o salto punha o título da secção por trás da barra.
        for largura in (TELEMOVEL, COMPUTADOR):
            with self.subTest(largura=largura):
                self.assertEqual(
                    self.folha.resolve("section[id]", "scroll-margin-top", largura),
                    "110px",
                )

    def test_the_footer_gets_the_same_clearance(self):
        # "Contacto" aponta para o rodapé, e o rodapé não é uma `section`.
        self.assertEqual(
            self.folha.resolve("footer[id]", "scroll-margin-top", COMPUTADOR),
            "110px",
        )

    def test_the_clearance_is_declared_once(self):
        """Uma regra só, e não duas a discordar.

        Havia duas — 96px a meio do ficheiro e 110px mais abaixo, ambas para
        `section[id]`. A de baixo ganhava, e a de cima ficava a dizer o
        contrário a quem lesse o ficheiro à procura do valor.
        """

        self.assertEqual(
            len(self.folha.declaring_rules("section[id]", "scroll-margin-top")),
            1,
        )
