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

    Está agrupado por assunto: o dia a dia à vista, e o resto em dois menus
    que dizem o que são — Site e Configurações. O que este ficheiro guarda não
    é a arrumação em si, é o que ela não pode custar: o trabalho diário a um
    clique, nenhuma ligação repetida, e nenhuma página do sistema sem forma de
    lá chegar.
    """

    # Um clique, sem abrir menu nenhum. A agenda abre no dia — é a vista de
    # trabalho, e é dela que se salta para a semana.
    DIA_A_DIA = [
        ("appointments:visual_schedule", "Agenda"),
        ("appointments:appointment_list", "Marcações"),
        ("appointments:customer_list", "Clientes"),
        ("appointments:patient_record_index", "Anamnese"),
    ]

    GRUPOS = {
        "internalSiteMenu": [
            "appointments:service_list",
            "appointments:before_after_list",
            "appointments:schedule_block_list",
        ],
        # As mensagens vivem aqui dentro, num grupo com nome: mexe-se-lhes de
        # tempos a tempos, não todos os dias.
        "internalSettingsMenu": [
            "appointments:scheduling_setting",
            "appointments:business_hour_list",
            "notifications:messaging_setting",
            "notifications:email_template_list",
            "notifications:service_followup_list",
            "notifications:whatsapp_setting_list",
            "notifications:whatsapp_connection",
            "appointments:appointment_audit",
            "appointments:schedule_diagnostics",
        ],
    }

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

    def menu(self, identificador):
        """Só o conteúdo de um dos menus."""

        inicio = self.navbar.index(f'aria-labelledby="{identificador}"')

        return self.navbar[inicio : self.navbar.index("</ul>", inicio)]

    def ligacoes_de_topo(self):
        """As ligações da barra que não estão dentro de menu nenhum.

        Não serve fatiar a barra até ao primeiro menu: o primeiro item já é um
        menu, e isso cortaria fora tudo o que vem a seguir. Retiram-se os
        menus um a um, e o que sobra é o que se vê sem abrir nada.
        """

        sobra = self.navbar

        for identificador in self.GRUPOS:
            inicio = sobra.index(f'aria-labelledby="{identificador}"')
            fim = sobra.index("</ul>", inicio) + len("</ul>")
            sobra = sobra[:inicio] + sobra[fim:]

        return re.findall(r'<a class="nav-link[^"]*"[^>]*href="([^"]+)"', sobra)

    def test_daily_work_is_one_click_away(self):
        # É o que não pode custar nada à arrumação: agenda, marcações e
        # clientes sem abrir menu nenhum.
        topo = self.ligacoes_de_topo()

        for nome, rotulo in self.DIA_A_DIA:
            with self.subTest(pagina=rotulo):
                self.assertIn(reverse(nome), topo)
                self.assertIn(rotulo, self.navbar)

    def test_the_week_is_reachable_from_the_daily_agenda(self):
        # A semana saiu do menu. Se também não estivesse na página do dia,
        # ficava sem forma de lá chegar.
        html = self.client.get(reverse("appointments:visual_schedule")).content.decode()

        self.assertIn(reverse("appointments:weekly_schedule"), html)

    def test_the_schedule_is_not_called_visual(self):
        self.assertNotIn("Agenda visual", self.navbar)

    def test_the_messages_live_inside_the_settings_menu(self):
        # Eram um menu de topo. Passaram para dentro das configurações, com um
        # cabeçalho a dizer o que são — sem ele, "Modelos de email" ficava ao
        # lado de "Horas trabalhadas" sem se perceber porquê.
        self.assertNotIn("internalMessagesMenu", self.navbar)
        self.assertIn("Mensagens", self.menu("internalSettingsMenu"))

    def test_the_anamnesis_is_one_click_away_for_who_may_read_it(self):
        self.assertIn(
            reverse("appointments:patient_record_index"), self.ligacoes_de_topo()
        )

    def test_who_has_no_clinical_access_does_not_see_it(self):
        # A ficha tem dados de saúde: quem não lhe pode chegar não precisa de
        # ver a porta.
        utilizador = get_user_model().objects.create_user(
            email="rececao@example.com",
            password="StrongPassword123",
            full_name="Receção",
            is_internal_staff=True,
            can_access_clinical_data=False,
        )

        self.client.force_login(utilizador)

        self.assertNotIn(
            reverse("appointments:patient_record_index"), self.barra()
        )

    def test_each_menu_holds_what_belongs_to_it(self):
        for identificador, paginas in self.GRUPOS.items():
            conteudo = self.menu(identificador)

            for nome in paginas:
                with self.subTest(menu=identificador, pagina=nome):
                    self.assertIn(reverse(nome), conteudo)

    def test_no_page_sits_in_two_menus(self):
        # Duplicar as ligações anularia o efeito de as arrumar.
        vistas = {}

        for identificador in self.GRUPOS:
            for href in re.findall(
                r'class="dropdown-item"[^>]*href="([^"]+)"', self.menu(identificador)
            ):
                self.assertNotIn(
                    href,
                    vistas,
                    f"{href} está em {identificador} e em {vistas.get(href)}",
                )
                vistas[href] = identificador

    def test_every_page_in_the_menu_answers(self):
        # Um menu que leva a um erro é pior do que não ter o item lá.
        for identificador, paginas in self.GRUPOS.items():
            for nome in paginas:
                with self.subTest(pagina=nome):
                    self.assertEqual(self.client.get(reverse(nome)).status_code, 200)

    def test_the_pages_that_had_no_menu_now_have_one(self):
        # O diagnóstico não era acessível de lado nenhum, e a ligação do
        # WhatsApp — onde se lê o QR code quando a ligação cai — só se
        # alcançava a partir de outras páginas de WhatsApp.
        for nome in [
            "appointments:schedule_diagnostics",
            "notifications:whatsapp_connection",
        ]:
            with self.subTest(pagina=nome):
                self.assertIn(reverse(nome), self.navbar)

    def test_the_menus_can_be_opened(self):
        # Sem isto o Bootstrap não abre nada e as páginas ficam inalcançáveis.
        for identificador in self.GRUPOS:
            with self.subTest(menu=identificador):
                self.assertIn(identificador, self.navbar)

        self.assertIn('data-bs-toggle="dropdown"', self.navbar)

    def test_signing_in_with_a_passkey_is_in_the_account_menu(self):
        # É da conta de quem usa o sistema, não uma configuração da clínica.
        self.assertIn(reverse("accounts:passkey_devices"), self.navbar)

        for identificador in self.GRUPOS:
            self.assertNotIn(
                reverse("accounts:passkey_devices"), self.menu(identificador)
            )

    def test_no_language_selector_in_the_internal_area(self):
        # A área interna existe só em português.
        self.assertNotIn("language-switcher", self.navbar)
        self.assertNotIn(reverse("set_language"), self.navbar)

    def test_signing_out_is_still_available(self):
        self.assertIn(reverse("accounts:logout"), self.navbar)


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
