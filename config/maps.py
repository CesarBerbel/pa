"""O endereço do mapa que vai no rodapé.

Há duas maneiras de incorporar um mapa da Google, e a diferença entre elas é
precisamente o que aqui se quer:

* o endereço com `pb=`, copiado do "Partilhar → Incorporar um mapa", desenha o
  mapa com um pino e mais nada;
* o **Maps Embed API em modo `place`** desenha o mesmo mapa com o cartão do
  estabelecimento ao lado — nome, classificação em estrelas, número de
  avaliações, morada e os botões de ver no Google Maps e traçar rota.

O segundo é o que se quer, e precisa de uma chave.

**Uma chave à parte, e não a das avaliações.** A das avaliações é lida no
servidor e nunca sai daqui; esta vai escrita no HTML, à vista de qualquer
pessoa que abra o código da página. São coisas diferentes com riscos
diferentes: esta tem de ser restringida por domínio na consola da Google, e
reaproveitar a outra seria pô-la na rua — além de que uma chave restringida por
IP nem sequer funcionaria no browser de quem visita o site.

Sem chave, fica o mapa de sempre. O rodapé nunca fica vazio por causa de uma
configuração que falta.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings

# O mapa de sempre: a ficha do estabelecimento em modo mapa, sem cartão. Vale
# enquanto não houver chave do Maps Embed API, e é o que estava no rodapé antes
# de isto existir.
MAPA_SIMPLES = (
    "https://www.google.com/maps/embed"
    "?pb=!1m18!1m12!1m3!1d8372.651118343003!2d-8.421179330722307"
    "!3d40.21086098822837!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1"
    "!3m3!1m2!1s0xd22f9608ebaeb71%3A0xb3ce60a117f3e59c"
    "!2sPriscila%20Arantes%20Pedicure%20Terap%C3%AAutica"
    "!5e0!3m2!1spt-PT!2spt!4v1787921638343!5m2!1spt-PT!2spt"
)

EMBED_API = "https://www.google.com/maps/embed/v1/place"


def endereco_do_mapa(idioma=None):
    """O endereço a pôr no `iframe` do rodapé.

    Com chave e identificador do local, o mapa com o cartão e as avaliações.
    Sem um deles, o mapa simples — que continua a mostrar onde é, que é o
    mínimo que o rodapé tem de fazer.
    """

    chave = getattr(settings, "GOOGLE_MAPS_EMBED_API_KEY", "")
    local = getattr(settings, "GOOGLE_PLACE_ID", "")

    if not chave or not local:
        return MAPA_SIMPLES

    parametros = {
        # `place_id:` e não o nome escrito: o nome apanha o estabelecimento
        # errado no dia em que abrir outro parecido no mesmo edifício, e já
        # aconteceu uma vez a este mapa.
        "q": f"place_id:{local}",
        "key": chave,
        # Nível de aproximação com a rua à volta ainda legível. Sem isto o
        # mapa abre demasiado longe para se perceber onde se estaciona.
        "zoom": "16",
    }

    if idioma:
        # "pt-pt" para "pt-PT": é a forma que a Google documenta, e não vale a
        # pena descobrir da maneira difícil se a dela é indiferente a
        # maiúsculas.
        partes = idioma.split("-")

        if len(partes) == 2:
            idioma = f"{partes[0]}-{partes[1].upper()}"

        parametros["language"] = idioma

    # `safe=":"` para o `place_id:` ficar escrito como a Google o documenta, e
    # não como `place_id%3A`. Deviam valer o mesmo; não vale a pena apostar
    # nisso num endereço que só se vê falhar em produção.
    return f"{EMBED_API}?{urlencode(parametros, safe=':')}"
