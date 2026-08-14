import json
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from PIL import Image
from django.urls import reverse

from config.test_utils import ResetLanguageMixin


class ManifestTests(ResetLanguageMixin, TestCase):
    # O manifesto é o que permite instalar o site no ecrã inicial.

    def setUp(self):
        super().setUp()
        self.response = self.client.get("/manifest.webmanifest")
        self.manifest = json.loads(self.response.content)

    def test_is_served_from_the_site_root(self):
        self.assertEqual(self.response.status_code, 200)
        self.assertEqual(
            self.response.headers["Content-Type"], "application/manifest+json"
        )

    def test_declares_what_installation_requires(self):
        self.assertEqual(self.manifest["display"], "standalone")
        self.assertEqual(self.manifest["start_url"], "/")
        self.assertEqual(self.manifest["scope"], "/")
        self.assertTrue(self.manifest["name"])
        self.assertTrue(self.manifest["theme_color"])

    def test_has_the_icon_sizes_browsers_require(self):
        tamanhos = {icon["sizes"] for icon in self.manifest["icons"]}

        self.assertIn("192x192", tamanhos)
        self.assertIn("512x512", tamanhos)

    def test_has_a_maskable_icon(self):
        # Sem um ícone com zona de segurança, o Android corta o logo ao
        # recortá-lo em círculo.
        propositos = {icon["purpose"] for icon in self.manifest["icons"]}

        self.assertIn("maskable", propositos)

    def test_icon_files_exist_on_disk(self):
        # Verificado no disco e não por HTTP: o cliente de testes não serve
        # ficheiros estáticos, e um manifesto a apontar para um ícone
        # inexistente impede a instalação sem dar erro visível.
        for icon in self.manifest["icons"]:
            nome = Path(icon["src"]).name
            caminho = Path(settings.BASE_DIR) / "static" / "img" / nome

            with self.subTest(icon=nome):
                self.assertTrue(caminho.exists(), f"{nome} não existe")

    def test_icons_are_square_and_the_declared_size(self):
        for icon in self.manifest["icons"]:
            nome = Path(icon["src"]).name
            caminho = Path(settings.BASE_DIR) / "static" / "img" / nome
            esperado = int(icon["sizes"].split("x")[0])

            with self.subTest(icon=nome):
                with Image.open(caminho) as imagem:
                    self.assertEqual(imagem.size, (esperado, esperado))

    def test_shortcuts_point_to_real_pages(self):
        for shortcut in self.manifest["shortcuts"]:
            with self.subTest(url=shortcut["url"]):
                self.assertEqual(self.client.get(shortcut["url"]).status_code, 200)


class ServiceWorkerTests(ResetLanguageMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.response = self.client.get("/sw.js")
        self.source = self.response.content.decode()

    def test_is_served_from_the_root_so_its_scope_covers_the_site(self):
        # Servido a partir de /static/ o âmbito ficaria limitado a essa pasta.
        self.assertEqual(self.response.status_code, 200)
        self.assertIn("javascript", self.response.headers["Content-Type"])

    def test_is_not_cached_by_the_browser(self):
        self.assertEqual(self.response.headers["Cache-Control"], "no-cache")

    def test_navigations_go_to_the_network_first(self):
        # A regra que mais importa: uma agenda servida da cache mostraria
        # horários já ocupados.
        self.assertIn('request.mode === "navigate"', self.source)
        self.assertIn("fetch(request).catch", self.source)

    def test_falls_back_to_the_offline_page(self):
        self.assertIn(reverse("offline"), self.source)

    def test_only_static_files_are_cached(self):
        self.assertIn('url.pathname.startsWith("/static/")', self.source)

    def test_cache_name_changes_with_the_stylesheet(self):
        # Sem isto, um utilizador com a PWA instalada continuaria a ver os
        # estilos antigos depois de um deploy.
        self.assertRegex(self.source, r'CACHE_NAME = "pa-static-\d+"')


class OfflinePageTests(ResetLanguageMixin, TestCase):
    def test_renders(self):
        response = self.client.get(reverse("offline"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sem ligação")

    def test_is_not_indexable(self):
        response = self.client.get(reverse("offline"))

        self.assertContains(response, "noindex,nofollow")

    def test_is_translated(self):
        response = self.client.get("/en/offline/")

        self.assertContains(response, "No internet connection")


class PwaMarkupTests(ResetLanguageMixin, TestCase):
    def test_pages_link_the_manifest_and_register_the_worker(self):
        html = self.client.get(reverse("home")).content.decode()

        self.assertIn('rel="manifest"', html)
        self.assertIn('rel="apple-touch-icon"', html)
        self.assertIn("serviceWorker", html)
        self.assertIn("/sw.js", html)
