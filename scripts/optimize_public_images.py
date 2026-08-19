"""Gera as imagens públicas a partir dos originais em `assets/img/`.

    python scripts/optimize_public_images.py

Os originais são ficheiros de trabalho: têm 1024 a 2172 pixels de largura e
pesam entre 380 KB e 1,4 MB cada. Estavam em `static/`, o que os fazia ir para
produção inteiros — a página inicial chegava a pedir 2,7 MB de PNG para mostrar
um logótipo de 360 pixels e uma foto de fundo.

Aqui saem em WebP, no tamanho em que são realmente mostrados (o dobro, para
ecrãs de alta densidade). O WebP é lido por tudo o que também consegue correr
o resto do site, e poupa cerca de 95% face ao PNG destas imagens.

A exceção é `logo-og.png`: é a imagem das pré-visualizações de links. Quem a lê
são os robôs do WhatsApp, Facebook e afins, que continuam a esperar PNG ou JPEG
e ignoram ficheiros grandes de mais.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
ORIGENS = BASE_DIR / "assets" / "img"
DESTINO = BASE_DIR / "static" / "img"

FUNDO = (255, 247, 249)  # --bg-soft

# (origem, destino, largura, qualidade)
#
# As larguras vêm do tamanho a que a imagem é mostrada, a dobrar:
# - o fundo do hero é servido tal como está (o original só tem 1024);
# - os logótipos aparecem no máximo a 560 px (`.luxury-logo-transparent`).
WEBP = [
    ("hero-photo.png", "hero-photo.webp", 1024, 82),
    ("logo.png", "logo.webp", 1120, 85),
    ("logo-transparent.png", "logo-transparent.webp", 1120, 85),
]

# A proporção que o Facebook, o WhatsApp e o LinkedIn recortam sem cortar nada.
OG_LARGURA = 1200
OG_ALTURA = 630
OG_OCUPACAO = 0.78


def redimensionar(imagem: Image.Image, largura: int) -> Image.Image:
    if imagem.width <= largura:
        return imagem

    altura = round(imagem.height * largura / imagem.width)

    return imagem.resize((largura, altura), Image.LANCZOS)


def cartao_social(origem: Image.Image) -> Image.Image:
    """Coloca a marca centrada numa tela 1200x630, sobre o fundo do site.

    O logótipo é três vezes mais largo do que alto. Servido tal e qual, cada
    pré-visualização apareceria com faixas cinzentas decididas por quem partilha
    o link — e não sempre as mesmas.
    """

    marca = redimensionar(origem.convert("RGBA"), int(OG_LARGURA * OG_OCUPACAO))

    tela = Image.new("RGB", (OG_LARGURA, OG_ALTURA), FUNDO)
    tela.paste(
        marca,
        ((OG_LARGURA - marca.width) // 2, (OG_ALTURA - marca.height) // 2),
        marca,
    )

    return tela


def main() -> int:
    if not ORIGENS.exists():
        print(f"ERRO: não encontrei {ORIGENS}", file=sys.stderr)
        return 1

    gerados = []

    for nome_origem, nome_destino, largura, qualidade in WEBP:
        origem = ORIGENS / nome_origem

        if not origem.exists():
            print(f"AVISO: não encontrei {origem.name}", file=sys.stderr)
            continue

        imagem = Image.open(origem)
        # `method=6` é a compressão mais lenta e mais eficaz do WebP. Isto corre
        # à mão, uma vez por imagem trocada, portanto o tempo não custa nada.
        redimensionar(imagem, largura).save(
            DESTINO / nome_destino, "WEBP", quality=qualidade, method=6
        )
        gerados.append((DESTINO / nome_destino, f"{largura}px de largura"))

    origem_marca = ORIGENS / "logo.png"

    if origem_marca.exists():
        cartao = DESTINO / "logo-og.png"
        cartao_social(Image.open(origem_marca)).save(cartao, "PNG", optimize=True)
        gerados.append((cartao, f"{OG_LARGURA}x{OG_ALTURA}, para pré-visualizações"))

    for caminho, detalhe in gerados:
        tamanho = caminho.stat().st_size // 1024
        print(f"{caminho.relative_to(BASE_DIR).as_posix()}: {detalhe}, {tamanho} KB")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
