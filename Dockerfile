# Duas fases. A primeira instala as dependências com o compilador e os
# cabeçalhos à mão; a segunda leva só o resultado. A imagem passa de 947 MB
# para 498 MB, e — o que conta mais — o compilador deixa de viajar para
# produção, onde não serve para nada e é uma ferramenta a mais para quem lá
# entre.

# --- Fase 1: construir as dependências ---------------------------------------
FROM python:3.12-slim AS dependencias

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# `--prefix` junta tudo numa árvore só, que a fase seguinte copia de uma vez.
RUN pip install --no-cache-dir --prefix=/dependencias -r requirements.txt


# --- Fase 2: a imagem que vai correr -----------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# `libpq5` e não `libpq-dev`: é a biblioteca de execução, sem cabeçalhos nem
# compilador atrás. Faz falta porque o `requirements.txt` traz o psycopg 3, e
# é esse que o Django tenta primeiro. Sem ela nada rebentava — o Django cairia
# em silêncio para o psycopg2-binary, que traz a sua própria cópia — e é
# precisamente isso que se quer evitar: uma imagem que muda de driver de base
# de dados sozinha, sem ninguém dar por ela.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=dependencias /dependencias /usr/local

# UID fixo, e não o primeiro que o sistema atribuir: a pasta `media/` do
# anfitrião é montada dentro do contentor (ver docker-compose.prod.yml) e as
# permissões dela são as do anfitrião. Com um UID que mudasse entre
# construções, mudava com ele o dia em que o carregamento de fotografias
# deixava de conseguir escrever.
#
# 1000 é o primeiro utilizador humano de um Debian ou Ubuntu, que é quem
# costuma ser dono de /opt/pa. Se no servidor for outro, passa-se na
# construção: `docker compose build --build-arg APP_UID=1001`.
ARG APP_UID=1000
ARG APP_GID=1000

RUN groupadd --gid "$APP_GID" pa \
    && useradd --uid "$APP_UID" --gid "$APP_GID" --create-home \
        --shell /usr/sbin/nologin pa

WORKDIR /app

COPY --chown=pa:pa . .

# O `collectstatic` do arranque escreve em `staticfiles/`, e `media/` é o ponto
# de montagem. As duas têm de existir e ser do utilizador antes de ele deixar
# de ser root e perder o direito de as criar.
RUN mkdir -p /app/staticfiles /app/media && chown -R pa:pa /app

# Daqui para a frente, e em particular o gunicorn, corre sem privilégios. Um
# processo exposto à internet não tem razão nenhuma para ser root dentro do
# contentor.
USER pa

EXPOSE 8000
