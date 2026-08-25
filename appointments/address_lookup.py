"""Moradas sugeridas pela Google, para o formulário da marcação.

Fala com a Places API (New) — a mesma chave que já traz as avaliações — e
devolve o que o formulário precisa: uma lista de sugestões enquanto se escreve,
e a morada em campos quando se escolhe uma.

**A chave nunca vai para o browser.** A do projeto é uma chave de servidor, e
uma chave de servidor posta numa página é uma chave que qualquer pessoa copia.
Por isso o pedido sai daqui e não do JavaScript: a página fala com a área
interna, e é a área interna que fala com a Google.

**A sessão poupa dinheiro.** A Google cobra o autocompletar por sessão quando
as sugestões e os detalhes vêm com o mesmo `sessionToken`: sem ele, cada tecla
escrita é uma consulta faturada à parte. O token é gerado pelo formulário e
morre quando uma morada é escolhida.

Como em tudo o que fala com o exterior, **isto nunca levanta exceção**: sem
Google, o formulário continua a poder ser preenchido à mão, que é como era
antes de haver sugestões nenhumas.
"""

from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)

AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"

# Sem máscara de campos a Places API nova recusa o pedido, e pedir só isto é
# também o que evita pagar por dados que não se mostram.
SUGGESTION_FIELDS = (
    "suggestions.placePrediction.placeId,"
    "suggestions.placePrediction.structuredFormat"
)

DETAIL_FIELDS = "addressComponents,formattedAddress"

# Que componente da Google enche que campo do formulário. A Google devolve os
# tipos numa lista por componente; o primeiro que encaixar é o que vale.
COMPONENTES = [
    ("home_street", "route", "longText"),
    ("home_number", "street_number", "longText"),
    ("home_floor", "subpremise", "longText"),
    ("home_postal_code", "postal_code", "longText"),
    ("home_locality", "locality", "longText"),
    ("home_municipality", "administrative_area_level_2", "longText"),
    ("home_district", "administrative_area_level_1", "longText"),
    ("home_country", "country", "longText"),
]


def is_configured():
    return bool(settings.GOOGLE_PLACES_API_KEY)


def _pedir(url, corpo=None, campos=""):
    """Um pedido à Places API. Devolve o JSON, ou None se algo correr mal."""

    if not is_configured():
        return None

    cabecalhos = {
        "X-Goog-Api-Key": settings.GOOGLE_PLACES_API_KEY,
        "Accept": "application/json",
    }

    if campos:
        cabecalhos["X-Goog-FieldMask"] = campos

    dados = None

    if corpo is not None:
        cabecalhos["Content-Type"] = "application/json"
        dados = json.dumps(corpo).encode("utf-8")

    pedido = Request(
        url=url,
        headers=cabecalhos,
        data=dados,
        method="POST" if dados else "GET",
    )

    try:
        with urlopen(pedido, timeout=settings.GOOGLE_REQUEST_TIMEOUT) as resposta:
            return json.loads(resposta.read().decode("utf-8") or "{}")

    except HTTPError as erro:
        # O corpo do erro traz a razão em texto. Sem o ler sobrava
        # "HTTP Error 403: Forbidden", que não distingue uma chave sem a API
        # ligada de uma chave restringida ao servidor errado.
        try:
            detalhe = json.loads(erro.read().decode("utf-8") or "{}")
        except (ValueError, OSError):
            detalhe = {}

        logger.warning(
            "Places API recusou o pedido de moradas: %s",
            detalhe.get("error", {}).get("message") or f"HTTP {erro.code}",
        )

    except (URLError, TimeoutError, OSError, ValueError) as erro:
        logger.warning("Places API inacessível: %s", erro)

    return None


def suggest(texto, session_token=""):
    """Moradas que começam pelo que já foi escrito.

    Restrito a Portugal: a clínica desloca-se a casa de quem atende, e uma
    lista com moradas do outro lado do mundo só atrapalha quem escreve.
    """

    texto = (texto or "").strip()

    # A Google devolve disparates com uma letra ou duas, e cada pedido custa.
    if len(texto) < 3:
        return []

    corpo = {
        "input": texto,
        "includedRegionCodes": [settings.HOME_VISIT_REGION_CODE],
        "languageCode": "pt-PT",
        # Só moradas: sem isto vinham restaurantes e lojas, que não são sítios
        # onde se vá fazer um atendimento.
        "includedPrimaryTypes": ["street_address", "premise", "subpremise", "route"],
    }

    if session_token:
        corpo["sessionToken"] = session_token

    resposta = _pedir(AUTOCOMPLETE_URL, corpo=corpo, campos=SUGGESTION_FIELDS) or {}

    sugestoes = []

    for entrada in resposta.get("suggestions") or []:
        predicao = entrada.get("placePrediction")

        if not predicao or not predicao.get("placeId"):
            continue

        formato = predicao.get("structuredFormat") or {}

        sugestoes.append(
            {
                "place_id": predicao["placeId"],
                "main": (formato.get("mainText") or {}).get("text", ""),
                "secondary": (formato.get("secondaryText") or {}).get("text", ""),
            }
        )

    return sugestoes


def details(place_id, session_token=""):
    """A morada escolhida, já repartida pelos campos do formulário."""

    place_id = (place_id or "").strip()

    if not place_id:
        return {}

    url = f"https://places.googleapis.com/v1/places/{place_id}"

    if session_token:
        url = f"{url}?sessionToken={session_token}"

    resposta = _pedir(url, campos=DETAIL_FIELDS)

    if resposta is None:
        return {}

    componentes = resposta.get("addressComponents") or []
    morada = {campo: "" for campo, _, _ in COMPONENTES}

    for campo, tipo, chave in COMPONENTES:
        for componente in componentes:
            if tipo in (componente.get("types") or []):
                morada[campo] = componente.get(chave, "")
                break

    morada["formatted"] = resposta.get("formattedAddress", "")

    return morada
