"""O mapa do rodapé.

O que aqui se guarda são três coisas que não dão erro quando estão erradas:

* que **a chave do servidor nunca vai parar ao HTML** — a das avaliações é
  lida aqui dentro e tem de lá ficar;
* que **sem configuração o rodapé continua a ter mapa**, em vez de um buraco;
* que o mapa continua **atrás do consentimento de cookies**, que é o que a
  política desta casa promete.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from appointments.tests.css_cascade import Stylesheet
from config.maps import MAPA_SIMPLES, endereco_do_mapa

CHAVE = "chave-de-mentira-do-embed"
LOCAL = "ChIJx6uujWD2Ig0RnOXzF6Fgzr"


class TheAddressTests(TestCase):
    @override_settings(GOOGLE_MAPS_EMBED_API_KEY=CHAVE, GOOGLE_PLACE_ID=LOCAL)
    def test_with_a_key_it_asks_for_the_place_card(self):
        # `/v1/place` é o que traz o cartão com o nome, as estrelas e o número
        # de avaliações. O endereço com `pb=` desenha só o pino.
        endereco = endereco_do_mapa("pt-pt")

        self.assertIn("/maps/embed/v1/place", endereco)
        self.assertIn(f"place_id:{LOCAL}", endereco)

    @override_settings(GOOGLE_MAPS_EMBED_API_KEY=CHAVE, GOOGLE_PLACE_ID=LOCAL)
    def test_the_place_id_keeps_its_colon(self):
        # `place_id%3A...` devia valer o mesmo que `place_id:...`. Não vale a
        # pena apostar nisso num endereço que só falha em produção.
        self.assertNotIn("%3A", endereco_do_mapa("pt-pt"))

    @override_settings(GOOGLE_MAPS_EMBED_API_KEY=CHAVE, GOOGLE_PLACE_ID=LOCAL)
    def test_the_language_comes_in_the_form_google_documents(self):
        self.assertIn("language=pt-PT", endereco_do_mapa("pt-pt"))
        self.assertIn("language=en", endereco_do_mapa("en"))

    @override_settings(GOOGLE_MAPS_EMBED_API_KEY="", GOOGLE_PLACE_ID=LOCAL)
    def test_without_a_key_the_plain_map_stays(self):
        # O rodapé não pode ficar sem mapa por causa de uma configuração que
        # ainda não foi posta.
        self.assertEqual(endereco_do_mapa("pt-pt"), MAPA_SIMPLES)

    @override_settings(GOOGLE_MAPS_EMBED_API_KEY=CHAVE, GOOGLE_PLACE_ID="")
    def test_a_key_without_a_place_is_not_enough(self):
        # Sem identificador do local não há cartão nenhum para pedir, e o
        # endereço sairia a apontar para lado nenhum.
        self.assertEqual(endereco_do_mapa("pt-pt"), MAPA_SIMPLES)


class WhatReachesThePageTests(TestCase):
    @override_settings(GOOGLE_MAPS_EMBED_API_KEY=CHAVE, GOOGLE_PLACE_ID=LOCAL)
    def test_the_home_page_carries_the_place_map(self):
        resposta = self.client.get(reverse("home"))

        self.assertContains(resposta, "/maps/embed/v1/place")

    @override_settings(GOOGLE_MAPS_EMBED_API_KEY="", GOOGLE_PLACE_ID=LOCAL)
    def test_and_the_plain_one_when_there_is_no_key(self):
        resposta = self.client.get(reverse("home"))

        self.assertContains(resposta, "maps/embed?pb=")

    @override_settings(GOOGLE_MAPS_EMBED_API_KEY=CHAVE, GOOGLE_PLACE_ID=LOCAL)
    def test_the_map_still_waits_for_cookie_consent(self):
        """O endereço vai em `data-cookie-src` e não em `src`.

        Escrito como `src`, o mapa carregava antes de alguém dizer que sim e a
        política de cookies desta casa passava a mentir. Trocar o endereço não
        pode ter trocado isso sem se dar por ela.
        """

        resposta = self.client.get(reverse("home"))
        html = resposta.content.decode()

        self.assertIn('data-cookie-src="https://www.google.com/maps', html)

        # `(?<![-\w])` de propósito: `data-cookie-src="..."` contém a
        # subcadeia `src="..."`, e uma procura simples dava-se por satisfeita
        # com o atributo certo — passando sempre, mesmo com um `src` a sério
        # ao lado.
        self.assertIsNone(
            re.search(r'(?<![-\w])src="https://www\.google\.com/maps', html),
            "o mapa tem um src directo e carrega antes do consentimento",
        )

    @override_settings(
        GOOGLE_MAPS_EMBED_API_KEY=CHAVE,
        GOOGLE_PLACE_ID=LOCAL,
        GOOGLE_PLACES_API_KEY="chave-do-servidor-que-nao-pode-sair",
    )
    def test_the_server_key_never_reaches_the_html(self):
        """A garantia que interessa mesmo.

        São duas chaves de propósito: a das avaliações é lida no servidor, a do
        mapa vai escrita no HTML. Confundi-las era publicar a primeira.
        """

        resposta = self.client.get(reverse("home"))

        self.assertNotContains(resposta, "chave-do-servidor-que-nao-pode-sair")
        self.assertContains(resposta, CHAVE)


class TheBoxAroundItTests(TestCase):
    """A caixa do mapa no rodapé.

    O endereço pede o cartão do estabelecimento — nome, estrelas e número de
    avaliações —, mas quem decide mostrá-lo é o Google, e num `iframe` baixo
    demais esconde-o. Pedir o cartão e não lhe dar altura era ficar na mesma
    com o pino de sempre.
    """

    #: Abaixo disto o Google deixa de desenhar o cartão.
    ALTURA_MINIMA = 300

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        caminho = Path(settings.BASE_DIR) / "static" / "css" / "public.css"
        cls.folha = Stylesheet(caminho.read_text(encoding="utf-8"))

    def altura(self, largura):
        return self.folha.resolve(".footer-map iframe", "height", largura)

    def test_the_map_is_tall_enough_for_the_card(self):
        for largura in (390, 1280):
            with self.subTest(largura=largura):
                altura = self.altura(largura)

                self.assertIsNotNone(altura, "o mapa ficou sem altura")
                self.assertGreaterEqual(
                    int(altura.removesuffix("px")),
                    self.ALTURA_MINIMA,
                )

    def test_the_box_matches_the_review_cards(self):
        # O mesmo fundo, a mesma linha e o mesmo raio dos cartões de
        # avaliação: solto no rodapé, o mapa lia-se como um remate da página.
        for propriedade in ("background", "border", "border-radius"):
            with self.subTest(propriedade=propriedade):
                self.assertEqual(
                    self.folha.resolve(".footer-map", propriedade, 1280),
                    self.folha.resolve(".review-card", propriedade, 1280),
                )

    def test_the_map_itself_keeps_rounded_corners(self):
        # A caixa passou a ter espaço à volta: sem raio próprio, o `iframe`
        # ficava de cantos direitos dentro de uma caixa redonda.
        self.assertIsNotNone(
            self.folha.resolve(".footer-map iframe", "border-radius", 1280)
        )
