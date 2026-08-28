"""As mensagens do site: como fecham e quanto tempo ficam.

Duas coisas se testam aqui. Que há sempre uma forma de fechar à mão — porque o
fecho automático depende de JavaScript, e sem ele a mensagem tem de sair de
alguma maneira. E que todas ficam os mesmos cinco segundos — mas que só um
problema interrompe quem usa leitor de ecrã.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import reverse

from config.test_utils import ResetLanguageMixin


class Mensagem:
    """O mínimo que o template lê de uma mensagem: nível, etiquetas e texto."""

    ETIQUETAS = {
        20: "info",
        25: "success",
        30: "warning",
        40: "danger",
    }

    def __init__(self, level, texto):
        self.level = level
        self.tags = self.ETIQUETAS.get(level, "info")
        self.texto = texto

    def __str__(self):
        return self.texto


class MessagesCloseThemselvesTests(ResetLanguageMixin, TestCase):
    def setUp(self):
        super().setUp()

        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

    def pagina_com(self, nivel, texto="Uma mensagem."):
        """Desenha a página com uma mensagem daquele nível.

        Desenhada e não obtida de uma view a sério: o que está a ser testado é
        o que o template faz com o nível da mensagem, e produzir os quatro
        níveis por ações verdadeiras obrigava a encontrar — e a manter — uma
        ação de cada, o que amarrava este teste a meia dúzia de ecrãs que nada
        têm a ver com ele.
        """

        pedido = RequestFactory().get(reverse("dashboard"))
        pedido.user = self.user

        return render_to_string(
            "base.html",
            {"messages": [Mensagem(nivel, texto)]},
            request=pedido,
        )

    def test_every_message_can_be_closed_by_hand(self):
        # O fecho automático é JavaScript. Sem ele, a mensagem tem de sair de
        # alguma maneira.
        html = self.pagina_com(messages.SUCCESS)

        self.assertIn('data-bs-dismiss="alert"', html)
        self.assertIn('aria-label="Fechar"', html)

    def test_every_message_stays_for_five_seconds(self):
        """O mesmo tempo para todas.

        Houve uma versão com dois segundos para as confirmações, e dois
        segundos é o tempo de olhar para o lado e perder a frase.
        """

        for nivel in (
            messages.INFO,
            messages.SUCCESS,
            messages.WARNING,
            messages.ERROR,
        ):
            with self.subTest(nivel=nivel):
                self.assertIn('data-auto-dismiss="5000"', self.pagina_com(nivel))

    def test_a_problem_interrupts_a_screen_reader(self):
        # Dizer "alert" a tudo fazia de cada gravação bem sucedida uma
        # interrupção.
        self.assertIn('role="alert"', self.pagina_com(messages.ERROR))

    def test_a_confirmation_waits_for_the_next_pause(self):
        self.assertIn('role="status"', self.pagina_com(messages.SUCCESS))

    def test_the_script_that_closes_them_is_on_the_page(self):
        html = self.pagina_com(messages.INFO)

        self.assertIn("js/mensagens.js", html)

    def test_the_text_still_shows(self):
        # O botão de fechar entrou dentro do alerta: um `alert-dismissible`
        # mal montado engole o texto por baixo do X.
        html = self.pagina_com(messages.SUCCESS, "Marcação criada.")

        self.assertIn("Marcação criada.", html)
