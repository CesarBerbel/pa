"""Gravar PNG com paleta, em vez de três bytes por pixel.

As imagens da marca são desenho, não fotografia: fundo liso, poucos tons, uma
letra e um monograma. Guardadas em cor verdadeira, cada pixel ocupa três ou
quatro bytes e o compressor do PNG pouco consegue fazer. Reduzidas a uma paleta
de 256 entradas, o mesmo desenho ocupa cerca de metade — e nos ficheiros com
transparência, um quarto.

O erro que isto introduz nestas imagens fica abaixo de um valor por canal, em
média. Numa fotografia far-se-iam faixas visíveis no céu; num logótipo sobre
fundo liso não há degradês onde apareçam.

A transparência sobrevive: o PNG guarda a opacidade de cada entrada da paleta
num bloco `tRNS`, lido por tudo desde os anos noventa.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

# Mais do que isto não muda o tamanho e menos começa a fazer degraus nos
# contornos suavizados das letras.
CORES = 256


def guardar_png(imagem: Image.Image, caminho: Path) -> Path:
    """Grava `imagem` em `caminho` como PNG de paleta."""
    # `FASTOCTREE` é o único quantizador do Pillow que leva a opacidade em
    # conta; o `MEDIANCUT`, melhor a escolher cores, deita o canal alfa fora.
    tem_alfa = "A" in imagem.getbands()
    metodo = Image.FASTOCTREE if tem_alfa else Image.MEDIANCUT

    imagem.quantize(colors=CORES, method=metodo).save(
        caminho, "PNG", optimize=True, compress_level=9
    )

    return caminho
