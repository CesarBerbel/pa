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

## WhatsApp pelo Baileys

O compose do PA inclui o serviço `baileys`, que mantém a ligação ao WhatsApp e
sobe com o mesmo comando acima. Da primeira vez é preciso acrescentar variáveis
ao `.env.prod` e emparelhar o número lendo um QR code no site.

Os passos, o que fazer quando a ligação cai e os riscos de usar uma via não
oficial estão em [baileys_whatsapp.md](baileys_whatsapp.md).

A sessão emparelhada fica no volume `pa_baileys_auth` e **sobrevive a deploys**:
um `up -d --build` não obriga a ler o QR code outra vez.

## Variáveis novas não viajam no `git pull`

O `.env.prod` vive **só no servidor** e está no `.gitignore`. Quando uma
funcionalidade nova traz variáveis novas, o `git pull` traz o código mas não as
variáveis: a funcionalidade fica em silêncio em produção enquanto funciona em
desenvolvimento. Depois de cada deploy que estreie uma funcionalidade, comparar
o `.env.prod` com o `.env.example` e acrescentar o que falta.

## Fotografias do antes e depois

As fotografias carregadas na área interna são servidas pelo Django, em
`/media/`. O `whitenoise` serve apenas o `STATIC_ROOT`, que é outra pasta, e o
Caddy encaminha tudo para o Django — não havia mais ninguém para as servir.

Isso é suficiente para as poucas imagens de uma página que raramente é aberta
por muita gente ao mesmo tempo. Se um dia forem muitas, o Caddy serve-as sem
passar pelo Django, acrescentando ao bloco do site:

```
handle /media/* {
    root * /opt/pa
    file_server
}
```

As fotografias não estão no git (`media/` está no `.gitignore`) e vivem em
`/opt/pa/media`. Um `up --build` não lhes toca — a pasta é montada de fora do
contentor — mas uma máquina nova começa sem elas: têm de vir da cópia de
segurança.

### O contentor deixou de correr como root

O `Dockerfile` cria o utilizador `pa`, com UID 1000, e o gunicorn corre com
esse. Como `/opt/pa/media` é montada de fora, quem manda nas permissões é o
anfitrião: se a pasta for de `root`, o carregamento de fotografias na área
interna deixa de conseguir escrever.

Uma vez, no servidor:

```bash
sudo chown -R 1000:1000 /opt/pa/media
ls -ld /opt/pa/media          # tem de dizer 1000 ou o nome do utilizador com esse UID
```

Se o dono de `/opt/pa` tiver outro UID, passa-se na construção em vez de mudar
a pasta:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml build     --build-arg APP_UID=$(id -u) --build-arg APP_GID=$(id -g) web
```

Confirmar depois do deploy, carregando uma fotografia em *Antes e depois*. Um
erro de permissões aparece nos registos como `PermissionError: [Errno 13]`:

```bash
docker compose -f docker-compose.prod.yml logs web | grep -i "permission"
```

## Avaliações do Google

A secção de avaliações da página inicial só aparece com as duas variáveis
preenchidas. Sem elas — ou com uma só — a página desenha-se na mesma e a secção
não existe, que é o que se vê quando o `.env.prod` ficou para trás.

```bash
# no servidor, em /opt/pa/.env.prod
GOOGLE_PLACES_API_KEY=...
GOOGLE_PLACE_ID=ChIJceu6jmD5Ig0RnOXzF6FgzrM
```

A chamada é feita **pelo servidor**, não pelo navegador. Isso decide como a
chave pode ser restringida na consola da Google:

* **Restrição por endereço IP** (o IP público do servidor), ou sem restrição.
* **Restrição por referenciador HTTP não serve** — não há referenciador num
  pedido feito pelo Django, e a Google devolve 403.
* Nas restrições de API, a **Places API (New)** tem de estar na lista.

Depois de editar o `.env.prod`, é preciso recriar o contentor — mudar o
ficheiro não chega, as variáveis são lidas no arranque:

```bash
cd /opt/pa && docker compose --env-file .env.prod -f docker-compose.prod.yml up -d web
```

As avaliações ficam em cache seis horas, e uma falha fica cinco minutos. Se a
secção continuar sem aparecer, a razão está nos registos, em texto:

```bash
docker compose -f docker-compose.prod.yml logs web | grep "Avaliações do Google"
```

---

# Cópias de segurança da base de dados

A base de dados guarda quase todo o estado da aplicação: perdê-la é perder as
marcações, os clientes e o histórico.

**Deixou de ser tudo.** Os casos "antes e depois" trazem fotografias
carregadas na área interna, e essas vivem em ficheiros, não na base. Uma cópia
da base sozinha restaura os registos com as legendas e sem as fotografias — os
`<img>` da página apontariam para ficheiros que já não existem.

Os scripts tratam disso: **cada cópia são dois ficheiros com o mesmo carimbo**,
e o restauro encontra o par sozinho.

```
backups/pa_pa_2026-08-24_030000.dump        a base
backups/pa_media_2026-08-24_030000.tar.gz   as fotografias
```

Os dois scripts leem as credenciais do `.env.prod`, portanto não há palavras-passe
escritas em lado nenhum.

## Criar uma cópia

```bash
cd /opt/pa && ./scripts/backup_db.sh
```

Gera os dois ficheiros: o dump no formato próprio do PostgreSQL, que já vem
comprimido e permite restauro seletivo, e o arquivo da pasta `media/`.

O script **valida os dois antes de os dar como bons**: escreve para ficheiros
`.parcial`, confirma que o dump se lê com `pg_restore --list` e que o arquivo
se lê com `tar tzf`, e só então lhes dá o nome definitivo. Um ficheiro truncado
com o nome certo é pior do que não haver cópia, porque só se descobre no dia em
que é precisa.

Se a pasta `media/` não existir, avisa e continua — a cópia leva só a base.

Apaga automaticamente cópias com mais de 30 dias, **as duas metades ao mesmo
tempo**: apagar só os dumps deixaria arquivos de fotografias órfãos a crescer
para sempre, e apagar só as fotografias deixaria dumps que restauram registos
sem imagens. Para mudar:

```bash
RETENTION_DAYS=90 ./scripts/backup_db.sh
```

## Cifrar e enviar para fora do servidor

Uma cópia no mesmo disco da base que copia não é uma cópia de segurança: perder
a máquina é perder as duas coisas no mesmo instante. E o dump traz as fichas de
anamnese e o histórico clínico — categoria especial de dados, artigo 9.º do
RGPD — em texto legível.

O script trata das duas coisas se lhe derem as variáveis. **Sem elas continua a
fazer a cópia local**, e avisa no stderr o que ficou por fazer: uma cópia local
em claro é pior do que uma cifrada e enviada, mas é muito melhor do que
nenhuma.

### Cifra

Duas vias, por ordem de preferência:

```bash
# preferível: chave pública, o servidor cifra mas não decifra
age-keygen -o ~/chave-copias.txt          # numa máquina que NÃO seja o servidor
BACKUP_AGE_RECIPIENT=age1...              # só a linha "public key" vai para o servidor

# alternativa, se o age não estiver disponível
BACKUP_PASSPHRASE=...
```

Com `age` e chave pública, quem tomar o servidor não abre as cópias — nem as
novas nem as antigas. Com `gpg --symmetric`, o servidor tem de conhecer o
segredo, o que já protege o ficheiro que sai mas não protege de quem entre na
máquina.

A chave privada (`~/chave-copias.txt`) **não pode viver no servidor**. Guardada
noutro sítio, e guardada mesmo: sem ela as cópias não se restauram.

Restaurar:

```bash
age --decrypt -i chave-copias.txt -o copia.dump copia.dump.age
gpg --decrypt --output copia.dump copia.dump.gpg
```

### Envio

```bash
sudo apt install rclone
rclone config                    # cria o destino, por exemplo "b2"
BACKUP_REMOTE=b2:pa-backups
```

A retenção de 30 dias é só a deste disco. O que já foi enviado fica no destino
até alguém o apagar lá, e é de propósito: a cópia de fora existe para
sobreviver a esta máquina.

### No cron

As variáveis têm de estar onde o cron as veja — não basta tê-las na sessão:

```cron
0 3 * * * cd /opt/pa && BACKUP_AGE_RECIPIENT=age1... BACKUP_REMOTE=b2:pa-backups ./scripts/backup_db.sh >> /var/log/pa-backup.log 2>&1
```

Ler o `/var/log/pa-backup.log` na primeira manhã. É lá que aparecem os avisos
de "as cópias ficam em claro" ou "ficam só neste servidor" quando falta alguma
peça.

## Automatizar

Uma cópia diária às 3 da manhã, com registo:

```bash
sudo crontab -e
```

```cron
0 3 * * * cd /opt/pa && ./scripts/backup_db.sh >> /var/log/pa-backup.log 2>&1
```

### Mensagens que dependem do cron

Três famílias de mensagens só saem se um comando correr. **Sem estas duas
linhas no cron, nada disto é enviado** e resta o envio manual, marcação a
marcação:

* os **seguimentos** de cuidados posteriores, configurados em *Configurações →
  Mensagens → Mensagens por serviço*;
* os **avisos de retorno**, a quem ficou de voltar e ainda não marcou;
* os **lembretes** das marcações que estão a chegar.

Os dois primeiros correm uma vez por dia, num comando só. Os lembretes correm
de meia em meia hora, porque uma antecedência de duas horas não se cumpre com
um comando que passa uma vez por dia.

```cron
15 8 * * * cd /opt/pa && docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T web python manage.py send_daily_messages >> /var/log/pa-emails.log 2>&1
*/30 * * * * cd /opt/pa && docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T web python manage.py send_appointment_reminders >> /var/log/pa-lembretes.log 2>&1
```

Correr duas vezes não duplica nada: cada envio fica registado e o registo é
consultado antes do seguinte. É por isso que os lembretes podem correr de meia
em meia hora sem mandarem quarenta e oito mensagens por dia.

A antecedência do lembrete não está aqui — está no próprio modelo da mensagem,
em *Configurações → Mensagens → Modelos de email → Lembrete da marcação*, com
24 horas por omissão. **Zero desliga-o.** Mudá-la no ecrã chega; o cron fica
como está.

Para ver o que sairia, sem enviar:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T web \
    python manage.py send_daily_messages --dry-run

docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T web \
    python manage.py send_appointment_reminders --dry-run
```

`exec -T` e não `run`: o `exec` entra no contentor que já está a correr, e o
`-T` desliga o pseudo-terminal, que o cron não tem. Sem o `-T`, a linha falha
com *"the input device is not a TTY"* — e ninguém dá por isso até estranhar as
mensagens que não chegaram.

Dois limites propositados, que valem a pena conhecer antes de estranhar um
email que não chegou:

* **Só apanha marcações posteriores à criação da regra.** Criar hoje um
  seguimento a 15 dias não envia nada a quem fez o serviço no mês passado —
  senão ativar a regra despejava dezenas de emails de uma vez. Para esses, use
  o envio manual.
* **Ignora prazos vencidos há mais de 7 dias.** Instruções "15 dias depois" que
  chegam dois meses depois confundem mais do que ajudam. Se o cron estiver
  parado mais do que isso, esses envios dão-se por perdidos. Para alargar, corra
  o comando dos seguimentos à parte — o diário não passa esta opção adiante:
  `... exec -T web python manage.py send_service_followups --max-age-days 30`.

## Mensagens de WhatsApp

Configuradas em *Configurações → Mensagens → Regras de WhatsApp*: uma linha por
acontecimento e destinatário. Ao contrário dos seguimentos, **não precisam de
cron** — saem no momento em que a marcação é criada, confirmada ou cancelada.
As exceções são o lembrete e o aviso de retorno, que saem pelos comandos
descritos acima.

Saem pelo número da clínica, ligado como um dispositivo à maneira do WhatsApp
Web: texto livre sempre, sem modelos para aprovar e sem custo por mensagem, mas
sem garantia de serviço. Como se liga está em
[baileys_whatsapp.md](baileys_whatsapp.md).

No `.env.prod`:

```env
BAILEYS_ENABLED=True
BAILEYS_API_URL=http://baileys:3000
BAILEYS_API_TOKEN=...
BAILEYS_PROFESSIONAL_WHATSAPP=+351938594367
```

Houve aqui um segundo caminho — um serviço contratado, com modelos aprovados
pela Meta e um Content SID por mensagem. Saiu do projeto: o que sobra dele são
as linhas antigas no histórico de envios, que continuam a dizer por onde
saíram.

### Antes de apontar a clientes reais

Cada regra tem um botão **Enviar teste** na página de edição. Envia com dados
de exemplo, não fica no histórico, e é a forma de descobrir uma credencial
errada ou um template por aprovar sem ser através de um cliente.

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

Indica-se o dump; **as fotografias vêm com ele**, pelo carimbo do nome. Se o
arquivo do par não existir, o script diz-o antes de pedir confirmação, para a
decisão ser tomada sabendo que as imagens vão ficar as de agora.

Isto **apaga os dados atuais**. O script protege-se disso em três camadas:

1. valida o dump e o arquivo das fotografias antes de mexer em nada;
2. pede que escreva o nome da base de dados para confirmar — não aceita "sim"
   nem `-y`, para não ser executado por reflexo;
3. guarda o estado atual — base **e** fotografias — em `backups/pre-restauro_*`
   antes de restaurar.

Durante o restauro o serviço `web` é parado, para que nenhuma marcação entre a
meio. Se o restauro falhar, o `web` volta a subir sozinho e o caminho da cópia
de segurança é impresso no ecrã.

As fotografias são extraídas para uma pasta ao lado e só depois trocadas.
Extrair por cima da pasta a sério deixaria, se falhasse a meio, uma mistura das
antigas com as novas — o pior dos dois estados, e sem forma de saber qual é
qual.

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

### 8. O botão de marcação na Pesquisa e no Maps

No **Perfil de Empresa do Google**, no campo de marcações, pôr:

```
https://priarantes.com/agenda-publica/?utm_source=google&utm_medium=organic&utm_campaign=perfil-empresa
```

Passa a aparecer um botão *Agendar* na ficha, na Pesquisa e no Maps. O cliente
sai do Google e cai na agenda pública desta casa, com os pagamentos, as listas
de espera e as regras de agenda todas do lado de cá.

O `utm_source` é lido pelo GA4 que já está no `base.html`, e diz depois quantas
marcações vieram dali — **para quem aceitar os cookies de análise**. Quem
recusar não é contado, portanto o número é um mínimo e não um total.

E no `.env.prod`:

```env
SEO_GOOGLE_BUSINESS_URL=https://g.page/...
```

O link de partilha da ficha. Entra no JSON-LD da página inicial como `sameAs` e
`hasMap`, e é o que diz ao Google que a ficha e o site são a mesma casa — sem
ele, ficam a ser duas coisas que por acaso se parecem. Vazio não escreve nada.

> **O que isto não é.** O *Reserve with Google* — marcar sem sair do Google —
> exige entrar no programa de parceiros e implementar a Maps Booking API:
> feeds de comerciante, serviços e disponibilidade, mais um servidor de
> reservas em tempo real, com certificação. O Google integra plataformas de
> marcações, não negócios individuais. O que está descrito acima é o caminho
> aberto a quem tem uma ficha.


---

# Por aplicar à mão no Caddy

Duas coisas que este repositório não consegue fazer sozinho: o `Caddyfile` vive
em `/etc/caddy/Caddyfile`, na máquina de produção, e não no git.

**Nenhuma das duas está aplicada.**

## 1. Compressão

O site é servido sem compressão nenhuma — a página inicial são cerca de 73 KB
de HTML que podiam ser 15. O Django já comprime desde que o `GZipMiddleware`
entrou no `config/settings.py`, mas o sítio próprio para o fazer é o proxy: ali
comprime-se uma vez à saída, com `zstd` para quem o aceite, e o Python fica de
fora da conta.

Acrescentar ao bloco do PA:

```caddyfile
priarantes.com, www.priarantes.com, priarantes.cloud, www.priarantes.cloud {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8001
}
```

As duas compressões não conflituam: o `GZipMiddleware` do Django não toca em
respostas que já tragam `Content-Encoding`, e o Caddy não recomprime o que já
vem comprimido.

Confirmar:

```bash
curl -sSI -H "Accept-Encoding: gzip, br, zstd" https://priarantes.com/ \
    | grep -i "content-encoding\|content-length"
```

## 2. Content-Security-Policy

A política, o inventário das origens externas e o bloco pronto a colar estão em
[csp.md](csp.md). Aplicar **primeiro em `Report-Only`** e só passar a ativo
depois de dias sem violações.

## Depois de cada alteração

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

O `reload` não derruba o outro site alojado na mesma máquina. O `validate`
antes dele não é opcional: um `Caddyfile` inválido não recarrega, e descobrir
isso depois de reiniciar o serviço é descobri-lo com os dois sites em baixo.
