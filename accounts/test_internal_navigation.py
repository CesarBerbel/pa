import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from config.test_utils import ResetLanguageMixin

# Só o que está dentro do <nav>, para não confundir com ligações do corpo da
# página nem do rodapé.
NAVBAR = re.compile(r"<nav\b.*?</nav>", re.S)


class InternalNavigationTests(ResetLanguageMixin, TestCase):
    """O menu de quem trabalha na clínica.

    O dia a dia — agenda, clientes, marcações — fica à vista. O que só se mexe
    de vez em quando vive em Configurações.
    """

    DIA_A_DIA = [
        ("appointments:visual_schedule", "Agenda"),
        ("appointments:customer_list", "Clientes"),
        ("appointments:appointment_list", "Marcações"),
    ]

    CONFIGURACOES = [
        ("appointments:reminder_diagnostics", "Diagnóstico"),
        ("appointments:business_hour_list", "Horas trabalhadas"),
        ("appointments:schedule_block_list", "Bloqueios"),
        ("appointments:service_list", "Serviços"),
        ("accounts:passkey_devices", "Entrar com digital"),
    ]

    def setUp(self):
        super().setUp()

        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.client.force_login(self.user)
        self.navbar = self.barra()

    def barra(self):
        html = self.client.get(reverse("dashboard")).content.decode()
        return NAVBAR.search(html).group(0)

    def menu_de_configuracoes(self):
        inicio = self.navbar.index('id="internalSettingsMenu"')
        return self.navbar[inicio : self.navbar.index("</ul>", inicio)]

    def test_daily_work_is_visible_without_opening_a_menu(self):
        fora_do_dropdown = self.navbar[: self.navbar.index("dropdown-menu")]

        for nome, rotulo in self.DIA_A_DIA:
            self.assertIn(reverse(nome), fora_do_dropdown)
            self.assertIn(rotulo, fora_do_dropdown)

    def test_schedule_link_drops_the_word_visual(self):
        self.assertNotIn("Agenda visual", self.navbar)
        self.assertIn(">Agenda</a>", self.navbar)

    def test_settings_menu_holds_the_occasional_pages(self):
        menu = self.menu_de_configuracoes()

        for nome, rotulo in self.CONFIGURACOES:
            self.assertIn(reverse(nome), menu, f"{rotulo} devia estar em Configurações")
            self.assertIn(rotulo, menu)

    def test_settings_pages_are_not_also_loose_in_the_bar(self):
        # Duplicar as ligações anularia o efeito de as arrumar.
        fora_do_dropdown = self.navbar[: self.navbar.index("dropdown-menu")]

        for nome, _ in self.CONFIGURACOES:
            self.assertNotIn(reverse(nome), fora_do_dropdown)

    def test_the_menu_can_be_opened(self):
        # Sem isto o Bootstrap não abre nada e as páginas ficam inalcançáveis.
        self.assertIn('data-bs-toggle="dropdown"', self.navbar)

    def test_no_language_selector_in_the_internal_area(self):
        # A área interna existe só em português.
        self.assertNotIn("language-switcher", self.navbar)
        self.assertNotIn(reverse("set_language"), self.navbar)

    def test_signing_out_is_still_available(self):
        self.assertIn(reverse("accounts:logout"), self.navbar)

    def test_every_settings_page_answers(self):
        for nome, rotulo in self.CONFIGURACOES:
            with self.subTest(pagina=rotulo):
                self.assertEqual(self.client.get(reverse(nome)).status_code, 200)


class PublicNavigationTests(ResetLanguageMixin, TestCase):
    """O que muda na área interna não pode mexer com o site público."""

    def barra(self):
        html = self.client.get(reverse("home")).content.decode()
        return NAVBAR.search(html).group(0)

    def test_visitors_keep_the_language_selector(self):
        self.assertIn("language-switcher", self.barra())

    def test_customers_keep_the_language_selector(self):
        customer = get_user_model().objects.create_user(
            email="cliente@example.com",
            password="StrongPassword123",
            full_name="Cliente",
        )

        self.client.force_login(customer)

        self.assertIn("language-switcher", self.barra())

    def test_customers_reach_their_devices_page(self):
        customer = get_user_model().objects.create_user(
            email="cliente@example.com",
            password="StrongPassword123",
            full_name="Cliente",
        )

        self.client.force_login(customer)

        self.assertIn(reverse("accounts:passkey_devices"), self.barra())

    def test_visitors_do_not_see_internal_pages(self):
        barra = self.barra()

        self.assertNotIn("internalSettingsMenu", barra)
        self.assertNotIn(reverse("appointments:service_list"), barra)
