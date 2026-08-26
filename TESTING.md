# Testes

A suite corre com **pytest** e `pytest-django`. A configuração está em
`pytest.ini`: o módulo de definições, os padrões de nome dos ficheiros e
`--reuse-db`, que evita recriar a base a cada execução.

```bash
pytest                                  # tudo
pytest appointments/tests/              # uma pasta
pytest appointments/tests/test_booking_integrity.py -q
pytest -k "cancel" -q                   # por nome
pytest --create-db                      # base nova, quando as migrações mudam
```

`SECRET_KEY` não tem valor por omissão: sem ela — no `.env` local ou no
ambiente — o Django nem arranca. É o primeiro erro a suspeitar quando a suite
não chega a coletar nada.

## Onde correm

Em cada `push` e em cada `pull request` para `main`, pelo
[`.github/workflows/testes.yml`](.github/workflows/testes.yml): Python 3.12 e
PostgreSQL 16, as mesmas versões do `Dockerfile` e do `docker-compose.prod.yml`.

Localmente a base por omissão é SQLite, o que é mais rápido e chega para quase
tudo. O CI corre em Postgres de propósito: uma suite que passa em SQLite e falha
em Postgres não prova nada sobre produção.

## O que está coberto

Cerca de **920 testes em 57 ficheiros**, mais uns 380 subtestes. Por assunto:

### Agenda e disponibilidade

O núcleo, e o que mais testes tem. Horário de funcionamento e dia partido em
dois períodos, bloqueios pontuais e recorrentes, colisão entre marcações,
antecedência mínima, marcações canceladas a libertarem o horário, grelha de
horários pública, agenda visual, semanal e mensal.

`test_booking_integrity.py` cobre a marcação em duplicado — incluindo a
restrição da base, que é a última linha de defesa contra dois pedidos em
corrida.

### Marcações

Criação pelo público e pela área interna, confirmação, conclusão, cancelamento,
alterações de estado quando a agenda muda por baixo, registo de auditoria
(`AppointmentLog`) e âmbito das listagens.

### Consulta pública

Consulta pelo código, consulta por email, o link direto que vai nas mensagens
de WhatsApp, deduplicação de clientes que marcam duas vezes, e os travões —
`test_public_ratelimit.py`.

### Fichas clínicas

`test_clinical_access.py` e `test_patient_record.py`: quem pode ver o quê. É a
fronteira entre os dois níveis de acesso, e é a que não pode falhar sem
consequências legais.

### Entrada e acessos

`accounts/`: entrada por email, navegação da área interna conforme o nível de
acesso, chaves WebAuthn (`test_passkeys.py`) e o bloqueio por tentativas
falhadas (`test_login_lockout.py`).

### Notificações

Emails, catálogo de mensagens, versões inglesas, definições por evento,
seguimentos por serviço, e o envio de WhatsApp (`test_baileys.py`), com o
exterior simulado.

### Site público e infraestrutura

`config/`: SEO, PWA e service worker, versionamento de estáticos, avaliações do
Google, i18n (as páginas em `/en/`), livro de reclamações, e a resolução do
endereço do cliente atrás do proxy (`test_client_ip.py`).

## Como estão escritos

`TestCase` do Django com o cliente de teste — não são testes de unidade puros,
percorrem a view, os formulários e a base. Isso torna-os mais lentos e muito
mais úteis: o que costuma partir aqui é a ligação entre camadas, não uma função
isolada.

Ajudantes partilhados:

* `appointments/tests/factories.py` — categorias, serviços e horários de base.
  Usam `get_or_create` para reaproveitar o que as migrações já semearam.
* `AppointmentTestSetupMixin`, em `appointments/tests/tests.py` — utilizadores,
  cliente, serviço e horário de funcionamento numa chamada.
* `freezegun` para congelar o tempo onde a data de hoje muda o resultado.

## O que os testes desligam de propósito

O `config/settings.py` deteta que está debaixo de testes (`RUNNING_TESTS`) e
desliga o que fala com o exterior ou o que mediria a suite em vez do site:

* **Avaliações do Google** — com a chave verdadeira no `.env`, cada teste que
  desenhasse a página inicial era uma chamada externa, lenta e paga. Os testes
  das avaliações ligam-na de volta com uma chave de mentira.
* **Entrega em segundo plano** — quase quatrocentos testes verificam o que foi
  enviado na linha a seguir à chamada; numa thread isso passaria a corrida.
* **Travões de tentativas** (`AXES_ENABLED`, `RATELIMIT_ENABLE`) — a suite
  inteira corre do mesmo endereço e em sequência, e esgotaria qualquer limite
  razoável. Os testes dos travões ligam-nos de volta com `override_settings`.

O padrão é sempre o mesmo: desligado por omissão nos testes, ligado de volta
onde é o assunto do teste. Cada um destes sítios explica no código porquê.

## Cobertura

O `pytest-cov` está instalado e a configuração vive no `pyproject.toml`. Não
está nos `addopts` porque medir cobertura torna cada execução mais lenta, e a
maior parte das execuções é durante o trabalho, não para arquivar um número:

```bash
pytest --cov --cov-report=term-missing
pytest --cov --cov-report=html    # htmlcov/index.html
```

O CI mede sempre, no resumo do passo dos testes.
