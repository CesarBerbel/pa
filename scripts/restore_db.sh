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
# Sequência:
#   1. valida o ficheiro
#   2. pede confirmação
#   3. copia o estado atual para backups/
#   4. para o serviço web, para ninguém escrever a meio
#   5. restaura
#   6. levanta o web e aplica migrations
#
# Variáveis de ambiente aceites: PROJECT_DIR, ENV_FILE, COMPOSE_FILE, BACKUP_DIR

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_DIR="${PROJECT_DIR:-$(dirname "$SCRIPT_DIR")}"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env.prod}"
COMPOSE_FILE="${COMPOSE_FILE:-$PROJECT_DIR/docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"

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

read -r -p "Escreva o nome da base de dados para confirmar: " CONFIRMACAO

[ "$CONFIRMACAO" = "$DB_NAME" ] || erro "confirmação não corresponde; nada foi alterado"

mkdir -p "$BACKUP_DIR"
SEGURANCA="$BACKUP_DIR/pre-restauro_${DB_NAME}_$(date +%Y-%m-%d_%H%M%S).dump"

echo
echo "1/4 A guardar o estado atual em $SEGURANCA…"

if ! compose exec -T -e PGPASSWORD="$DB_PASSWORD" db \
    pg_dump -U "$DB_USER" -d "$DB_NAME" --format=custom --no-owner --no-privileges \
    > "$SEGURANCA"; then
    rm -f "$SEGURANCA"
    erro "não consegui guardar o estado atual; restauro cancelado"
fi

echo "2/4 A parar o serviço web…"
compose stop web

# A partir daqui o web volta a subir mesmo que o restauro falhe: deixar o site
# em baixo por causa de um erro de restauro seria pior do que os dados antigos.
levantar_web() {
    echo "A levantar o serviço web…"
    compose start web || true
}
trap levantar_web EXIT

echo "3/4 A restaurar…"

if ! compose exec -T -e PGPASSWORD="$DB_PASSWORD" db \
    pg_restore -U "$DB_USER" -d "$DB_NAME" \
    --clean --if-exists --no-owner --no-privileges /dev/stdin < "$FICHEIRO"; then
    echo
    echo "O restauro falhou. O estado anterior está em:" >&2
    echo "  $SEGURANCA" >&2
    exit 1
fi

trap - EXIT

echo "4/4 A levantar o web e a aplicar migrations…"
compose start web
compose exec -T web python manage.py migrate --no-input

echo
echo "Restauro concluído a partir de $FICHEIRO."
echo "Cópia do estado anterior: $SEGURANCA"
