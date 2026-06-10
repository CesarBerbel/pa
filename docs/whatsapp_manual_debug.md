# Teste manual de debug do WhatsApp

Este guia descreve como testar manualmente o envio do template `marcacao` pela WhatsApp Cloud API, sem depender do fluxo normal de confirmação de marcações.

## Objetivo

Validar rapidamente:

1. Se as variáveis do `.env` estão corretas.
2. Se o `PHONE_NUMBER_ID` está correto.
3. Se o token da Meta está válido.
4. Se o template `marcacao` está aprovado e com o idioma correto.
5. Se a ordem dos parâmetros do template está correta.
6. Se o número de destino está em formato aceite pela Meta.

## Comando criado

```powershell
python manage.py debug_whatsapp_template
```

O comando fica em:

```text
notifications/management/commands/debug_whatsapp_template.py
```

## Teste 1: validar payload sem enviar

Use este teste primeiro para conferir o JSON que será enviado para a Meta.

```powershell
python manage.py debug_whatsapp_template --to "+351910000000" --dry-run
```

O comando vai mostrar:

- endpoint usado;
- `PHONE_NUMBER_ID`;
- token mascarado;
- template;
- idioma;
- telefone normalizado;
- ordem das variáveis do template;
- payload JSON completo.

## Teste 2: envio real com dados de exemplo

Depois de validar o payload, rode sem `--dry-run`.

```powershell
python manage.py debug_whatsapp_template --to "+351910000000"
```

Substitua `+351910000000` por um número real autorizado/compatível com a conta WhatsApp Business usada na Meta.

## Teste 3: envio real usando uma marcação existente

Use este teste para montar o template com os dados reais da marcação.

```powershell
python manage.py debug_whatsapp_template --appointment-id 1
```

Nesse caso, se `--to` não for informado, o comando usa o telefone do cliente da marcação.

Para enviar os dados de uma marcação real para outro número de teste:

```powershell
python manage.py debug_whatsapp_template --appointment-id 1 --to "+351910000000"
```

## Teste 4: alterar a ordem dos parâmetros sem mexer no `.env`

Use quando a Meta retornar erro de quantidade ou ordem das variáveis do template.

```powershell
python manage.py debug_whatsapp_template --to "+351910000000" --parameters "customer_name,service_name,appointment_date,appointment_time,reference_code" --dry-run
```

Se o payload estiver correto, rode sem `--dry-run`:

```powershell
python manage.py debug_whatsapp_template --to "+351910000000" --parameters "customer_name,service_name,appointment_date,appointment_time,reference_code"
```

## Teste 5: enviar valores manuais

Use quando quiser testar texto específico em cada variável do template.

```powershell
python manage.py debug_whatsapp_template --to "+351910000000" --customer-name "Maria Teste" --service-name "Podologia" --appointment-date "20/06/2026" --appointment-time "14:30" --reference-code "AGD-TESTE"
```

## Teste 6: testar outro idioma ou template

```powershell
python manage.py debug_whatsapp_template --to "+351910000000" --template "marcacao" --language "pt_PT" --dry-run
```

## Variáveis obrigatórias no `.env`

```env
WHATSAPP_CLOUD_API_ENABLED=True
WHATSAPP_CLOUD_API_VERSION=v23.0
WHATSAPP_PHONE_NUMBER_ID=COLOCAR_AQUI_O_PHONE_NUMBER_ID_DO_META
WHATSAPP_ACCESS_TOKEN=COLOCAR_AQUI_O_TOKEN_VALIDO
WHATSAPP_TEMPLATE_NAME=marcacao
WHATSAPP_TEMPLATE_LANGUAGE_CODE=pt_PT
WHATSAPP_TEMPLATE_BODY_PARAMETERS=customer_name,service_name,appointment_date,appointment_time,reference_code
WHATSAPP_REQUEST_TIMEOUT=15
```

## Erros comuns

### Erro: Configuração WhatsApp incompleta

Significa que falta alguma variável obrigatória no `.env`.

Confira:

```powershell
Get-Content .env
```

Depois reinicie o servidor/terminal se necessário.

### Erro HTTP 400 da Meta

Normalmente indica um destes problemas:

1. Template inexistente.
2. Template não aprovado.
3. Idioma diferente do cadastrado no Meta.
4. Quantidade de variáveis diferente do template.
5. Ordem incorreta das variáveis.
6. Número de destino inválido.

### Erro HTTP 401 ou 403 da Meta

Normalmente indica:

1. Token inválido.
2. Token expirado.
3. Token sem permissão suficiente.
4. `PHONE_NUMBER_ID` não pertence à app/conta do token.

### Mensagem enviada para a Meta, mas não chega no WhatsApp

Verifique:

1. Se o número tem indicativo do país.
2. Se o número pode receber mensagens da conta WhatsApp Business.
3. Se a conta Meta não está em modo de teste restrito.
4. Se o template está aprovado para o idioma usado.

## Segurança

Não use `--show-token` em ambiente partilhado.

O comando mascara o token por padrão. A opção `--show-token` existe apenas para diagnóstico local controlado.
