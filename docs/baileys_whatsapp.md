# WhatsApp pelo Baileys

Guia para pôr a ligação a funcionar em produção e para o dia em que ela cair.

---

## O que isto é

O Baileys liga o **número da clínica** ao servidor como um dispositivo
emparelhado, exatamente como o WhatsApp Web. Emparelha-se uma vez, lendo um QR
code com o telemóvel, e a sessão fica válida até alguém a terminar.

É por aqui que sai **todo** o WhatsApp desta casa. Houve um segundo caminho —
um serviço contratado, com modelos aprovados pela Meta e um identificador por
mensagem — mas saiu do projeto; do que sobra, o que interessa é a comparação,
porque explica o que se ganhou e o que se perdeu:

| | Baileys | serviço contratado |
|---|---|---|
| Modelos aprovados pela Meta | não precisa | obrigatórios fora das 24h |
| Custo por mensagem | nenhum | sim |
| Confirmação de entrega | não | sim, por webhook |
| Garantia de serviço | nenhuma | contratada |
| Quem envia | o número da clínica | um número alugado |

As regras configuram-se em *Configurações → Mensagens → Regras de WhatsApp*:
uma linha por acontecimento e destinatário, com o texto que sai. Não há
fornecedor a escolher — só o texto.

---

## Arquitetura

O Baileys é uma biblioteca Node e o resto é Django. Em vez de os juntar, há um
container à parte que mantém a ligação viva:

```
                     rede interna do Docker
   ┌──────────┐                                ┌─────────────┐
   │   web    │ ──── HTTP (X-Auth-Token) ────► │   baileys   │ ──► WhatsApp
   │ (Django) │      /status /send /logout     │   (Node)    │
   └──────────┘                                └──────┬──────┘
                                                      │
                                            volume pa_baileys_auth
                                            (a sessão emparelhada)
```

O serviço **não tem porta publicada**: só o Django lhe fala, pela rede interna.
O `BAILEYS_API_TOKEN` protege-o de qualquer outro container na mesma rede.

A sessão vive no volume `pa_baileys_auth`. É por isso que sobrevive a
reinícios, a `git pull` e a `up --build` — sem o volume, cada deploy obrigaria
a ler o QR outra vez.

---

## Deploy

### 1. Acrescentar as variáveis ao `.env.prod`

Gere primeiro um token:

```bash
openssl rand -hex 32
```

E acrescente ao fim do `.env.prod`, no servidor:

```env
# Baileys (WhatsApp)
BAILEYS_ENABLED=True
BAILEYS_API_URL=http://baileys:3000
BAILEYS_API_TOKEN=cole-aqui-o-token-gerado-acima
BAILEYS_PROFESSIONAL_WHATSAPP=+351938594367
BAILEYS_REQUEST_TIMEOUT=20
BAILEYS_DEVICE_NAME=Priscila Arantes Pedicure Terapêutica
BAILEYS_LOG_LEVEL=info
```

`BAILEYS_API_URL` é `http://baileys:3000` porque `baileys` é o nome do serviço
no compose — é assim que o Docker o resolve na rede interna. Não mexa nisto a
não ser que mude o nome do serviço.

O `BAILEYS_API_TOKEN` é lido dos dois lados: pelo Django (via `env_file`) e
pelo container Node (via `--env-file`). Tem de ser o mesmo valor, e é por isso
que basta escrevê-lo uma vez.

### 2. Subir

O comando é o mesmo de sempre — o serviço novo vem no compose:

```bash
cd /opt/pa && git pull && docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

### 3. Confirmar que o serviço arrancou

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f baileys
```

À espera de ver:

```
{"level":30,"msg":"Serviço Baileys a ouvir","port":3000,"authDir":"/data/auth"}
{"level":30,"msg":"A abrir ligação ao WhatsApp"}
{"level":30,"msg":"QR code novo à espera de leitura"}
```

### 4. Ler o QR code

No site: **Configurações → WhatsApp → Ligação**.

O código aparece no ecrã e vai-se renovando sozinho a cada 20 segundos. No
telemóvel da clínica:

1. WhatsApp → **Definições**
2. **Dispositivos ligados** → **Ligar dispositivo**
3. Apontar a câmara ao código

O estado passa a **Ligado** e mostra o número, sem ser preciso recarregar a
página.

### 5. Confirmar que as regras têm texto

O Baileys envia texto livre, por isso cada regra precisa do campo **Mensagem**
preenchido. Uma regra sem texto não tem nada para dizer — o ecrã da lista
marca-a com *Sem texto*.

### 6. Testar antes de apanhar um cliente

Em **Mensagens → Editar** numa regra qualquer há um **Enviar teste**: manda a
mensagem com dados de exemplo para o número que indicar, sem ficar no
histórico.

---

## O dia-a-dia

### A ligação caiu

O separador **Ligação** mostra o estado sempre atualizado:

| Estado | O que significa | O que fazer |
|---|---|---|
| **Ligado** | tudo bem | — |
| **À espera da leitura do QR code** | sem sessão | ler o código |
| **A ligar** / **A arrancar** | em curso | esperar uns segundos |
| **Desligado** | quebra de rede | reconecta sozinho; se ficar preso, *Reabrir a ligação* |
| **Sessão terminada no telemóvel** | alguém a removeu em Dispositivos ligados | ler o QR code novo |
| **Serviço inacessível** | o container está em baixo | ver os logs (abaixo) |
| **Desligado nas definições** | `BAILEYS_ENABLED=False` | corrigir o `.env.prod` |
| **Mal configurado** | falta o URL ou o token | corrigir o `.env.prod` |

Enquanto a ligação está em baixo, as regras que a usam aparecem marcadas como
**Bloqueada** na lista de mensagens, com o motivo. Nada é enviado em silêncio.

### Mudar de número

Separador Ligação → **Terminar sessão** → ler o QR code com o telemóvel novo.

### Ver os logs

```bash
cd /opt/pa
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=100 baileys
```

Para mais detalhe, ponha `BAILEYS_LOG_LEVEL=debug` no `.env.prod` e reinicie só
este serviço:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d baileys
```

### Reiniciar só o serviço

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml restart baileys
```

A sessão não se perde: está no volume, não no container.

### Voltar atrás

Basta pôr `BAILEYS_ENABLED=False` no `.env.prod` e subir. As regras ficam
bloqueadas — não enviam, e dizem porquê no ecrã. O e-mail continua a sair: são
canais separados, e desligar um não cala o outro.

---

## Riscos, ditos por inteiro

O Baileys **não é uma API oficial da Meta**. Liga-se ao WhatsApp como um
dispositivo, e o WhatsApp não tem obrigação nenhuma de o aceitar.

- Um volume alto de mensagens não solicitadas pode fazer **bloquear o número da
  clínica** — o mesmo número que os clientes usam para telefonar.
- Uma atualização do protocolo do WhatsApp pode quebrar a biblioteca até sair
  versão nova.
- Não há suporte, SLA, nem confirmação de entrega.

É um risco assumido, e a razão de o e-mail continuar ligado a par: as
mensagens que não podem falhar têm sempre um segundo caminho até à pessoa.

---

## Desenvolvimento local

O serviço corre à mão, fora do Docker:

```bash
cd baileys
npm install
AUTH_DIR=./auth BAILEYS_API_TOKEN=dev-token-local npm start
```

E no `.env` local:

```env
BAILEYS_ENABLED=True
BAILEYS_API_URL=http://localhost:3000
BAILEYS_API_TOKEN=dev-token-local
```

A pasta `baileys/auth/` fica ignorada pelo git — são as credenciais da sessão e
não têm nada que fazer no repositório.

### Endpoints do serviço

Todos, menos `/health`, exigem o cabeçalho `X-Auth-Token`.

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/health` | o container está de pé (usado pelo healthcheck) |
| GET | `/status` | estado, QR code em data URL, número ligado |
| POST | `/send` | `{"to": "+351...", "text": "..."}` |
| POST | `/logout` | termina a sessão e apaga as credenciais |
| POST | `/restart` | reabre a ligação sem perder o emparelhamento |

```bash
curl -H "X-Auth-Token: dev-token-local" http://localhost:3000/status
```
