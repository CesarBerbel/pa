"""Catálogo das mensagens de WhatsApp que o sistema traz configuradas.

Cada entrada tem dois textos, e a diferença entre eles é o que costuma
tropeçar:

* ``body_template`` é o texto que o servidor envia. Usa as variáveis do Django
  e só funciona no sandbox ou dentro das 24 horas seguintes a uma mensagem do
  destinatário.
* ``meta_template_body`` é o mesmo texto no formato que a Meta aprova, com as
  posições numeradas. É este que se cola no Content Template Builder da Twilio;
  o SID que de lá vem entra depois no campo do modelo aprovado.

``content_variables`` liga as duas coisas: diz que posição do modelo aprovado
recebe que variável do sistema.

Os textos seguem as regras que mais rejeições causam na revisão da Meta:
nenhuma posição no início ou no fim do corpo, nunca duas seguidas, e numeração
contínua a partir de 1.
"""

# (evento, destinatário, texto de envio, texto para a Meta, variáveis)
DEFAULT_MESSAGES = [
    {
        "event_type": "appointment_requested",
        "audience": "professional",
        "body_template": (
            "Novo pedido de marcação: {{ customer_name }} pediu "
            "{{ service_name }} para {{ appointment_date }} às "
            "{{ appointment_time }}. Referência {{ reference_code }}. "
            "Confirme na agenda interna."
        ),
        "meta_template_body": (
            "Novo pedido de marcação: {{1}} pediu {{2}} para {{3}} às {{4}}. "
            "Referência {{5}}. Confirme na agenda interna."
        ),
        "content_variables": {
            "1": "{{ customer_name }}",
            "2": "{{ service_name }}",
            "3": "{{ appointment_date }}",
            "4": "{{ appointment_time }}",
            "5": "{{ reference_code }}",
        },
    },
    {
        "event_type": "appointment_requested",
        "audience": "customer",
        "body_template": (
            "Olá {{ customer_name }}, recebemos o seu pedido de marcação para "
            "{{ service_name }}, no dia {{ appointment_date }} às "
            "{{ appointment_time }}. A referência é {{ reference_code }}. "
            "Entraremos em contacto assim que estiver confirmado."
        ),
        "meta_template_body": (
            "Olá {{1}}, recebemos o seu pedido de marcação para {{2}}, no dia "
            "{{3}} às {{4}}. A referência é {{5}}. Entraremos em contacto "
            "assim que estiver confirmado."
        ),
        "content_variables": {
            "1": "{{ customer_name }}",
            "2": "{{ service_name }}",
            "3": "{{ appointment_date }}",
            "4": "{{ appointment_time }}",
            "5": "{{ reference_code }}",
        },
    },
    {
        "event_type": "appointment_confirmed",
        "audience": "customer",
        "body_template": (
            "Olá {{ customer_name }}, a sua marcação de {{ service_name }} "
            "está confirmada para {{ appointment_date }} às "
            "{{ appointment_time }}. Referência {{ reference_code }}. "
            "Se precisar de alterar, responda a esta mensagem."
        ),
        "meta_template_body": (
            "Olá {{1}}, a sua marcação de {{2}} está confirmada para {{3}} às "
            "{{4}}. Referência {{5}}. Se precisar de alterar, responda a esta "
            "mensagem."
        ),
        "content_variables": {
            "1": "{{ customer_name }}",
            "2": "{{ service_name }}",
            "3": "{{ appointment_date }}",
            "4": "{{ appointment_time }}",
            "5": "{{ reference_code }}",
        },
    },
    {
        "event_type": "appointment_cancelled",
        "audience": "customer",
        "body_template": (
            "Olá {{ customer_name }}, a sua marcação de {{ service_name }} "
            "de {{ appointment_date }} às {{ appointment_time }} foi "
            "cancelada. Referência {{ reference_code }}. Se quiser remarcar, "
            "responda a esta mensagem."
        ),
        "meta_template_body": (
            "Olá {{1}}, a sua marcação de {{2}} de {{3}} às {{4}} foi "
            "cancelada. Referência {{5}}. Se quiser remarcar, responda a esta "
            "mensagem."
        ),
        "content_variables": {
            "1": "{{ customer_name }}",
            "2": "{{ service_name }}",
            "3": "{{ appointment_date }}",
            "4": "{{ appointment_time }}",
            "5": "{{ reference_code }}",
        },
    },
    {
        "event_type": "appointment_cancelled",
        "audience": "professional",
        "body_template": (
            "Marcação cancelada: {{ customer_name }}, {{ service_name }}, "
            "{{ appointment_date }} às {{ appointment_time }}. Referência "
            "{{ reference_code }}. O horário voltou a ficar livre."
        ),
        "meta_template_body": (
            "Marcação cancelada: {{1}}, {{2}}, {{3}} às {{4}}. Referência "
            "{{5}}. O horário voltou a ficar livre."
        ),
        "content_variables": {
            "1": "{{ customer_name }}",
            "2": "{{ service_name }}",
            "3": "{{ appointment_date }}",
            "4": "{{ appointment_time }}",
            "5": "{{ reference_code }}",
        },
    },
    {
        "event_type": "appointment_completed",
        "audience": "customer",
        "body_template": (
            "Olá {{ customer_name }}, obrigada pela sua visita. Esperamos que "
            "tenha corrido tudo bem com o seu {{ service_name }} de "
            "{{ appointment_date }}. Se tiver alguma dúvida sobre os cuidados "
            "a ter, responda a esta mensagem e teremos todo o gosto em ajudar."
        ),
        "meta_template_body": (
            "Olá {{1}}, obrigada pela sua visita. Esperamos que tenha corrido "
            "tudo bem com o seu {{2}} de {{3}}. Se tiver alguma dúvida sobre "
            "os cuidados a ter, responda a esta mensagem e teremos todo o "
            "gosto em ajudar."
        ),
        "content_variables": {
            "1": "{{ customer_name }}",
            "2": "{{ service_name }}",
            "3": "{{ appointment_date }}",
        },
    },
]
