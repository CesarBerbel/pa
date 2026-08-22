import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from config import google_reviews
from config.test_utils import ResetLanguageMixin

LIGADO = {
    "GOOGLE_PLACES_API_KEY": "chave-de-teste",
    "GOOGLE_PLACE_ID": "ChIJexemplo",
}

RESPOSTA = {
    "rating": 4.8,
    "userRatingCount": 37,
    "googleMapsUri": "https://maps.google.com/?cid=1",
    "reviews": [
        {
            "rating": 5,
            "text": {"text": "Atendimento impecável.\nVoltarei."},
            "relativePublishTimeDescription": "há 2 semanas",
            "googleMapsUri": "https://maps.google.com/review/1",
            "authorAttribution": {
                "displayName": "Maria Silva",
                "uri": "https://maps.google.com/contrib/1",
                "photoUri": "https://lh3.googleusercontent.com/foto1",
            },
        },
        {
            "rating": 4,
            "text": {"text": "Muito profissional."},
            "relativePublishTimeDescription": "há 1 mês",
            "authorAttribution": {"displayName": "Ana Costa"},
        },
        {
            # Só estrelas, sem texto: conta para a média, mas num cartão
            # ficaria vazia.
            "rating": 5,
            "relativePublishTimeDescription": "há 3 meses",
            "authorAttribution": {"displayName": "Rita Sem Texto"},
        },
    ],
}


def resposta(conteudo):
    """Imita o que o `urlopen` devolve: um ficheiro que se lê uma vez."""

    corpo = BytesIO(json.dumps(conteudo).encode("utf-8"))
    corpo.__enter__ = lambda: corpo
    corpo.__exit__ = lambda *args: None

    return corpo


@override_settings(**LIGADO)
class GoogleReviewsServiceTests(TestCase):
    """A leitura das avaliações, e o que fazer quando ela falha."""

    def setUp(self):
        cache.clear()

    def test_it_reads_the_rating_and_the_reviews(self):
        with patch.object(google_reviews, "urlopen", return_value=resposta(RESPOSTA)):
            resultado = google_reviews.get_reviews()

        self.assertEqual(resultado["rating"], 4.8)
        self.assertEqual(resultado["total"], 37)
        self.assertEqual(len(resultado["reviews"]), 2)

    def test_a_review_without_text_is_left_out(self):
        with patch.object(google_reviews, "urlopen", return_value=resposta(RESPOSTA)):
            resultado = google_reviews.get_reviews()

        autores = [avaliacao["author"] for avaliacao in resultado["reviews"]]

        self.assertNotIn("Rita Sem Texto", autores)

    def test_the_attribution_comes_along(self):
        # Os termos da Google obrigam a dizer quem escreveu e a ligar para a
        # avaliação. Sem isto, o cartão não poderia ser mostrado.
        with patch.object(google_reviews, "urlopen", return_value=resposta(RESPOSTA)):
            primeira = google_reviews.get_reviews()["reviews"][0]

        self.assertEqual(primeira["author"], "Maria Silva")
        self.assertTrue(primeira["photo"])
        self.assertTrue(primeira["url"])

    def test_the_text_is_not_touched(self):
        # Alterar ou cortar o texto é proibido, e mudaria o que a pessoa disse.
        with patch.object(google_reviews, "urlopen", return_value=resposta(RESPOSTA)):
            primeira = google_reviews.get_reviews()["reviews"][0]

        self.assertEqual(primeira["text"], "Atendimento impecável.\nVoltarei.")

    def test_the_average_is_rounded_to_whole_stars(self):
        # 4,8 são cinco estrelas cheias, não quatro.
        with patch.object(google_reviews, "urlopen", return_value=resposta(RESPOSTA)):
            resultado = google_reviews.get_reviews()

        self.assertEqual(resultado["stars"], 5)
        self.assertEqual(resultado["empty_stars"], 0)

    def test_it_never_asks_for_more_than_the_limit(self):
        with override_settings(GOOGLE_REVIEWS_LIMIT=1):
            with patch.object(
                google_reviews, "urlopen", return_value=resposta(RESPOSTA)
            ):
                resultado = google_reviews.get_reviews()

        self.assertEqual(len(resultado["reviews"]), 1)

    def test_the_api_is_asked_once_per_cache_window(self):
        # A página inicial não pode ir à Google a cada visita: é uma chamada
        # externa no caminho do pedido, e a API é paga por chamada.
        with patch.object(
            google_reviews, "urlopen", return_value=resposta(RESPOSTA)
        ) as chamada:
            google_reviews.get_reviews()
            google_reviews.get_reviews()

        self.assertEqual(chamada.call_count, 1)

    def test_a_failure_gives_nothing_and_says_why_in_the_log(self):
        erro = HTTPError(
            url="https://places.googleapis.com/v1/places/X",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=BytesIO(
                json.dumps(
                    {"error": {"message": "Places API has not been used"}}
                ).encode("utf-8")
            ),
        )

        with self.assertLogs("config.google_reviews", level="WARNING") as registo:
            with patch.object(google_reviews, "urlopen", side_effect=erro):
                self.assertIsNone(google_reviews.get_reviews())

        self.assertIn("Places API has not been used", "\n".join(registo.output))

    def test_a_failure_is_not_remembered_for_long(self):
        # Guardar o vazio durante seis horas escondia a secção por causa de um
        # soluço de rede.
        with patch.object(google_reviews, "urlopen", side_effect=OSError("sem rede")):
            google_reviews.get_reviews()

        self.assertEqual(cache.get(google_reviews.CACHE_KEY), {})

    def test_the_request_asks_for_portuguese(self):
        with patch.object(
            google_reviews, "urlopen", return_value=resposta(RESPOSTA)
        ) as chamada:
            google_reviews.get_reviews()

        pedido = chamada.call_args[0][0]

        self.assertEqual(pedido.get_header("Accept-language"), "pt-PT")
        self.assertEqual(pedido.get_header("X-goog-api-key"), "chave-de-teste")


class GoogleReviewsAreOptionalTests(TestCase):
    def setUp(self):
        cache.clear()

    @override_settings(GOOGLE_PLACES_API_KEY="", GOOGLE_PLACE_ID="")
    def test_without_keys_nothing_is_requested(self):
        with patch.object(google_reviews, "urlopen") as chamada:
            self.assertIsNone(google_reviews.get_reviews())

        chamada.assert_not_called()

    @override_settings(GOOGLE_PLACES_API_KEY="chave", GOOGLE_PLACE_ID="")
    def test_half_configured_is_the_same_as_not_configured(self):
        # Uma chave sem local não dá para pedir nada, e pedir daria um erro
        # por visita.
        with patch.object(google_reviews, "urlopen") as chamada:
            self.assertIsNone(google_reviews.get_reviews())

        chamada.assert_not_called()


class HomepageReviewsSectionTests(ResetLanguageMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    @override_settings(**LIGADO)
    def test_the_section_shows_the_reviews(self):
        with patch.object(google_reviews, "urlopen", return_value=resposta(RESPOSTA)):
            html = self.client.get(reverse("home")).content.decode()

        self.assertIn('id="avaliacoes"', html)
        self.assertIn("Maria Silva", html)
        self.assertIn("Atendimento impecável", html)
        self.assertIn("37", html)

    @override_settings(**LIGADO)
    def test_the_page_survives_google_being_down(self):
        with patch.object(google_reviews, "urlopen", side_effect=OSError("sem rede")):
            resposta_http = self.client.get(reverse("home"))

        self.assertEqual(resposta_http.status_code, 200)
        self.assertNotIn('id="avaliacoes"', resposta_http.content.decode())

    @override_settings(GOOGLE_PLACES_API_KEY="", GOOGLE_PLACE_ID="")
    def test_without_keys_the_section_simply_is_not_there(self):
        html = self.client.get(reverse("home")).content.decode()

        self.assertNotIn('id="avaliacoes"', html)


class SalonModalIsGoneTests(ResetLanguageMixin, TestCase):
    """O aviso do novo espaço, que abria a cada entrada na página inicial."""

    def test_the_homepage_no_longer_interrupts_anyone(self):
        html = self.client.get(reverse("home")).content.decode()

        self.assertNotIn("salon-modal", html)

    def test_the_address_is_still_reachable(self):
        # O modal saiu; a morada não. Quem a procura continua a encontrá-la no
        # rodapé, que é onde se procura uma morada.
        self.assertContains(self.client.get(reverse("home")), "Sá da Bandeira")
