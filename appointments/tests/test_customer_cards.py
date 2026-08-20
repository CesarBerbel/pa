import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from appointments.models import Customer


class CustomerCardsTests(TestCase):
    """A lista de clientes como cartões, com o telefone a abrir conversa.

    Quem trabalha nesta lista faz sobretudo duas coisas: procurar alguém e
    falar com essa pessoa. O telefone era texto, e falar com alguém obrigava a
    copiar o número para outra aplicação.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.maria = Customer.objects.create(
            full_name="Maria Silva",
            phone="+351 910 000 000",
            email="maria@exemplo.pt",
        )

        self.client.force_login(self.user)
        self.url = reverse("appointments:customer_list")

    def cartao(self, cliente):
        """O HTML do cartão deste cliente, e só dele."""

        html = self.client.get(self.url).content.decode()

        # Do início deste cartão até ao início do seguinte, para as asserções
        # não apanharem por engano o que pertence ao cartão do lado. No último,
        # o limite é o fim do conteúdo: depois dele vem o botão flutuante de
        # WhatsApp do rodapé, que dava um falso positivo.
        inicio = html.rindex('class="customer-card"', 0, html.index(cliente.full_name))
        fim = html.find('class="customer-card"', inicio + 1)

        if fim == -1:
            fim = html.index("</main>", inicio)

        return html[inicio:fim]

    def test_the_list_is_made_of_cards(self):
        html = self.client.get(self.url).content.decode()

        self.assertIn('class="customer-card"', html)
        self.assertNotIn("<table", html)

    def test_the_phone_opens_the_conversation(self):
        cartao = self.cartao(self.maria)

        # O wa.me só aceita dígitos: o "+" e os espaços dão uma página de erro.
        self.assertIn("https://wa.me/351910000000", cartao)
        self.assertIn("bi-whatsapp", cartao)

    def test_the_phone_is_still_readable(self):
        # O link é para clicar, mas o número também é para ler em voz alta a
        # quem está do outro lado do balcão.
        self.assertIn("+351 910 000 000", self.cartao(self.maria))

    def test_a_number_that_cannot_open_a_conversation_promises_nothing(self):
        nuno = Customer.objects.create(full_name="Nuno Sem Número", phone="n/d")

        cartao = self.cartao(nuno)

        self.assertNotIn("wa.me", cartao)
        self.assertIn("n/d", cartao)

    def test_a_customer_without_email_says_so(self):
        ana = Customer.objects.create(full_name="Ana Sem Email", phone="+351920000000")

        cartao = self.cartao(ana)

        self.assertNotIn("mailto:", cartao)
        self.assertIn("Sem email", cartao)

    def test_the_email_is_a_link(self):
        self.assertIn("mailto:maria@exemplo.pt", self.cartao(self.maria))

    def test_the_actions_are_still_there(self):
        cartao = self.cartao(self.maria)

        for nome in ["patient_record", "customer_update", "customer_delete"]:
            with self.subTest(acao=nome):
                self.assertIn(
                    reverse(f"appointments:{nome}", args=[self.maria.pk]), cartao
                )

    def test_every_customer_gets_a_card(self):
        Customer.objects.create(full_name="Ana Costa", phone="+351920000000")

        html = self.client.get(self.url).content.decode()

        self.assertEqual(len(re.findall(r'class="customer-card"', html)), 2)

    def test_an_empty_list_still_explains_itself(self):
        Customer.objects.all().delete()

        self.assertContains(self.client.get(self.url), "Nenhum cliente registado")
