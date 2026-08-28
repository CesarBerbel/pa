"""As avaliações do Google do estabelecimento, para mostrar no site.

Vêm da Places API. É preciso saber três coisas antes de mexer aqui:

* **São no máximo cinco.** A API devolve até cinco avaliações, escolhidas por
  ela, e não há forma de pedir mais nem de paginar. Uma secção que prometa
  "todas as avaliações" está a prometer o que a Google não dá.
* **A atribuição não é opcional.** Os termos da Google obrigam a mostrar o
  nome de quem escreveu e a ligação para a avaliação, e a não alterar o texto.
  É por isso que o autor e a fotografia vêm no que o serviço devolve.
* **Não se guarda para sempre.** A Google só permite guardar dados de um local
  por pouco tempo — o `place_id` é a exceção. Daí a cache ser de horas e não
  de dias.

Como em tudo o que fala com o exterior, **isto nunca levanta exceção**: a
página inicial não pode ficar em branco porque a Google esteve indisponível ou
porque a chave expirou. Falhando, a secção não aparece.
"""

from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_KEY = "google_reviews"

# Guardar o vazio por menos tempo do que o cheio: uma falha passageira não deve
# esconder a secção durante horas.
CACHE_SECONDS_ON_FAILURE = 300

# O que se pede à API. Pedir só isto é obrigatório na Places API nova — sem
# máscara de campos, o pedido é recusado — e é também o que evita pagar por
# dados que não se mostram.
FIELD_MASK = "rating,userRatingCount,googleMapsUri,reviews"


class GoogleReviewsError(Exception):
    """Falha a falar com a Places API, já com a explicação que ela devolveu."""


def is_configured():
    return bool(settings.GOOGLE_PLACES_API_KEY and settings.GOOGLE_PLACE_ID)


def _pedir():
    url = f"{settings.GOOGLE_PLACES_API_URL.rstrip('/')}/{settings.GOOGLE_PLACE_ID}"

    pedido = Request(
        url=url,
        headers={
            "X-Goog-Api-Key": settings.GOOGLE_PLACES_API_KEY,
            "X-Goog-FieldMask": FIELD_MASK,
            "Accept": "application/json",
            # Sem isto, os textos e as datas vêm em inglês.
            "Accept-Language": settings.GOOGLE_REVIEWS_LANGUAGE,
        },
        method="GET",
    )

    try:
        with urlopen(pedido, timeout=settings.GOOGLE_REQUEST_TIMEOUT) as resposta:
            return json.loads(resposta.read().decode("utf-8") or "{}")

    except HTTPError as erro:
        # O corpo do erro traz a razão em texto. Sem o ler sobrava
        # "HTTP Error 403: Forbidden", que não distingue uma chave sem a API
        # ligada de uma chave restringida ao domínio errado.
        try:
            detalhe = json.loads(erro.read().decode("utf-8") or "{}")
        except (ValueError, OSError):
            detalhe = {}

        mensagem = detalhe.get("error", {}).get("message") or f"HTTP {erro.code}"

        raise GoogleReviewsError(mensagem) from erro

    except URLError as erro:
        raise GoogleReviewsError(f"Google inacessível ({erro.reason}).") from erro

    except (TimeoutError, OSError, ValueError) as erro:
        raise GoogleReviewsError(f"Falha de rede com a Google: {erro}") from erro


def _normalizar(avaliacao):
    """Reduz uma avaliação ao que a página precisa de desenhar."""

    autor = avaliacao.get("authorAttribution") or {}
    texto = (avaliacao.get("originalText") or avaliacao.get("text") or {}).get(
        "text", ""
    )

    return {
        "author": autor.get("displayName", ""),
        "author_url": autor.get("uri", ""),
        "photo": autor.get("photoUri", ""),
        "rating": avaliacao.get("rating") or 0,
        # A escala é de cinco: o que falta para cinco desenha as estrelas
        # vazias, e fazer essa conta no template dava um ciclo por avaliação.
        "empty_stars": max(0, 5 - int(avaliacao.get("rating") or 0)),
        "text": texto.strip(),
        "when": avaliacao.get("relativePublishTimeDescription", ""),
        # Em ISO 8601, tal como a Google a manda. Não se mostra: serve para
        # ordenar, e ordenar por texto funciona porque o formato dela é
        # crescente por natureza — "2026-08-16" vem depois de "2026-08-03".
        "published_at": avaliacao.get("publishTime", ""),
        "url": avaliacao.get("googleMapsUri", ""),
    }


def _ordenar(avaliacoes):
    """As mais recentes à frente.

    **Quais são as cinco não se escolhe** — é a Google que as escolhe, e pedir
    `reviews_sort` à Places API nova é recusado com um 400. O que está nas
    nossas mãos é a ordem por que se mostram as que ela deu, e uma avaliação
    de há duas semanas diz mais sobre a casa do que uma de há dois anos.

    Ordenadas **antes** de se cortar pelo limite e não depois: com um limite
    abaixo de cinco, a ordem deixa de ser só a ordem — passa a decidir quais
    entram.

    As sem data ficam à parte e vão para o fim. Metê-las na mesma ordenação
    com uma chave qualquer não resolve: seja qual for a chave, o `reverse`
    atira-as para a ponta oposta àquela onde se queriam. Foi o defeito da
    primeira versão disto.
    """

    com_data = [a for a in avaliacoes if a.get("published_at")]
    sem_data = [a for a in avaliacoes if not a.get("published_at")]

    com_data.sort(key=lambda a: a["published_at"], reverse=True)

    return com_data + sem_data


def fetch_reviews():
    """Vai à API. Pode levantar `GoogleReviewsError`."""

    if not is_configured():
        return None

    dados = _pedir()

    avaliacoes = [
        _normalizar(avaliacao)
        for avaliacao in dados.get("reviews", [])
        # Uma avaliação só com estrelas não tem nada para ler. Conta para a
        # média, que vem à parte, mas num cartão ficaria vazia.
        if (avaliacao.get("originalText") or avaliacao.get("text") or {}).get("text")
    ]

    avaliacoes = _ordenar(avaliacoes)

    media = dados.get("rating")

    return {
        "rating": media,
        # As estrelas da média são contadas aqui pela mesma razão das de cada
        # avaliação: o template não sabe arredondar, e uma média de 4,6 tem de
        # dar cinco estrelas cheias e não quatro.
        "stars": round(media) if media else 0,
        "empty_stars": max(0, 5 - round(media)) if media else 5,
        "total": dados.get("userRatingCount"),
        "url": dados.get("googleMapsUri", ""),
        "reviews": avaliacoes[: settings.GOOGLE_REVIEWS_LIMIT],
    }


def get_reviews():
    """As avaliações a mostrar na página, da cache quando possível.

    Esta é a porta que a página inicial usa, e por isso é a que nunca deixa
    passar uma exceção: uma falha da Google não pode ser uma falha do site.
    """

    if not is_configured():
        return None

    guardadas = cache.get(CACHE_KEY)

    if guardadas is not None:
        return guardadas or None

    try:
        resultado = fetch_reviews()
    except GoogleReviewsError as erro:
        logger.warning("Avaliações do Google: %s", erro)
        cache.set(CACHE_KEY, {}, CACHE_SECONDS_ON_FAILURE)

        return None
    except Exception:
        logger.exception("Avaliações do Google: falha inesperada.")

        return None

    cache.set(CACHE_KEY, resultado or {}, settings.GOOGLE_REVIEWS_CACHE_SECONDS)

    return resultado
