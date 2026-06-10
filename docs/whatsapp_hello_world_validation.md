# Validação manual da WhatsApp Cloud API com `hello_world`

Este teste serve para validar a ligação básica com a WhatsApp Cloud API antes de testar o template real `marcacao`.

O comando envia o template padrão `hello_world`, usando por padrão o idioma `en_US` e sem parâmetros no corpo.

## Quando usar

Use este teste quando aparecerem erros como:

```text
HTTP 401 / OAuthException / code 190
HTTP 400 relacionado a Phone Number ID
Dúvida se o token, número remetente ou endpoint estão corretos
```

Se o `hello_world` falhar, o problema normalmente está antes do template `marcacao`: token, permissões, Phone Number ID, número de destino ou configuração do App/Business Manager.

## Configurações necessárias no `.env`

```env
WHATSAPP_CLOUD_API_ENABLED=True
WHATSAPP_CLOUD_API_VERSION=v23.0
WHATSAPP_PHONE_NUMBER_ID=COLOCAR_AQUI_O_PHONE_NUMBER_ID_DO_META
WHATSAPP_ACCESS_TOKEN=COLOCAR_AQUI_O_TOKEN_SEM_BEARER
WHATSAPP_REQUEST_TIMEOUT=15
```

Atenção: `WHATSAPP_ACCESS_TOKEN` não deve começar com `Bearer `. O código já adiciona `Bearer` no header HTTP.

## Ver payload sem enviar

```powershell
python manage.py validate_whatsapp_hello_world --to "+351910000000" --dry-run
```

Este comando mostra:

- endpoint de envio `/messages`;
- endpoint de validação do `Phone Number ID`;
- token mascarado;
- template usado;
- idioma usado;
- número de destino normalizado;
- payload JSON completo.

## Envio real

```powershell
python manage.py validate_whatsapp_hello_world --to "+351910000000"
```

Substitua o número pelo WhatsApp real de teste.

## Mostrar token completo apenas em ambiente local

```powershell
python manage.py validate_whatsapp_hello_world --to "+351910000000" --dry-run --show-token
```

Não copie o resultado com token completo para chats, tickets ou logs públicos.

## Pular validação prévia do Phone Number ID

```powershell
python manage.py validate_whatsapp_hello_world --to "+351910000000" --skip-phone-check
```

Use esta opção apenas quando quiser testar diretamente o endpoint `/messages`.

## Usar outro idioma ou template

O padrão é:

```text
Template: hello_world
Idioma: en_US
```

Se necessário:

```powershell
python manage.py validate_whatsapp_hello_world --to "+351910000000" --template "hello_world" --language "en_US"
```

## Interpretação dos resultados

### Sucesso na validação do Phone Number ID

Se aparecer algo como:

```json
{
  "display_phone_number": "...",
  "verified_name": "...",
  "id": "..."
}
```

então o token conseguiu ler o `WHATSAPP_PHONE_NUMBER_ID`.

### Sucesso no envio

Se o envio funcionar, a Meta retorna um JSON com `messages` e um `id` da mensagem.

### Erro 401 / code 190

O token está inválido, expirado, mal copiado, sem permissão ou pertence a outro App/Business.

### Erro de template

Se o `hello_world` falhar por template/idioma, confirme se o template padrão está disponível no App da Meta e mantenha `--language en_US`.

### Erro de número de destino

Confirme que o número está com indicativo do país e sem espaços. O comando normaliza o número removendo caracteres não numéricos.
