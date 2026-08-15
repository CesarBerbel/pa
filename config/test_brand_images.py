import re

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from config.test_utils import ResetLanguageMixin

IMG = settings.BASE_DIR / "static" / "img"


class BrandImageTests(TestCase):
    """Os ficheiros gerados por `scripts/generate_pwa_icons.py`.

    O script não corre no deploy: o que vai para produção é o que está no
    repositório. Se um destes ficheiros desaparecer ou ficar com o tamanho
    errado, o sítio onde isso aparece é o ecrã inicial de um telemóvel.
    """

    ICONES = [
        ("icon-192.png", 192),
        ("icon-512.png", 512),
        ("icon-maskable-512.png", 512),
    ]

    def test_icons_exist_at_the_declared_size(self):
        for nome, lado in self.ICONES:
            with self.subTest(icone=nome):
                ficheiro = IMG / nome

                self.assertTrue(ficheiro.exists(), f"falta {nome}")
                self.assertEqual(Image.open(ficheiro).size, (lado, lado))

    def test_icons_are_opaque(self):
        # O Android e o iOS não contam com transparência nos ícones de
        # aplicação: desenhariam o que estivesse por trás.
        for nome, _ in self.ICONES:
            with self.subTest(icone=nome):
                self.assertNotIn("A", Image.open(IMG / nome).getbands())

    def test_maskable_icon_keeps_the_safe_area_clear(self):
        # O Android recorta o ícone; o desenho tem de caber num círculo com 80%
        # do lado. Se os cantos não forem fundo liso, algo ficou de fora.
        imagem = Image.open(IMG / "icon-maskable-512.png").convert("RGB")
        lado = imagem.width
        margem = int(lado * 0.06)

        cantos = [
            imagem.getpixel((margem, margem)),
            imagem.getpixel((lado - margem, margem)),
            imagem.getpixel((margem, lado - margem)),
            imagem.getpixel((lado - margem, lado - margem)),
        ]

        for canto in cantos:
            self.assertEqual(canto, cantos[0], "o desenho chega aos cantos")

    def test_navbar_images_keep_their_transparency(self):
        # Assentam sobre a barra, que é branco a 92% com desfoque: um fundo
        # opaco desenharia um retângulo visível.
        for nome in ["logo-mark.png", "logo-wordmark.png"]:
            with self.subTest(imagem=nome):
                imagem = Image.open(IMG / nome)

                self.assertIn("A", imagem.getbands())
                self.assertEqual(imagem.getchannel("A").getextrema()[0], 0)

    def test_mark_is_square(self):
        imagem = Image.open(IMG / "logo-mark.png")

        self.assertEqual(imagem.width, imagem.height)

    def test_navbar_images_are_small_enough_to_ship_on_every_page(self):
        # O original tem meio megabyte para ser mostrado a 120 pixels.
        for nome in ["logo-mark.png", "logo-wordmark.png"]:
            with self.subTest(imagem=nome):
                kb = (IMG / nome).stat().st_size // 1024

                self.assertLess(kb, 200, f"{nome} tem {kb} KB")


class NavbarLogoTests(ResetLanguageMixin, TestCase):
    def setUp(self):
        super().setUp()
        html = self.client.get(reverse("home")).content.decode()
        self.navbar = re.search(r"<nav\b.*?</nav>", html, re.S).group(0)

    def test_wide_screens_get_the_name(self):
        self.assertIn("logo-wordmark.png", self.navbar)
        self.assertIn('media="(min-width: 992px)"', self.navbar)

    def test_narrow_screens_get_the_compact_mark(self):
        # O <img> é o que fica quando nenhum <source> corresponde.
        self.assertRegex(self.navbar, r'<img[^>]*src="[^"]*logo-mark\.png')

    def test_only_one_of_them_is_downloaded(self):
        # Duas <img> com classes de visibilidade descarregariam as duas.
        self.assertIn("<picture>", self.navbar)

    def test_logo_still_links_home_and_has_a_text_alternative(self):
        self.assertIn(reverse("home"), self.navbar)
        self.assertIn('alt="Priscila Arantes PA"', self.navbar)

    def test_navbar_images_are_versioned(self):
        for nome in ["logo-mark.png", "logo-wordmark.png"]:
            with self.subTest(imagem=nome):
                self.assertRegex(self.navbar, rf"{re.escape(nome)}\?v=\d+")
