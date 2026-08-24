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
# A cópia fica cifrada e sai do servidor, quando houver como. As duas coisas
# são opcionais e nenhuma delas pode fazer falhar a cópia local: uma cópia em
# claro no mesmo disco continua a ser melhor do que cópia nenhuma. Sem as
# variáveis, o script faz o que sempre fez e avisa no stderr.
#
# Variáveis de ambiente aceites:
#   PROJECT_DIR     raiz do projeto no servidor        (default: diretoria do script)
#   ENV_FILE        ficheiro de variáveis              (default: $PROJECT_DIR/.env.prod)
#   BACKUP_DIR      onde guardar                       (default: $PROJECT_DIR/backups)
#   MEDIA_DIR       pasta das fotografias              (default: $PROJECT_DIR/media)
#   RETENTION_DAYS  dias a manter, 0 desliga a limpeza (default: 30)
#
#   BACKUP_AGE_RECIPIENT  chave pública `age` (age1...). Cifra as duas cópias.
#   BACKUP_PASSPHRASE     passphrase para `gpg --symmetric`, usada só quando
#                         não houver BACKUP_AGE_RECIPIENT
#   BACKUP_REMOTE         destino do `rclone` para onde enviar, por exemplo
#                         `b2:pa-backups` ou `drive:copias/pa`
#   RCLONE_CONFIG         ficheiro de configuração do rclone, quando o script
#                         corre pelo cron e não encontra o do utilizador
#
# Nem a chave nem a passphrase se escrevem aqui: vêm do ambiente, para não
# ficarem no git nem no `ps`. Com `age`, o servidor só tem a chave pública —
# cifra, mas não decifra: quem lhe puser as mãos em cima não abre as cópias.
#
# Restaurar uma cópia cifrada passa por decifrar primeiro:
#   age --decrypt -i chave.txt -o copia.dump copia.dump.age
#   gpg --decrypt --output copia.dump copia.dump.gpg

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_DIR="${PROJECT_DIR:-$(dirname "$SCRIPT_DIR")}"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env.prod}"
COMPOSE_FILE="${COMPOSE_FILE:-$PROJECT_DIR/docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
MEDIA_DIR="${MEDIA_DIR:-$PROJECT_DIR/media}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

# `:-` em todas: com `set -u`, ler uma variável não definida abortava o script,
# e estas são precisamente as que costumam não estar definidas.
BACKUP_AGE_RECIPIENT="${BACKUP_AGE_RECIPIENT:-}"
BACKUP_PASSPHRASE="${BACKUP_PASSPHRASE:-}"
BACKUP_REMOTE="${BACKUP_REMOTE:-}"

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

aviso() {
    echo "AVISO: $*" >&2
}

# --- Cifra ------------------------------------------------------------------
#
# O dump traz as fichas de anamnese e o histórico clínico: categoria especial
# de dados (RGPD, artigo 9.º). Em claro, basta ler o ficheiro para os ter
# todos — e ele está prestes a sair do servidor.
#
# `age` primeiro, porque cifra com uma chave pública: o servidor não guarda a
# chave que decifra, por isso quem lhe puser as mãos em cima não abre nem
# estas cópias nem as antigas. Sem `age`, `gpg --symmetric` com uma passphrase
# do ambiente, que protege o ficheiro mas obriga o servidor a conhecer o
# segredo. Sem nenhum dos dois, a cópia fica em claro: é pior, mas é melhor do
# que não haver cópia — que é o que aconteceria se isto fosse um erro fatal.

MODO_CIFRA="nenhum"

if [ -n "$BACKUP_AGE_RECIPIENT" ]; then
    if command -v age > /dev/null 2>&1; then
        MODO_CIFRA="age"
    else
        aviso "BACKUP_AGE_RECIPIENT está definido mas o 'age' não está instalado; as cópias ficam em claro."
    fi
elif [ -n "$BACKUP_PASSPHRASE" ]; then
    if command -v gpg > /dev/null 2>&1; then
        MODO_CIFRA="gpg"
    else
        aviso "BACKUP_PASSPHRASE está definida mas o 'gpg' não está instalado; as cópias ficam em claro."
    fi
else
    aviso "sem BACKUP_AGE_RECIPIENT nem BACKUP_PASSPHRASE: as cópias ficam em claro, com dados clínicos legíveis."
fi

# Devolve em CIFRADO o caminho a usar daqui para a frente: o ficheiro cifrado
# quando correu bem, o original quando não há como cifrar ou a cifra falhou.
CIFRADO=""

cifrar() {
    local origem="$1"
    local destino

    CIFRADO="$origem"

    case "$MODO_CIFRA" in
        age)
            destino="$origem.age"

            # A mesma regra do dump e do tar: `.parcial` primeiro, definitivo
            # só depois de sair inteiro. Um ficheiro cifrado meio escrito não
            # se queixa ao ser guardado — queixa-se no dia em que for preciso.
            if ! age -r "$BACKUP_AGE_RECIPIENT" -o "$destino.parcial" "$origem"; then
                rm -f "$destino.parcial"
                aviso "não consegui cifrar $(basename "$origem") com o age; fica em claro."
                return 0
            fi
            ;;
        gpg)
            destino="$origem.gpg"

            # A passphrase entra pelo stdin e não pela linha de comandos: em
            # `--passphrase` ficava visível a qualquer utilizador da máquina
            # que corresse `ps`.
            if ! printf '%s' "$BACKUP_PASSPHRASE" | gpg --batch --yes --quiet --symmetric --cipher-algo AES256 --passphrase-fd 0 --output "$destino.parcial" "$origem"; then
                rm -f "$destino.parcial"
                aviso "não consegui cifrar $(basename "$origem") com o gpg; fica em claro."
                return 0
            fi
            ;;
        *)
            return 0
            ;;
    esac

    mv "$destino.parcial" "$destino"

    # O original em claro sai do disco: mantê-lo ao lado do cifrado tornava a
    # cifra decorativa.
    rm -f "$origem"

    CIFRADO="$destino"
}

# --- Envio para fora do servidor --------------------------------------------
#
# Até aqui a cópia vivia no mesmo disco da base que copia: perder a máquina era
# perder as duas coisas no mesmo instante. O `rclone` serve qualquer destino
# (S3, B2, Drive, outro servidor por SFTP) sem o script ter de saber qual.
#
# Falhar o envio nunca é fatal: a cópia local já está feita e validada, e é ela
# que não se pode perder por causa de uma rede em baixo.

if [ -z "$BACKUP_REMOTE" ]; then
    aviso "BACKUP_REMOTE não está definido: as cópias ficam só neste servidor."
elif ! command -v rclone > /dev/null 2>&1; then
    aviso "BACKUP_REMOTE está definido mas o 'rclone' não está instalado; as cópias ficam só neste servidor."
    BACKUP_REMOTE=""
fi

enviar() {
    local ficheiro="$1"

    [ -n "$BACKUP_REMOTE" ] || return 0

    echo "A enviar $(basename "$ficheiro") para $BACKUP_REMOTE…"

    if ! rclone copy --no-traverse "$ficheiro" "$BACKUP_REMOTE"; then
        aviso "o envio de $(basename "$ficheiro") falhou; a cópia local ficou guardada."
    fi
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

# A validação acima corre sobre o ficheiro em claro, e tem de ser por esta
# ordem: o `pg_restore --list` não sabe ler um ficheiro cifrado. Primeiro
# provar que o dump presta, só depois fechá-lo.
cifrar "$DESTINO"
DESTINO="$CIFRADO"

TAMANHO="$(du -h "$DESTINO" | cut -f1)"
echo "Base copiada: $DESTINO ($TAMANHO)"

enviar "$DESTINO"

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

    cifrar "$MEDIA_DESTINO"
    MEDIA_DESTINO="$CIFRADO"

    MEDIA_TAMANHO="$(du -h "$MEDIA_DESTINO" | cut -f1)"
    echo "Fotografias copiadas: $MEDIA_DESTINO ($MEDIA_TAMANHO)"

    enviar "$MEDIA_DESTINO"
else
    echo "AVISO: $MEDIA_DIR nao existe - a copia leva so a base." >&2
fi

if [ "$RETENTION_DAYS" -gt 0 ]; then
    # Os `*` no fim de cada padrão apanham os sufixos da cifra (.age, .gpg):
    # sem eles a limpeza deixava de ver as cópias assim que passassem a ser
    # cifradas, e o disco enchia-se em silêncio.
    #
    # As duas metades saem juntas. Apagar so os dumps deixaria arquivos de
    # fotografias orfaos a crescer para sempre; apagar so as fotografias
    # deixaria dumps que restauram registos sem imagens.
    APAGADAS="$(find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'pa_*.dump*' -o -name 'pa_media_*.tar.gz*' \) \
        -mtime "+$RETENTION_DAYS" -print -delete | wc -l)"

    if [ "$APAGADAS" -gt 0 ]; then
        echo "Removidos $APAGADAS ficheiro(s) com mais de $RETENTION_DAYS dias."
    fi
fi

TOTAL="$(find "$BACKUP_DIR" -maxdepth 1 -type f \
    \( -name 'pa_*.dump' -o -name 'pa_*.dump.age' -o -name 'pa_*.dump.gpg' \) | wc -l)"
echo "Total de cópias guardadas: $TOTAL"

# A limpeza acima é só a deste disco. O que já foi enviado fica no destino
# remoto até alguém o apagar lá, e é de propósito: a cópia de fora existe
# para sobreviver a esta máquina, incluindo a um `find -delete` que corra
# nela por engano.
if [ -n "$BACKUP_REMOTE" ]; then
    echo "Cópias enviadas para $BACKUP_REMOTE (a retenção lá define-se no destino)."
fi
