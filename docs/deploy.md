# Deploy em produção

Comandos para atualizar e subir os projetos em produção via Docker Compose.

## PA (este projeto)

```bash
cd /opt/pa && git pull && docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

## Pocket

```bash
cd /opt/pocket && git pull && docker compose -f docker-compose.prod.yml up -d --build
```

## O que cada comando faz

1. `cd` até a pasta do projeto no servidor.
2. `git pull` — traz as últimas alterações da branch atual.
3. `docker compose ... up -d --build` — reconstrói as imagens alteradas e sobe os containers atualizados em background (`-d`).

No caso do PA, `--env-file .env.prod` aponta explicitamente para o arquivo de variáveis de ambiente de produção (diferente do `.env` local de desenvolvimento).

---

# Cópias de segurança da base de dados

A base de dados é o estado todo da aplicação: nenhum modelo guarda ficheiros,
por isso não há media a proteger em separado. Perder a base é perder as
marcações, os clientes e o histórico.

Os dois scripts leem as credenciais do `.env.prod`, portanto não há palavras-passe
escritas em lado nenhum.

## Criar uma cópia

```bash
cd /opt/pa && ./scripts/backup_db.sh
```

Gera `backups/pa_<base>_<data>_<hora>.dump` no formato próprio do PostgreSQL,
que já vem comprimido e permite restauro seletivo.

O script **valida o dump antes de o dar como bom**: escreve para um ficheiro
`.parcial`, confirma com `pg_restore --list` que o conteúdo é legível e só então
lhe dá o nome definitivo. Um ficheiro truncado com o nome certo é pior do que
não haver cópia, porque só se descobre no dia em que é precisa.

Apaga automaticamente cópias com mais de 30 dias. Para mudar:

```bash
RETENTION_DAYS=90 ./scripts/backup_db.sh
```

## Automatizar

Uma cópia diária às 3 da manhã, com registo:

```bash
sudo crontab -e
```

```cron
0 3 * * * cd /opt/pa && ./scripts/backup_db.sh >> /var/log/pa-backup.log 2>&1
```

Vale confirmar de vez em quando que o cron está mesmo a correr:

```bash
ls -lh /opt/pa/backups/ | tail -5
tail -20 /var/log/pa-backup.log
```

**As cópias ficam no mesmo servidor que a base.** Isso protege contra erro
humano e contra um restauro falhado, mas não contra perder o VPS. Se quiser
proteção real, sincronize a pasta para fora da máquina — por exemplo com
`rclone` ou `scp` para outro destino, num segundo cron.

## Restaurar

```bash
cd /opt/pa && ./scripts/restore_db.sh backups/pa_pa_2026-08-10_030000.dump
```

Isto **apaga os dados atuais**. O script protege-se disso em três camadas:

1. valida o ficheiro antes de mexer em nada;
2. pede que escreva o nome da base de dados para confirmar — não aceita "sim"
   nem `-y`, para não ser executado por reflexo;
3. guarda o estado atual em `backups/pre-restauro_*.dump` antes de restaurar.

Durante o restauro o serviço `web` é parado, para que nenhuma marcação entre a
meio. Se o restauro falhar, o `web` volta a subir sozinho e o caminho da cópia
de segurança é impresso no ecrã.

No fim aplica as migrations, para o caso de a cópia ser anterior a alterações de
esquema já presentes no código.

## Testar o restauro

Uma cópia que nunca foi restaurada é uma suposição, não uma garantia. De tempos
a tempos vale a pena confirmar que um dump abre, sem tocar em produção:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
    psql -U "$DB_USER" -c 'CREATE DATABASE teste_restauro;'

docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
    pg_restore -U "$DB_USER" -d teste_restauro --no-owner /dev/stdin < backups/<ficheiro>.dump

docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
    psql -U "$DB_USER" -d teste_restauro -c 'SELECT count(*) FROM appointments_appointment;'

docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
    psql -U "$DB_USER" -c 'DROP DATABASE teste_restauro;'
```

---

# Domínio principal e domínios alternativos

O site responde em `priarantes.com` e `priarantes.cloud`. Só **um** deles pode
ser o canónico: servir o mesmo conteúdo em dois domínios divide os sinais de
SEO entre eles, e o Google trata-os como conteúdo duplicado.

**Domínio canónico: `priarantes.com`.** O `.cloud` redireciona para ele.

Razões: o `.com` é o que as pessoas escrevem à mão, o `.cloud` é um TLD técnico
pouco natural num negócio de saúde, e o site tem pouca indexação — trocar agora
é barato, mais tarde deixa de ser.

## O que hoje está errado

O `priarantes.com` está com **encaminhamento de domínio no registador**, que
responde `301` para a raiz do `.cloud` e **perde o caminho**:

```
https://priarantes.com/servicos/feed/   ->   https://priarantes.cloud/
```

Isto tem duas consequências: qualquer ligação para uma página interna aterra na
homepage, e os links de marcação enviados por email (`/m/<token>/`) deixariam de
funcionar se alguma vez usassem esse domínio.

## Ordem de execução

A ordem importa. Cada passo assume o anterior concluído, e assim não há nenhum
momento em que o domínio canónico aponte para algo que ainda não responde.

### 1. DNS (Hostinger)

O `priarantes.com` está na Hostinger e **já tem registos de endereço**, mas a
apontar para o servidor de encaminhamento deles, não para o VPS:

| Tipo | Nome | Valor atual |
|------|------|-------------|
| `A` | `@` | `76.13.61.104` |
| `AAAA` | `@` | `2a02:4780:84::32` |

Obter os endereços reais do VPS:

```bash
curl -4 ifconfig.me   # IPv4
curl -6 ifconfig.me   # IPv6, se o VPS tiver
```

Depois, na zona DNS da Hostinger:

- **editar o `A` de `@`** para o IPv4 do VPS;
- **editar o `AAAA` de `@`** para o IPv6 do VPS — ou **apagá-lo**, se o VPS não
  tiver IPv6;
- verificar em *Websites → Redirecionamentos* do hPanel se existe um
  redirecionamento ativo para o `.cloud` e removê-lo.

O `CNAME` de `www` já aponta para `priarantes.com` e acompanha o apex
automaticamente: não é preciso mexer.

#### O registo AAAA é a armadilha

Se editar só o `A` e deixar o `AAAA` a apontar para a Hostinger, os visitantes
com IPv6 — a maioria dos telemóveis em rede móvel — continuam a ser
redirecionados para o `.cloud`, enquanto no computador tudo parece funcionar. O
sintoma é intermitente e leva horas a diagnosticar. **Os dois registos têm de
apontar para o mesmo sítio, ou o AAAA não deve existir.**

#### Não tocar nestes registos

Estes servem o email de `@priarantes.com`, incluindo os emails de marcação que a
aplicação envia. Apagá-los ou alterá-los derruba o correio:

- `MX` → `mx1.hostinger.com` (5) e `mx2.hostinger.com` (10)
- `CNAME` → `hostingermail-a/b/c._domainkey` (assinatura DKIM)
- `CNAME` → `autodiscover` e `autoconfig`

O `TXT` com `google-site-verification=...` também fica: é o que mantém o domínio
verificado no Google Search Console, e vai dar jeito no passo 6.

#### Confirmar antes de seguir

```bash
dig +short A    priarantes.com
dig +short AAAA priarantes.com
dig +short A    priarantes.cloud   # tem de devolver o mesmo IPv4
```

A propagação pode demorar até ao TTL do registo — `1800` segundos, meia hora.

### 2. Caddy: aceitar o novo domínio

O proxy do host é o **Caddy**. O `nginx` que aparece no `docker ps` é interno do
Pocket e serve apenas o frontend dele em `127.0.0.1:8080` — não trata de TLS nem
de domínios.

Confirmar onde está a configuração:

```bash
systemctl cat caddy | grep -E "ExecStart"
# normalmente: /etc/caddy/Caddyfile
```

Ver o mapa atual de domínios e destinos antes de mexer:

```bash
grep -nE "^[a-z0-9.,* ]+\{|reverse_proxy" /etc/caddy/Caddyfile
```

Acrescentar os nomes `.com` ao bloco do PA — o que faz `reverse_proxy` para
`127.0.0.1:8001`. Não tocar no bloco do Pocket, que aponta para `:8080`:

```caddyfile
# /etc/caddy/Caddyfile
priarantes.com, www.priarantes.com, priarantes.cloud, www.priarantes.cloud {
    reverse_proxy 127.0.0.1:8001
}
```

Validar e recarregar sem derrubar o outro site:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

O Caddy pede e renova os certificados automaticamente na primeira visita a cada
domínio novo. **Não é preciso certbot.** Se o certificado não sair, é quase
sempre porque o DNS do passo 1 ainda não propagou — o Let's Encrypt precisa de
resolver o domínio para este servidor.

Acompanhar a emissão:

```bash
sudo journalctl -u caddy -f | grep -iE "certificate|obtain|error"
```

### 2b. Sobre hosts desconhecidos

Num nginx, um pedido cujo `Host` não corresponda a nenhum `server_name` cai no
primeiro bloco carregado — e é assim que um domínio acaba a mostrar o site
errado. **O Caddy não se comporta assim:** faz correspondência exata por nome e,
para um host que não conste do Caddyfile, nem sequer tem certificado para
apresentar, pelo que a ligação falha no handshake em vez de servir outro site.

Ou seja, aqui não é preciso nenhum bloco por omissão. Basta garantir que cada
domínio aparece exatamente num bloco.

### 3. Django: autorizar os domínios

No `.env.prod`, **sem mexer ainda no `SITE_URL`**:

```ini
ALLOWED_HOSTS=priarantes.com,www.priarantes.com,priarantes.cloud,www.priarantes.cloud
CSRF_TRUSTED_ORIGINS=https://priarantes.com,https://www.priarantes.com,https://priarantes.cloud,https://www.priarantes.cloud
SECURE_PROXY_SSL_HEADER=True
SECURE_SSL_REDIRECT=True
```

Sem `ALLOWED_HOSTS` o Django devolve **400 Bad Request** ao domínio novo. Sem
`CSRF_TRUSTED_ORIGINS` a submissão do formulário de marcação falha.

`SECURE_SSL_REDIRECT=True` **exige** `SECURE_PROXY_SSL_HEADER=True`: sem ele o
Django não reconhece o HTTPS terminado no proxy e entra em ciclo infinito de
redirecionamentos.

Aplicar e verificar que os dois domínios servem o site:

```bash
cd /opt/pa && docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
curl -I https://priarantes.com/
curl -I https://priarantes.cloud/
```

### 4. Trocar o domínio canónico

Só agora, com o `.com` confirmado a responder. No `.env.prod`:

```ini
SITE_URL=https://priarantes.com
```

Isto ajusta de uma vez a tag `canonical`, o `sitemap.xml`, o `robots.txt`, as
tags `hreflang` e os links dos emails de marcação. Reconstruir e confirmar:

```bash
cd /opt/pa && docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
curl -s https://priarantes.com/sitemap.xml | grep loc
```

### 5. Redirecionar o `.cloud`, preservando o caminho

Separar os dois domínios em blocos distintos no Caddyfile: o `.com` continua a
servir a aplicação, o `.cloud` passa só a redirecionar.

```caddyfile
# /etc/caddy/Caddyfile
priarantes.com, www.priarantes.com {
    reverse_proxy 127.0.0.1:8001
}

priarantes.cloud, www.priarantes.cloud {
    # {uri} preserva o caminho e a query string.
    redir https://priarantes.com{uri} permanent
}
```

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

O `{uri}` é o detalhe que resolve o problema original. Sem ele repete-se o
comportamento do registador: tudo cai na homepage. Com ele, os links de marcação
já enviados por email continuam a abrir a marcação certa.

O Caddy mantém o certificado do `.cloud` a renovar sozinho enquanto o domínio
constar do Caddyfile — e ele é preciso, porque o TLS acontece antes do
redirecionamento. Se retirasse o `.cloud` do ficheiro, o certificado deixaria de
renovar e os visitantes apanhariam um aviso de segurança em vez de serem
reencaminhados.

Confirmar que o caminho sobrevive:

```bash
curl -I https://priarantes.cloud/servicos/feed/
# Location: https://priarantes.com/servicos/feed/
```

### 6. Google Search Console

- adicionar a propriedade `priarantes.com` e verificá-la;
- submeter `https://priarantes.com/sitemap.xml`;
- se o `.cloud` já estiver verificado, usar a **Alteração de endereço** para
  transferir os sinais acumulados;
- pedir indexação da homepage pela Inspeção de URL.

### 7. Atualizar o domínio onde ele aparece

Google Business Profile, Instagram, cartões e diretórios. Para pesquisa local, a
consistência entre estes registos e o site é um fator de posicionamento.
