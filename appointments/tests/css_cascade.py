"""Resolvedor mínimo de cascata para folhas de estilo estáticas.

Serve um problema concreto: `public.css` redefine os mesmos seletores em várias
camadas, sem media query, e uma media query não acrescenta especificidade. Uma
regra escrita para o telemóvel a meio do ficheiro é anulada por uma regra
genérica escrita mais abaixo, sem aviso nenhum.

Procurar o texto da regra no ficheiro não deteta isso — a regra está lá, apenas
não ganha. Isto percorre as regras por ordem e devolve o valor que o browser
acabaria por aplicar, para uma largura de ecrã concreta.

Assume o que basta para este ficheiro: seletores de classe simples, todos com a
mesma especificidade, sem @media aninhados nem @supports.
"""

from __future__ import annotations

import re

COMENTARIO = re.compile(r"/\*.*?\*/", re.S)
CONDICAO_LARGURA = re.compile(r"(min|max)-width:\s*(\d+)px")
CONDICAO_HOVER = re.compile(r"hover:\s*(hover|none)")


class Stylesheet:
    def __init__(self, texto):
        self.regras = list(_ler_regras(COMENTARIO.sub("", texto)))

    def resolve(self, seletor, prop, width, hover=False):
        """Valor final de `prop` em `seletor`, para a largura dada.

        Devolve None se nenhuma regra aplicável a definir.
        """

        valor = None

        for media, seletores, declaracoes in self.regras:
            if seletor not in seletores:
                continue

            if not _media_aplica(media, width, hover):
                continue

            if prop in declaracoes:
                valor = declaracoes[prop]

        return valor

    def declaring_rules(self, seletor, prop):
        """Onde é que `prop` é definida, por ordem. Útil em mensagens de erro."""

        return [
            media or "(sem media query)"
            for media, seletores, declaracoes in self.regras
            if seletor in seletores and prop in declaracoes
        ]


def _media_aplica(condicao, width, hover):
    if not condicao:
        return True

    # Uma condição que não se saiba avaliar não deve fingir que se aplica.
    if "prefers-" in condicao or "print" in condicao:
        return False

    correspondencia_hover = CONDICAO_HOVER.search(condicao)

    if correspondencia_hover:
        return (correspondencia_hover.group(1) == "hover") == hover

    limites = CONDICAO_LARGURA.findall(condicao)

    if not limites:
        return False

    for tipo, valor in limites:
        if tipo == "max" and width > int(valor):
            return False
        if tipo == "min" and width < int(valor):
            return False

    return True


def _ler_regras(texto):
    """Produz (media, {seletores}, {propriedade: valor}) por ordem do ficheiro."""

    for media, corpo in _blocos_de_topo(texto):
        for cabecalho, declaracoes in _pares_seletor_bloco(corpo):
            if cabecalho.startswith("@"):
                continue

            seletores = {s.strip() for s in cabecalho.split(",") if s.strip()}

            yield media, seletores, _declaracoes(declaracoes)


def _blocos_de_topo(texto):
    """Separa o conteúdo fora de @media do conteúdo dentro de cada @media."""

    posicao = 0

    for correspondencia in re.finditer(r"@media([^{]*)\{", texto):
        yield None, texto[posicao : correspondencia.start()]

        corpo, fim = _ate_fechar(texto, correspondencia.end())

        yield correspondencia.group(1).strip(), corpo
        posicao = fim

    yield None, texto[posicao:]


def _ate_fechar(texto, inicio):
    """Devolve o conteúdo até à chaveta que fecha a aberta antes de `inicio`."""

    profundidade = 1
    i = inicio

    while i < len(texto) and profundidade:
        if texto[i] == "{":
            profundidade += 1
        elif texto[i] == "}":
            profundidade -= 1
        i += 1

    return texto[inicio : i - 1], i


def _pares_seletor_bloco(texto):
    for correspondencia in re.finditer(r"([^{}]+)\{([^{}]*)\}", texto):
        yield correspondencia.group(1).strip(), correspondencia.group(2)


def _declaracoes(texto):
    resultado = {}

    for parte in texto.split(";"):
        if ":" not in parte:
            continue

        nome, _, valor = parte.partition(":")
        resultado[nome.strip()] = valor.strip()

    return resultado
