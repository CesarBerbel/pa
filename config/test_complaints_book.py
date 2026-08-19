from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from config.test_utils import ResetLanguageMixin


class ComplaintsBookPageTests(ResetLanguageMixin, TestCase):
    """A página do Livro de Reclamações.

    O Decreto-Lei n.º 74/2017 obriga a divulgar o livro eletrónico de forma
    visível. O que cumpre a obrigação é o link para o portal oficial estar
    acessível a partir de qualquer página pública — por isso os testes cobrem
    tanto a página como a ligação no rodapé.
    """

    def test_page_is_served_in_portuguese(self):
        response = self.client.get(reverse("complaints_book"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Livro de Reclamações")
        self.assertContains(response, settings.COMPLAINTS_BOOK_URL)

    def test_page_is_served_in_english(self):
        response = self.client.get("/en/livro-de-reclamacoes/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Complaints Book")
        self.assertContains(response, "Open the Electronic Complaints Book")
        self.assertNotContains(response, "Abrir o Livro de Reclamações")

    def test_official_portal_link_opens_safely_in_a_new_tab(self):
        # target="_blank" sem rel="noopener" dá à página aberta acesso à
        # janela de origem; o link é externo, por isso os dois andam juntos.
        html = self.client.get(reverse("complaints_book")).content.decode()

        posicao = html.find(settings.COMPLAINTS_BOOK_URL)
        trecho = html[max(0, posicao - 200) : posicao + 200]

        self.assertIn('target="_blank"', trecho)
        self.assertIn('rel="noopener noreferrer"', trecho)

    def test_page_does_not_collect_complaints(self):
        # A reclamação é submetida no portal oficial. Um formulário aqui
        # guardaria dados pessoais sem base legal nem resposta associada.
        html = self.client.get(reverse("complaints_book")).content.decode()
        conteudo = html.split('<section class="legal-page">', 1)[1].split(
            "</section>", 1
        )[0]

        self.assertNotIn("<form", conteudo)
        self.assertNotIn("<input", conteudo)
        self.assertNotIn("<textarea", conteudo)

    def test_public_pages_link_to_the_complaints_book(self):
        html = self.client.get(reverse("home")).content.decode()

        self.assertIn(reverse("complaints_book"), html)

    def test_sitemap_lists_the_complaints_book(self):
        xml = self.client.get("/sitemap.xml").content.decode()

        self.assertIn(f"{settings.SITE_URL}{reverse('complaints_book')}", xml)

    def test_robots_does_not_block_the_page(self):
        robots = self.client.get("/robots.txt").content.decode()

        self.assertNotIn("livro-de-reclamacoes", robots)
