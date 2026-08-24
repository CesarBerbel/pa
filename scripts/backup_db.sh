#!/usr/bin/env bash
#
# Cópia de segurança de produção: a base de dados e as fotografias.
#
#   ./scripts/backup_db.sh
#
# Gera DOIS ficheiros em backups/, com o mesmo carimbo de data e hora:
#
#   pa_<base>_<carimbo>.dump        a base, no formato próprio do PostgreSQL
#   pa_media_<carimbo>.tar.gz       a pasta media/, com as fotografias
#
# São um par, e é de propósito. As fotografias do "antes e depois" vivem em
# ficheiros e não na base: restaurar só a base devolve os registos com as
# legendas e sem as imagens, e a página fica com <img> a apontar para
# ficheiros que já não existem. O carimbo comum é o que permite ao restauro
# encontrar as duas metades do mesmo momento.
#
# Variáveis de ambiente aceites:
#   PROJECT_DIR     raiz do projeto no servidor        (default: diretoria do script)
#   ENV_FILE        ficheiro de variáveis              (default: $PROJECT_DIR/.env.prod)
#   BACKUP_DIR      onde guardar                       (default: $PROJECT_DIR/backups)
#   MEDIA_DIR       pasta das fotografias              (default: $PROJECT_DIR/media)
#   RETENTION_DAYS  dias a manter, 0 desliga a limpeza (default: 30)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_DIR="${PROJECT_DIR:-$(dirname "$SCRIPT_DIR")}"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env.prod}"
COMPOSE_FILE="${COMPOSE_FILE:-$PROJECT_DIR/docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
MEDIA_DIR="${MEDIA_DIR:-$PROJECT_DIR/media}"
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
echo "Base copiada: $DESTINO ($TAMANHO)"

# --- As fotografias -----------------------------------------------------
#
# Mesmo carimbo do dump: e assim que o restauro sabe que as duas metades sao
# do mesmo momento. Uma pasta vazia continua a gerar arquivo — o vazio tambem
# e um estado, e a falta do ficheiro seria lida como copia incompleta.

MEDIA_DESTINO="$BACKUP_DIR/pa_media_${CARIMBO}.tar.gz"
MEDIA_PARCIAL="$MEDIA_DESTINO.parcial"

if [ -d "$MEDIA_DIR" ]; then
    echo "A copiar as fotografias de $MEDIA_DIR..."

    if ! tar czf "$MEDIA_PARCIAL" -C "$(dirname "$MEDIA_DIR")" "$(basename "$MEDIA_DIR")"; then
        rm -f "$MEDIA_PARCIAL"
        erro "nao consegui arquivar $MEDIA_DIR; a copia da base fica sem par"
    fi

    # A mesma regra do dump: so passa a definitivo depois de se conseguir ler.
    if ! tar tzf "$MEDIA_PARCIAL" > /dev/null 2>&1; then
        rm -f "$MEDIA_PARCIAL"
        erro "o arquivo das fotografias saiu ilegivel; foi descartado"
    fi

    mv "$MEDIA_PARCIAL" "$MEDIA_DESTINO"

    MEDIA_TAMANHO="$(du -h "$MEDIA_DESTINO" | cut -f1)"
    echo "Fotografias copiadas: $MEDIA_DESTINO ($MEDIA_TAMANHO)"
else
    echo "AVISO: $MEDIA_DIR nao existe - a copia leva so a base." >&2
fi

if [ "$RETENTION_DAYS" -gt 0 ]; then
    # As duas metades saem juntas. Apagar so os dumps deixaria arquivos de
    # fotografias orfaos a crescer para sempre; apagar so as fotografias
    # deixaria dumps que restauram registos sem imagens.
    APAGADAS="$(find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'pa_*.dump' -o -name 'pa_media_*.tar.gz' \) \
        -mtime "+$RETENTION_DAYS" -print -delete | wc -l)"

    if [ "$APAGADAS" -gt 0 ]; then
        echo "Removidos $APAGADAS ficheiro(s) com mais de $RETENTION_DAYS dias."
    fi
fi

TOTAL="$(find "$BACKUP_DIR" -maxdepth 1 -name 'pa_*.dump' -type f | wc -l)"
echo "Total de cópias guardadas: $TOTAL"
