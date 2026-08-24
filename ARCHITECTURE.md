# Arquitetura

Monólito Django que serve **priarantes.com**: o site público de uma clínica de
pedicure terapêutica em Coimbra, a marcação online e a área interna onde a
profissional gere a agenda, as clientes e as fichas clínicas.

Uma pessoa a trabalhar, uma cadeira, uma agenda. Quase todas as decisões deste
documento saem daí: não há fila de tarefas, não há Redis, não há microserviços,
e a coisa mais cara que acontece num pedido é enviar um email.

## As quatro peças

| App | O que guarda e faz |
| --- | --- |
| `accounts` | Utilizadores (entrada por **email**, não por username), os dois níveis de acesso à área interna, e as chaves de acesso WebAuthn |
| `appointments` | O catálogo de serviços, as clientes, a agenda, as marcações, as fichas clínicas e as regras de disponibilidade |
| `notifications` | Emails, WhatsApp, seguimentos por serviço, a galeria de antes e depois e as publicações do Instagram |
| `config` | Definições, rotas, SEO, PWA, avaliações do Google, resolução do endereço do cliente |

`config` **não é uma app instalada** — é o pacote do projeto. Por isso a
biblioteca de tags `assets` é registada à mão em `TEMPLATES["OPTIONS"]`.

## Os dois níveis de acesso

Não é um só. `accounts.User` tem dois interruptores, e a diferença entre eles é
a razão de existir do segundo:

* `is_internal_staff` → gerir marcações, clientes, serviços e agenda.
* `can_access_clinical_data` → ver e editar anamneses e notas de evolução.

Quem trata da receção marca consultas sem ver a ficha clínica de ninguém. Os
mixins que os impõem são `InternalAreaRequiredMixin` e
`ClinicalAccessRequiredMixin`, em `appointments/mixins.py`.

## O núcleo: disponibilidade

`appointments/availability.py` é o sítio único onde vive a resposta a "este
horário pode ser marcado?". Horário de funcionamento, dia partido em dois
períodos, bloqueios pontuais e recorrentes, colisão com outras marcações,
antecedência mínima — está tudo lá.

`Appointment.clean()` delega para lá em vez de repetir a regra, e a base de
dados tem a última palavra: uma `UniqueConstraint` sobre `(date, start_time)`
que ignora as canceladas. A validação da aplicação pode ser ultrapassada por
dois pedidos em corrida; a restrição não pode.

As restantes camadas de `appointments` seguem o mesmo princípio — uma
responsabilidade por ficheiro, e as views ficam só com apresentação:

* `selectors.py` — as consultas de leitura usadas pelas views.
* `use_cases.py`, `appointment_services.py`, `cancellation_services.py` — as
  operações transacionais (criar, confirmar, concluir, cancelar).
* `customer_services.py`, `lookup_services.py`, `clinical_services.py`,
  `blocking_services.py`, `audit_services.py` — o resto do domínio.
* `views/` está dividido por assunto (`public.py`, `appointments.py`,
  `customers.py`, `schedules.py`, …), não num ficheiro só.

## O código da marcação é uma credencial

Cada marcação recebe um `reference_code` no formato `AGD-XXXXXX`, gerado com
`secrets`. Com ele — e sem sessão iniciada — vê-se e cancela-se a marcação, em
`/consultar/<código>/` e `/cancelar/<código>/`.

É deliberado: o link segue nas mensagens de WhatsApp e tem de continuar a
funcionar dias depois, mesmo que a marcação entretanto mude. Os links assinados
que vão nos emails (`/m/<token>/`) morrem à primeira alteração, porque levam o
`updated_at` no token — daí não servirem para o WhatsApp.

Sendo uma credencial, tem travão: ver "Travões", abaixo.

## Fichas clínicas

`PatientRecord` guarda a anamnese podológica e `ClinicalNote` as notas de
evolução. É **categoria especial de dados** (RGPD, artigo 9.º).

O que está feito: acesso separado por permissão própria, registo de quem leu e
alterou (`PatientRecordLog`), prazo de conservação configurável
(`CLINICAL_RECORD_RETENTION_YEARS`) e um comando que **lista** o que passou do
prazo — `report_clinical_retention`. A eliminação nunca é automática: é decisão
caso a caso.

O que **não** está feito: os campos estão em texto simples na base. Um dump
lê-se. As cópias de segurança passaram a sair cifradas (ver
`scripts/backup_db.sh`), que é a parte mais exposta do problema; cifrar campo a
campo custa pesquisa e filtragem e continua por decidir.

## WhatsApp

O sistema fala com as clientes por WhatsApp, e há **três** vias possíveis:

| Via | O que é |
| --- | --- |
| Cloud API | a oficial da Meta: modelos aprovados, janela de 24 horas |
| Twilio | intermediário para a mesma Cloud API, com o mesmo modelo aprovado |
| Baileys | liga-se como dispositivo emparelhado, tal como o WhatsApp Web |

`notifications/whatsapp_dispatch.py` é o único ponto por onde as marcações
disparam mensagens: cada regra escolhe o seu fornecedor e as marcações não têm
de saber que existe mais do que um.

O **Baileys corre num container à parte** (`baileys/`, Node) porque é uma
biblioteca Node. O Django só lhe fala por HTTP, pela rede interna do Docker, com
um token partilhado. Não há modelos para aprovar nem janela de 24 horas — mas
também não há garantia de serviço, porque é o número da clínica que está a
enviar. Ver [docs/baileys_whatsapp.md](docs/baileys_whatsapp.md).

## Entrega em segundo plano

Emails e mensagens saem depois de a marcação estar gravada, mas fora do pedido:
com `EMAIL_TIMEOUT` a 30s e o WhatsApp a 15-20s, um fornecedor lento segurava um
worker do gunicorn quase um minuto, e três marcações assim paravam o site.

São threads, não uma fila. Se o processo morrer com entregas a meio, elas
perdem-se — o que se resolveu foi o pior caso, não todos. Em testes o envio é
sempre imediato (`NOTIFICATIONS_IN_BACKGROUND` é forçado a `False`), porque
quase quatrocentos testes verificam o que foi enviado na linha seguinte.

## Público e interno na mesma raiz

`/` mostra a página inicial a quem não tem sessão e redireciona para o painel
quem tem acesso interno. O site é bilingue: português na raiz e inglês sob
`/en/`, com `prefix_default_language=False` para nenhum endereço existente
mudar.

Fora do `i18n_patterns` ficam as coisas que os robôs leem e não devem ganhar
prefixo de idioma: `robots.txt`, `sitemap.xml`, o admin, o manifesto e o service
worker. O manifesto e o `sw.js` vivem na raiz porque o âmbito de um service
worker é a pasta onde é servido.

O conteúdo do catálogo vive na base e não passa por `gettext`: cada categoria e
serviço tem campos `_en` próprios, com recurso ao português quando ficam vazios
(`get_localized_value`).

## Travões

* **Login** — `django-axes`. Bloqueia o par utilizador+endereço ao fim de oito
  falhas, durante meia hora.
* **Portas públicas** — `django-ratelimit`, através do `RateLimitedMixin` em
  `appointments/ratelimit.py`: consulta e cancelamento pelo código, marcação
  pública e consulta por email.

Atrás do Caddy todos os pedidos chegam de `127.0.0.1`. `config/client_ip.py`
resolve o endereço verdadeiro a partir do `X-Forwarded-For`, contando só os
elementos escritos por proxies de confiança — os últimos da lista. É o que
impede que uma pessoa a esgotar o limite bloqueie todas as outras, e que quem
queira escapar ao travão o faça inventando um cabeçalho.

A contagem é por processo: a cache é de memória local e o gunicorn corre com
três workers, portanto o limite real é o triplo do escrito. Trava um script, que
é o que se quer; o número só passa a exato no dia em que houver Redis.

## Produção

`docker-compose.prod.yml` sobe três serviços: `db` (PostgreSQL 16), `baileys` e
`web` (gunicorn com três workers). À frente deles, no anfitrião, está o **Caddy**
— que trata do TLS e faz `reverse_proxy` para `127.0.0.1:8001`, e cuja
configuração vive fora deste repositório.

O `web` espera que a base esteja saudável, mas só espera que o Baileys tenha
arrancado: o Baileys só fica saudável depois de falar com o WhatsApp, e o site
não tem de esperar por isso para servir páginas.

As fotografias carregadas vivem em `./media`, montada do anfitrião — não num
volume nomeado, para entrarem nas cópias de segurança como qualquer outro
ficheiro de `/opt/pa`. São servidas pelo Django, porque o WhiteNoise só serve o
`STATIC_ROOT` e o Caddy encaminha tudo para o Django.

Ver [docs/deploy.md](docs/deploy.md) para o procedimento, as cópias de segurança
e o que ainda está por aplicar à mão no Caddy.

## O que continua por fazer

1. Cifrar os campos clínicos na base (ver acima).
2. Content-Security-Policy — a política está escrita em [docs/csp.md](docs/csp.md),
   falta aplicá-la no Caddy.
3. Uma fila a sério (Celery/Redis) para entregas e lembretes, que também daria
   travões exatos.
4. Nonces nos scripts inline, para a CSP deixar de precisar de `'unsafe-inline'`.
