#!/usr/bin/env bash
#
# Restaura a base de dados PostgreSQL de produção a partir de uma cópia.
#
#   ./scripts/restore_db.sh backups/pa_pa_2026-08-10_030000.dump
#
# ESTA OPERAÇÃO APAGA OS DADOS ATUAIS. Antes de tocar em alguma coisa o script
# pede confirmação escrita e cria uma cópia de segurança do estado presente,
# para que um restauro enganado continue a ter volta.
#
# Restaura as duas metades: a base e as fotografias que lhe correspondem.
# O arquivo das fotografias e encontrado pelo carimbo do dump — o mesmo par
# que o backup_db.sh cria. Restaurar so a base devolveria os registos com as
# legendas e sem as imagens.
#
# Sequencia:
#   1. valida o dump e procura o par das fotografias
#   2. pede confirmacao
#   3. copia o estado atual — base E fotografias — para backups/
#   4. para o servico web, para ninguem escrever a meio
#   5. restaura a base
#   6. restaura as fotografias
#   7. levanta o web e aplica migrations
#
# Variaveis de ambiente aceites: PROJECT_DIR, ENV_FILE, COMPOSE_FILE,
# BACKUP_DIR, MEDIA_DIR

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_DIR="${PROJECT_DIR:-$(dirname "$SCRIPT_DIR")}"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env.prod}"
COMPOSE_FILE="${COMPOSE_FILE:-$PROJECT_DIR/docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
MEDIA_DIR="${MEDIA_DIR:-$PROJECT_DIR/media}"

erro() {
    echo "ERRO: $*" >&2
    exit 1
}

FICHEIRO="${1:-}"

[ -n "$FICHEIRO" ] || erro "indique o ficheiro a restaurar: $0 <ficheiro.dump>"
[ -f "$FICHEIRO" ] || erro "não encontrei $FICHEIRO"
[ -f "$ENV_FILE" ] || erro "não encontrei $ENV_FILE"

ler_env() {
    local chave="$1"
    local valor
    valor="$(grep -E "^${chave}=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true)"
    valor="${valor%\"}"
    valor="${valor#\"}"
    printf '%s' "$valor"
}

DB_NAME="$(ler_env DB_NAME)"
DB_USER="$(ler_env DB_USER)"
DB_PASSWORD="$(ler_env DB_PASSWORD)"

[ -n "$DB_NAME" ] || erro "DB_NAME não está definido em $ENV_FILE"
[ -n "$DB_USER" ] || erro "DB_USER não está definido em $ENV_FILE"

compose() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

compose ps --status running --services 2>/dev/null | grep -qx db \
    || erro "o serviço 'db' não está a correr"

echo "A validar $FICHEIRO…"

if ! compose exec -T db pg_restore --list /dev/stdin < "$FICHEIRO" > /dev/null 2>&1; then
    erro "o ficheiro não é um dump válido do PostgreSQL"
fi

# O par das fotografias, pelo carimbo do nome do dump. Sem carimbo legivel
# — um ficheiro renomeado a mao — nao ha par, e diz-se.
CARIMBO_DUMP="$(basename "$FICHEIRO" | sed -n 's/.*_\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}_[0-9]\{6\}\)\.dump$/\1/p')"
MEDIA_FICHEIRO=""

if [ -n "$CARIMBO_DUMP" ]; then
    CANDIDATO="$(dirname "$FICHEIRO")/pa_media_${CARIMBO_DUMP}.tar.gz"

    if [ -f "$CANDIDATO" ]; then
        if tar tzf "$CANDIDATO" > /dev/null 2>&1; then
            MEDIA_FICHEIRO="$CANDIDATO"
        else
            erro "o arquivo das fotografias $CANDIDATO esta ilegivel"
        fi
    fi
fi

TAMANHO="$(du -h "$FICHEIRO" | cut -f1)"
DATA="$(date -r "$FICHEIRO" '+%Y-%m-%d %H:%M' 2>/dev/null || echo 'desconhecida')"

cat <<AVISO

  Vai substituir por completo a base de dados "$DB_NAME".
  Todos os dados atuais serão apagados, incluindo marcações
  criadas depois desta cópia.

  Ficheiro : $FICHEIRO
  Tamanho  : $TAMANHO
  Data     : $DATA

AVISO

if [ -n "$MEDIA_FICHEIRO" ]; then
    echo "  As fotografias tambem sao substituidas, a partir de:"
    echo "    $MEDIA_FICHEIRO"
    echo
else
    echo "  ATENCAO: nao ha arquivo de fotografias para esta copia."
    echo "  A base sera restaurada e as imagens ficam as de agora — os casos"
    echo "  restaurados podem apontar para ficheiros que nao existem."
    echo
fi

read -r -p "Escreva o nome da base de dados para confirmar: " CONFIRMACAO

[ "$CONFIRMACAO" = "$DB_NAME" ] || erro "confirmação não corresponde; nada foi alterado"

mkdir -p "$BACKUP_DIR"
SEGURANCA="$BACKUP_DIR/pre-restauro_${DB_NAME}_$(date +%Y-%m-%d_%H%M%S).dump"

MEDIA_SEGURANCA="$BACKUP_DIR/pre-restauro_media_$(date +%Y-%m-%d_%H%M%S).tar.gz"

echo
echo "1/5 A guardar o estado atual em $SEGURANCA..."

if ! compose exec -T -e PGPASSWORD="$DB_PASSWORD" db \
    pg_dump -U "$DB_USER" -d "$DB_NAME" --format=custom --no-owner --no-privileges \
    > "$SEGURANCA"; then
    rm -f "$SEGURANCA"
    erro "não consegui guardar o estado atual; restauro cancelado"
fi

if [ -d "$MEDIA_DIR" ]; then
    if ! tar czf "$MEDIA_SEGURANCA" -C "$(dirname "$MEDIA_DIR")" "$(basename "$MEDIA_DIR")"; then
        rm -f "$MEDIA_SEGURANCA"
        erro "nao consegui guardar as fotografias atuais; restauro cancelado"
    fi

    echo "     fotografias atuais em $MEDIA_SEGURANCA"
fi

echo "2/5 A parar o servico web..."
compose stop web

# A partir daqui o web volta a subir mesmo que o restauro falhe: deixar o site
# em baixo por causa de um erro de restauro seria pior do que os dados antigos.
levantar_web() {
    echo "A levantar o serviço web…"
    compose start web || true
}
trap levantar_web EXIT

echo "3/5 A restaurar a base..."

if ! compose exec -T -e PGPASSWORD="$DB_PASSWORD" db \
    pg_restore -U "$DB_USER" -d "$DB_NAME" \
    --clean --if-exists --no-owner --no-privileges /dev/stdin < "$FICHEIRO"; then
    echo
    echo "O restauro falhou. O estado anterior está em:" >&2
    echo "  $SEGURANCA" >&2
    exit 1
fi

# --- As fotografias -----------------------------------------------------
#
# Extrai-se para uma pasta ao lado e so depois se troca. Extrair por cima da
# pasta a serio deixaria, se falhasse a meio, uma mistura das fotografias
# antigas com as novas — o pior dos dois estados, e sem forma de saber qual e
# qual.

if [ -n "$MEDIA_FICHEIRO" ]; then
    echo "4/5 A restaurar as fotografias..."

    TEMPORARIA="$(dirname "$MEDIA_DIR")/.media-restauro-$$"
    rm -rf "$TEMPORARIA"
    mkdir -p "$TEMPORARIA"

    if ! tar xzf "$MEDIA_FICHEIRO" -C "$TEMPORARIA"; then
        rm -rf "$TEMPORARIA"
        echo "AVISO: as fotografias nao foram restauradas; a base ja foi." >&2
        echo "       arquivo: $MEDIA_FICHEIRO" >&2
    else
        EXTRAIDA="$TEMPORARIA/$(basename "$MEDIA_DIR")"

        if [ -d "$EXTRAIDA" ]; then
            ANTIGA="$(dirname "$MEDIA_DIR")/.media-anterior-$$"
            rm -rf "$ANTIGA"

            [ -d "$MEDIA_DIR" ] && mv "$MEDIA_DIR" "$ANTIGA"
            mv "$EXTRAIDA" "$MEDIA_DIR"
            rm -rf "$ANTIGA"

            QUANTAS="$(find "$MEDIA_DIR" -type f | wc -l)"
            echo "     $QUANTAS ficheiro(s) restaurado(s) em $MEDIA_DIR"
        else
            echo "AVISO: o arquivo nao continha a pasta esperada." >&2
        fi

        rm -rf "$TEMPORARIA"
    fi
else
    echo "4/5 Sem arquivo de fotografias — as imagens ficam como estao."
fi

trap - EXIT

echo "5/5 A levantar o web e a aplicar migrations..."
compose start web
compose exec -T web python manage.py migrate --no-input

echo
echo "Restauro concluido a partir de $FICHEIRO."
echo "Estado anterior da base : $SEGURANCA"

if [ -f "$MEDIA_SEGURANCA" ]; then
    echo "Fotografias anteriores  : $MEDIA_SEGURANCA"
fi
