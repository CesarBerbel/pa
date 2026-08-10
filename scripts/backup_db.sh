#!/usr/bin/env bash
#
# Cópia de segurança da base de dados PostgreSQL de produção.
#
#   ./scripts/backup_db.sh
#
# Gera um ficheiro em backups/ com data e hora, no formato próprio do
# PostgreSQL (-Fc), que já vem comprimido e permite restauro seletivo.
#
# Variáveis de ambiente aceites:
#   PROJECT_DIR     raiz do projeto no servidor        (default: diretoria do script)
#   ENV_FILE        ficheiro de variáveis              (default: $PROJECT_DIR/.env.prod)
#   BACKUP_DIR      onde guardar                       (default: $PROJECT_DIR/backups)
#   RETENTION_DAYS  dias a manter, 0 desliga a limpeza (default: 30)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_DIR="${PROJECT_DIR:-$(dirname "$SCRIPT_DIR")}"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env.prod}"
COMPOSE_FILE="${COMPOSE_FILE:-$PROJECT_DIR/docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

erro() {
    echo "ERRO: $*" >&2
    exit 1
}

[ -f "$ENV_FILE" ] || erro "não encontrei $ENV_FILE"
[ -f "$COMPOSE_FILE" ] || erro "não encontrei $COMPOSE_FILE"

# Lê uma chave do .env sem fazer source: o ficheiro tem segredos com
# caracteres que o shell interpretaria.
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

mkdir -p "$BACKUP_DIR"

CARIMBO="$(date +%Y-%m-%d_%H%M%S)"
DESTINO="$BACKUP_DIR/pa_${DB_NAME}_${CARIMBO}.dump"
PARCIAL="$DESTINO.parcial"

echo "A criar cópia de $DB_NAME…"

# -T desliga o TTY, sem o qual o redirecionamento traz lixo para o ficheiro.
if ! compose exec -T -e PGPASSWORD="$DB_PASSWORD" db \
    pg_dump -U "$DB_USER" -d "$DB_NAME" --format=custom --no-owner --no-privileges \
    > "$PARCIAL"; then
    rm -f "$PARCIAL"
    erro "o pg_dump falhou; nada foi guardado"
fi

# Só passa a definitivo depois de o conteúdo ser validado: um ficheiro
# truncado com o nome certo é pior do que não ter cópia nenhuma.
if ! pg_restore --list "$PARCIAL" > /dev/null 2>&1; then
    if ! compose exec -T db pg_restore --list /dev/stdin < "$PARCIAL" > /dev/null 2>&1; then
        rm -f "$PARCIAL"
        erro "a cópia gerada não é um dump válido; foi descartada"
    fi
fi

mv "$PARCIAL" "$DESTINO"

TAMANHO="$(du -h "$DESTINO" | cut -f1)"
echo "Cópia criada: $DESTINO ($TAMANHO)"

if [ "$RETENTION_DAYS" -gt 0 ]; then
    APAGADAS="$(find "$BACKUP_DIR" -maxdepth 1 -name 'pa_*.dump' -type f \
        -mtime "+$RETENTION_DAYS" -print -delete | wc -l)"

    if [ "$APAGADAS" -gt 0 ]; then
        echo "Removidas $APAGADAS cópia(s) com mais de $RETENTION_DAYS dias."
    fi
fi

TOTAL="$(find "$BACKUP_DIR" -maxdepth 1 -name 'pa_*.dump' -type f | wc -l)"
echo "Total de cópias guardadas: $TOTAL"
