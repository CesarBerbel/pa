import re

from django.conf import settings
from django.test import TestCase, override_settings
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
        #
        # A opacidade é lida depois de converter, e não pelos nomes dos canais:
        # um PNG de paleta não tem canal alfa nenhum e ainda assim pode guardar
        # transparência, num bloco `tRNS` que a lista de canais não mostra.
        for nome, _ in self.ICONES:
            with self.subTest(icone=nome):
                alfa = Image.open(IMG / nome).convert("RGBA").getchannel("A")

                self.assertEqual(alfa.getextrema(), (255, 255))

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
                alfa = Image.open(IMG / nome).convert("RGBA").getchannel("A")

                self.assertEqual(alfa.getextrema()[0], 0, "não há pixels vazios")

    def test_mark_is_square(self):
        imagem = Image.open(IMG / "logo-mark.png")

        self.assertEqual(imagem.width, imagem.height)

    def test_navbar_images_are_small_enough_to_ship_on_every_page(self):
        # O original tem meio megabyte para ser mostrado a 120 pixels.
        for nome in ["logo-mark.png", "logo-wordmark.png"]:
            with self.subTest(imagem=nome):
                kb = (IMG / nome).stat().st_size // 1024

                self.assertLess(kb, 200, f"{nome} tem {kb} KB")


class PublicImageTests(TestCase):
    """As imagens geradas por `scripts/optimize_public_images.py`.

    Os originais têm entre 380 KB e 1,4 MB e vivem em `assets/`, fora de
    `static/`. O que estes testes protegem é o limite: a página inicial já
    chegou a pedir 2,7 MB de PNG, e basta alguém voltar a apontar um template
    para um original para o problema regressar sem dar por isso.
    """

    # (ficheiro, KB no máximo)
    PUBLICAS = [
        ("hero-new.webp", 150),
        ("hero-photo.webp", 150),
        ("logo.webp", 60),
        ("logo-transparent.webp", 120),
    ]

    # Nenhum ficheiro servido a partir de `static/img/` deve passar disto. O
    # maior legítimo é o cartão social, com 115 KB desde que passou a paleta.
    TETO_KB = 130

    def test_public_images_exist_and_stay_small(self):
        for nome, teto in self.PUBLICAS:
            with self.subTest(imagem=nome):
                ficheiro = IMG / nome

                self.assertTrue(ficheiro.exists(), f"falta {nome}")
                self.assertEqual(Image.open(ficheiro).format, "WEBP")

                kb = ficheiro.stat().st_size // 1024
                self.assertLessEqual(kb, teto, f"{nome} tem {kb} KB")

    def test_social_card_is_readable_by_link_previews(self):
        # Os robôs do WhatsApp e do Facebook esperam PNG ou JPEG e ignoram
        # imagens grandes de mais — a anterior tinha 912 KB e não aparecia.
        cartao = IMG / "logo-og.png"
        imagem = Image.open(cartao)

        self.assertEqual(imagem.format, "PNG")
        self.assertEqual(imagem.size, (1200, 630))
        self.assertLess(cartao.stat().st_size, 600 * 1024)

        self.assertTrue(settings.SEO_DEFAULT_IMAGE_PATH.endswith("logo-og.png"))

    # A fotografia de fundo só existe no desenho `logo_top`. O `.env` desta
    # casa, o `.env.example` e a produção usam-no, mas a omissão do
    # `settings.py` é `classic` — e o CI não tem `.env` nenhum. O teste passava
    # em qualquer máquina com o ficheiro e rebentava no CI, num `.group(1)`
    # sobre um `None` que não dizia nada sobre a imagem.
    #
    # Fixar o desenho é o que faz o teste medir a imagem, e não a configuração
    # da máquina onde corre.
    @override_settings(HOME_HERO_LAYOUT="logo_top")
    def test_the_hero_uses_a_generated_image(self):
        # O fundo do hero é a imagem mais pesada da página inicial e a
        # primeira a ser pedida. Apontar o template ao original — que vive em
        # `assets/` com 163 KB — passava despercebido até alguém medir.
        html = self.client.get(reverse("home")).content.decode()
        fundo = re.search(r"--hero-bg: url\('([^']+)'\)", html)

        self.assertIsNotNone(fundo, "A página inicial não desenhou o fundo do hero.")
        self.assertIn("hero-new.webp", fundo.group(1))

        ficheiro = IMG / "hero-new.webp"

        self.assertEqual(Image.open(ficheiro).format, "WEBP")
        self.assertLessEqual(ficheiro.stat().st_size // 1024, self.TETO_KB)

    def test_no_source_image_is_served(self):
        # `static/` é o que vai para produção. Um original deixado aqui é
        # descarregado por quem visita o site, mesmo que nenhuma página o use.
        for ficheiro in IMG.iterdir():
            with self.subTest(imagem=ficheiro.name):
                kb = ficheiro.stat().st_size // 1024

                self.assertLessEqual(kb, self.TETO_KB, f"{ficheiro.name} tem {kb} KB")


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
        self.assertIn('alt="Priscila Arantes Pedicure Terapêutica"', self.navbar)

    def test_navbar_images_are_versioned(self):
        for nome in ["logo-mark.png", "logo-wordmark.png"]:
            with self.subTest(imagem=nome):
                self.assertRegex(self.navbar, rf"{re.escape(nome)}\?v=\d+")
