"""Limpeza do HTML escrito no editor, antes de ele chegar à base de dados.

Até aqui, o texto das páginas era escapado ao sair: `{{ texto|linebreaks }}`, e
um campo de formulário nunca podia pôr etiquetas numa página pública. Um editor
de texto acaba com isso — o que se escreve **é** HTML, e a página tem de o
mostrar como HTML.

A troca de garantia tem de ser feita algures, e o sítio é este: **limpa-se à
entrada, não à saída.** Duas razões.

A primeira é que à saída se esquece. Uma página nova, um resumo mostrado num
sítio diferente, um email que reaproveita o texto — cada um desses é uma
oportunidade de alguém escrever `|safe` sem limpar. Limpo à entrada, o que está
guardado é seguro em todo o lado onde for parar.

A segunda é que dá para ver. O que está na base de dados é o que vai para a
página, e não uma versão que só existe depois de passar por um filtro.

**Quem escreve é de dentro de casa.** Isto não protege contra a profissional —
protege contra o que ela cole de outro sítio. Copiar uma tabela de uma página
web traz consigo `<script>`, `onclick`, `style` com `url(javascript:...)` e um
punhado de coisas que ninguém quis. É esse o caso comum, e é esse que isto
apanha.
"""

from __future__ import annotations

import nh3

# O que se pode escrever. É uma lista de permissões e não de proibições: uma
# lista de proibições esquece sempre a etiqueta seguinte que alguém inventar.
ETIQUETAS = {
    # Texto
    "p",
    "br",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "s",
    "sub",
    "sup",
    "mark",
    "small",
    "span",
    "div",
    # Títulos. O <h1> fica de fora de propósito: é o título da página e é a
    # página que o dá. Dois <h1> valem menos do que um.
    "h2",
    "h3",
    "h4",
    # Listas
    "ul",
    "ol",
    "li",
    # Blocos
    "blockquote",
    "pre",
    "code",
    "hr",
    # Ligações e imagens
    "a",
    "img",
    "figure",
    "figcaption",
    # Tabelas
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "caption",
    "colgroup",
    "col",
}

ATRIBUTOS = {
    "*": {"class", "id", "title", "dir", "lang"},
    # Sem "rel": é o `link_rel` abaixo que o escreve, e o nh3 recusa gerir
    # os dois ao mesmo tempo — com razão, porque um "rel" colado de fora
    # substituiria o que aqui se garante.
    "a": {"href", "target"},
    "img": {"src", "alt", "width", "height", "loading"},
    "td": {"colspan", "rowspan", "headers"},
    "th": {"colspan", "rowspan", "scope", "abbr"},
    "col": {"span"},
    "colgroup": {"span"},
    "ol": {"start", "type"},
}

# Sem `javascript:` nem `data:`. Um `data:` numa etiqueta `<a>` é uma página
# inteira escondida dentro de um link, e num `<img>` é a forma habitual de
# contornar uma política de conteúdos.
ESQUEMAS = {"http", "https", "mailto", "tel"}


def limpar(html):
    """Devolve o HTML sem nada que possa correr ou levar alguém para fora.

    Vazio entra, vazio sai — um `None` de um campo por preencher não é erro.
    """

    if not html:
        return ""

    return nh3.clean(
        html,
        tags=ETIQUETAS,
        attributes={etiqueta: set(valores) for etiqueta, valores in ATRIBUTOS.items()},
        url_schemes=ESQUEMAS,
        # Todo o link para fora leva `rel="noopener noreferrer"`. Sem
        # `noopener`, a página aberta ganha uma referência para esta e pode
        # trocá-la por outra debaixo dos pés de quem clicou.
        link_rel="noopener noreferrer",
    )


def esta_vazio(html):
    """Diz se o que sobra do HTML é texto a sério ou só marcação vazia.

    Um editor deixado por preencher não devolve string vazia: devolve
    `<p><br></p>`, ou `<p>&nbsp;</p>`, que parecem conteúdo a qualquer
    verificação de "está preenchido?" e não são. É isto que impede publicar uma
    página com um parágrafo vazio lá dentro.
    """

    if not html:
        return True

    # Sem etiquetas nenhumas sobra o texto. O `\xa0` é o espaço duro que o
    # editor põe, e que não conta como espaço para o `strip()`.
    texto = nh3.clean(html, tags=set()).replace("&nbsp;", " ").replace("\xa0", " ")

    return not texto.strip()
