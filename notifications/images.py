"""Preparar uma fotografia carregada para ser mostrada no site.

Uma fotografia tirada com telemóvel tem hoje 3000 a 4000 píxeis de largura e
vários megabytes. O sítio onde ela aparece tem 460 píxeis. Guardar o ficheiro
como veio significa mandar dez a vinte vezes mais dados do que o ecrã
consegue mostrar — lento a abrir, e caro para quem está com dados móveis.

Além do tamanho, há duas coisas que se resolvem aqui:

* **A orientação.** Um telemóvel grava a fotografia sempre na mesma direção e
  guarda à parte, nos metadados, a nota de como deve ser rodada. Quem lê essa
  nota mostra-a direita; quem não a lê mostra-a deitada. Rodá-la de verdade
  acaba com a diferença.
* **Os metadados.** Esses mesmos dados trazem a data, o modelo do telemóvel e,
  muitas vezes, **as coordenadas de onde a fotografia foi tirada**. São
  fotografias de pacientes: publicar a morada de quem quer que seja junto com
  a imagem não é aceitável. Ao gravar de novo, tudo isso fica para trás.
"""

from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from PIL import Image, ImageOps

# O maior lado depois de encolher. O espaço no site tem 460 píxeis; o dobro
# cobre ecrãs de alta densidade, e o resto é margem para quem abrir a imagem
# em separado.
MAX_SIDE = 1200

JPEG_QUALITY = 82


def resize_uploaded_image(campo):
    """Encolhe e volta a gravar a imagem de um `ImageField`, se for nova.

    Só mexe em ficheiros acabados de carregar. Uma imagem que já está no
    disco passou por aqui uma vez, e voltar a comprimi-la a cada gravação do
    registo — mudar uma legenda, por exemplo — degradava-a um pouco de cada
    vez, sem nada a ganhar.
    """

    if not campo:
        return False

    try:
        ficheiro = campo.file
    except (ValueError, FileNotFoundError):
        return False

    if not isinstance(ficheiro, UploadedFile):
        return False

    ficheiro.seek(0)

    with Image.open(ficheiro) as original:
        # A rotação tem de vir antes de tudo: depois de gravar já não há
        # metadados que digam como a imagem devia estar virada.
        imagem = ImageOps.exif_transpose(original)

        # O JPEG não tem transparência. Um PNG com fundo transparente ficaria
        # preto sem esta conversão.
        if imagem.mode != "RGB":
            imagem = imagem.convert("RGB")

        # `thumbnail` só encolhe: uma fotografia já pequena fica como está,
        # em vez de ser esticada e ficar desfocada.
        imagem.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)

        destino = BytesIO()
        imagem.save(
            destino,
            format="JPEG",
            quality=JPEG_QUALITY,
            optimize=True,
            # Vai aparecendo à medida que chega, em vez de linha a linha.
            progressive=True,
        )

    nome = Path(campo.name).with_suffix(".jpg").name
    campo.save(nome, ContentFile(destino.getvalue()), save=False)

    return True
