"""Gera os ícones da aplicação e a marca do menu a partir de `icone.png`.

    python scripts/generate_pwa_icons.py

O ficheiro de origem é o monograma quadrado, desenhado sobre fundo branco
opaco. Colado tal e qual sobre a barra de navegação — que é branco a 92% com
desfoque — via-se o quadrado sempre que passasse conteúdo escuro por trás. Por
isso o branco é convertido em transparência antes de qualquer outra coisa.

Do mesmo original saem:

* os ícones da PWA, quadrados, sobre o fundo da marca;
* `logo-mark.png`, a versão leve para o menu — o original tem meio megabyte
  para ser mostrado a 120 pixels de altura.

O ícone "maskable" leva margem maior: o Android recorta-o em círculo, losango
ou quadrado arredondado consoante o fabricante, e sem margem o desenho sairia
cortado.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops

BASE_DIR = Path(__file__).resolve().parent.parent
ORIGEM = BASE_DIR / "static" / "img" / "icone.png"
CONJUNTO = BASE_DIR / "static" / "img" / "logo_transparent.png"
DESTINO = BASE_DIR / "static" / "img"

FUNDO = (255, 247, 249, 255)  # --bg-soft

# (ficheiro, lado, fração do lado ocupada pelo desenho)
ICONES = [
    ("icon-192.png", 192, 0.86),
    ("icon-512.png", 512, 0.86),
    # Zona de segurança do formato maskable: o conteúdo tem de caber num
    # círculo com 80% do lado, por isso o desenho fica bastante mais pequeno.
    ("icon-maskable-512.png", 512, 0.62),
]

# O menu mostra-os a 120px de altura; o dobro chega para ecrãs de alta
# densidade sem carregar meio megabyte por cada página.
LADO_MARCA = 240
ALTURA_CONJUNTO = 240


def sem_fundo_branco(imagem: Image.Image) -> Image.Image:
    """Converte o branco do fundo em transparência.

    O desenho está sobre branco puro, portanto a opacidade de cada pixel é o
    quanto ele se afasta do branco. Depois disso é preciso desfazer a mistura
    com o branco, senão os traços claros ficam mais claros do que eram: um rosa
    a 250,200,200 com 21% de opacidade, recomposto sobre branco, daria 254 em
    vez de 250.
    """

    imagem = imagem.convert("RGBA")
    r, g, b, _ = imagem.split()

    # Quanto mais escuro for o canal mais afastado do branco está o pixel, e
    # portanto mais opaco. O mínimo dos três preserva as cores saturadas.
    minimo = ImageChops.darker(ImageChops.darker(r, g), b)
    alfa = ImageChops.invert(minimo)

    valores_alfa = alfa.load()
    origem = imagem.load()

    resultado = Image.new("RGBA", imagem.size)
    destino = resultado.load()

    for y in range(imagem.height):
        for x in range(imagem.width):
            a = valores_alfa[x, y]

            if a == 0:
                destino[x, y] = (0, 0, 0, 0)
                continue

            cor = origem[x, y]

            destino[x, y] = (
                *(
                    min(255, max(0, 255 - (255 - canal) * 255 // a))
                    for canal in cor[:3]
                ),
                a,
            )

    return resultado


def centrar(desenho: Image.Image, lado: int, ocupacao: float) -> Image.Image:
    alvo = int(lado * ocupacao)
    redimensionado = desenho.resize((alvo, alvo), Image.LANCZOS)

    tela = Image.new("RGBA", (lado, lado), FUNDO)
    tela.paste(redimensionado, ((lado - alvo) // 2, (lado - alvo) // 2), redimensionado)

    return tela


def main() -> int:
    if not ORIGEM.exists():
        print(f"ERRO: não encontrei {ORIGEM}", file=sys.stderr)
        return 1

    original = Image.open(ORIGEM)

    if original.width != original.height:
        print(
            f"AVISO: {ORIGEM.name} não é quadrado ({original.size}); "
            "o desenho vai ficar distorcido.",
            file=sys.stderr,
        )

    desenho = sem_fundo_branco(original)

    gerados = []

    for nome, lado, ocupacao in ICONES:
        caminho = DESTINO / nome
        # Os ícones da aplicação são opacos: o Android e o iOS não contam com
        # transparência e desenhariam o que estivesse por trás.
        centrar(desenho, lado, ocupacao).convert("RGB").save(
            caminho, "PNG", optimize=True
        )
        gerados.append((caminho, f"{lado}x{lado}"))

    # A marca do menu mantém a transparência, para assentar na barra.
    marca = DESTINO / "logo-mark.png"
    desenho.resize((LADO_MARCA, LADO_MARCA), Image.LANCZOS).save(
        marca, "PNG", optimize=True
    )
    gerados.append((marca, f"{LADO_MARCA}x{LADO_MARCA}, com transparência"))

    # O conjunto com o nome, para o menu em ecrãs largos. O original tem 2172
    # pixels de largura para ser mostrado a 360, e é servido em todas as
    # páginas.
    if CONJUNTO.exists():
        original_conjunto = Image.open(CONJUNTO).convert("RGBA")
        largura = round(
            original_conjunto.width * ALTURA_CONJUNTO / original_conjunto.height
        )

        conjunto = DESTINO / "logo-wordmark.png"
        original_conjunto.resize((largura, ALTURA_CONJUNTO), Image.LANCZOS).save(
            conjunto, "PNG", optimize=True
        )
        gerados.append((conjunto, f"{largura}x{ALTURA_CONJUNTO}, com transparência"))
    else:
        print(f"AVISO: não encontrei {CONJUNTO.name}", file=sys.stderr)

    for caminho, detalhe in gerados:
        tamanho = caminho.stat().st_size // 1024
        print(f"{caminho.relative_to(BASE_DIR).as_posix()}: {detalhe}, {tamanho} KB")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
