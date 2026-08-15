"""URLs de ficheiros estáticos com versão.

`{% static %}` devolve sempre o mesmo URL, portanto o browser — e o service
worker, que guarda `/static/` cache-first — continuam a servir a cópia antiga
depois de o ficheiro mudar. Em desenvolvimento isso significa alterar o CSS e
não ver nada acontecer; em produção, um deploy que só chega a metade das
pessoas.

A versão vem da data de modificação do ficheiro de origem: muda quando, e só
quando, o conteúdo é substituído.
"""

from pathlib import Path

from django import template
from django.conf import settings
from django.templatetags.static import static

register = template.Library()

_versoes = {}


def asset_version(path):
    """Data de modificação do ficheiro em `static/`, como string."""

    if not settings.DEBUG and path in _versoes:
        return _versoes[path]

    ficheiro = Path(settings.BASE_DIR) / "static" / path

    try:
        versao = str(int(ficheiro.stat().st_mtime))
    except OSError:
        # Um ficheiro que não se consegue ler não deve rebentar a página; fica
        # sem versão e comporta-se como antes.
        versao = "0"

    if not settings.DEBUG:
        # Em produção o ficheiro não muda enquanto o processo vive, e assim
        # evita-se um stat() por cada página servida.
        _versoes[path] = versao

    return versao


@register.simple_tag
def versioned_static(path):
    return f"{static(path)}?v={asset_version(path)}"
