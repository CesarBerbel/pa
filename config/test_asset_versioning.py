import re

from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse

from config.templatetags.assets import asset_version, versioned_static
from config.test_utils import ResetLanguageMixin

VERSAO = re.compile(r"\?v=\d+$")


class AssetVersionTests(TestCase):
    """A versão que acompanha cada ficheiro estático.

    Sem ela, `{% static %}` devolve sempre o mesmo URL e tanto o browser como o
    service worker continuam a servir a cópia antiga depois de o ficheiro
    mudar: alterava-se o CSS e não acontecia nada.
    """

    def test_url_carries_a_version(self):
        self.assertRegex(versioned_static("css/public.css"), VERSAO)

    def test_version_comes_from_the_file(self):
        self.assertNotEqual(
            asset_version("css/public.css"),
            asset_version("js/passkeys.js"),
        )

    def test_a_missing_file_does_not_break_the_page(self):
        self.assertEqual(asset_version("css/nao-existe.css"), "0")

    def test_tag_is_available_to_templates(self):
        # A biblioteca está registada à mão nas definições, porque `config` não
        # é uma app instalada.
        rendered = Template(
            "{% load assets %}{% versioned_static 'css/public.css' %}"
        ).render(Context({}))

        self.assertRegex(rendered, VERSAO)


class VersionedAssetsInPagesTests(ResetLanguageMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.html = self.client.get(reverse("home")).content.decode()

    def test_stylesheet_link_is_versioned(self):
        self.assertRegex(self.html, r'href="/static/css/public\.css\?v=\d+"')

    def test_scripts_are_versioned(self):
        for src in re.findall(r'src="(/static/js/[^"]+)"', self.html):
            self.assertRegex(src, VERSAO, f"{src} devia trazer versão")


class ServiceWorkerPrecacheTests(ResetLanguageMixin, TestCase):
    """O que o service worker guarda tem de ser o que as páginas pedem."""

    def test_precached_stylesheet_matches_the_one_pages_request(self):
        # Guardar `/static/css/public.css` enquanto a página pede
        # `...?v=123` enche a cache com uma entrada que nunca é usada, e a
        # página fica sem estilos quando não há rede.
        pagina = self.client.get(reverse("home")).content.decode()
        worker = self.client.get("/sw.js").content.decode()

        pedido = re.search(r'href="(/static/css/public\.css[^"]*)"', pagina).group(1)

        self.assertIn(f'"{pedido}"', worker)
