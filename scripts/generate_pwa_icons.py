"""Gera os ícones da PWA a partir do logo.

    python scripts/generate_pwa_icons.py

O logo do projeto é largo (2172x724) e os ícones de aplicação têm de ser
quadrados. Cada ícone é o logo centrado sobre o fundo da marca, com margem.

O ícone "maskable" leva margem maior: o Android recorta o ícone em círculo,
losango ou quadrado arredondado consoante o fabricante, e sem margem o logo
sairia cortado.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
ORIGEM = BASE_DIR / "static" / "img" / "logo_transparent.png"
DESTINO = BASE_DIR / "static" / "img"

FUNDO = (255, 247, 249, 255)  # --bg-soft

# (ficheiro, lado, fração do lado ocupada pelo logo)
ICONES = [
    ("icon-192.png", 192, 0.82),
    ("icon-512.png", 512, 0.82),
    # Zona de segurança do formato maskable: o conteúdo tem de caber num
    # círculo com 80% do lado, por isso o logo fica bastante mais pequeno.
    ("icon-maskable-512.png", 512, 0.60),
]


def gerar(nome: str, lado: int, ocupacao: float) -> Path:
    logo = Image.open(ORIGEM).convert("RGBA")

    largura_alvo = int(lado * ocupacao)
    altura_alvo = int(logo.height * (largura_alvo / logo.width))

    if altura_alvo > lado * ocupacao:
        altura_alvo = int(lado * ocupacao)
        largura_alvo = int(logo.width * (altura_alvo / logo.height))

    redimensionado = logo.resize((largura_alvo, altura_alvo), Image.LANCZOS)

    tela = Image.new("RGBA", (lado, lado), FUNDO)
    tela.paste(
        redimensionado,
        ((lado - largura_alvo) // 2, (lado - altura_alvo) // 2),
        redimensionado,
    )

    caminho = DESTINO / nome
    tela.convert("RGB").save(caminho, "PNG", optimize=True)

    return caminho


def main() -> int:
    if not ORIGEM.exists():
        print(f"ERRO: não encontrei {ORIGEM}", file=sys.stderr)
        return 1

    for nome, lado, ocupacao in ICONES:
        caminho = gerar(nome, lado, ocupacao)
        tamanho = caminho.stat().st_size // 1024
        print(
            f"{caminho.relative_to(BASE_DIR).as_posix()}: {lado}x{lado}, {tamanho} KB"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
