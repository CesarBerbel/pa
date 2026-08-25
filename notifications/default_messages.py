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

A morada aparece escrita por extenso nas confirmações, em vez de sair de uma
variável: é a mensagem que a cliente vai reler à porta do prédio, e um modelo
aprovado pela Meta não muda todos os dias.
"""

MORADA = "Galeria Avenida, Av. Sá da Bandeira 33, Loja 108, Coimbra"

# (evento, destinatário, texto de envio, texto para a Meta, variáveis)
DEFAULT_MESSAGES = [
    {
        "event_type": "appointment_requested",
        "audience": "professional",
        "body_template": (
            "Novo pedido de marcação pelo site: {{ customer_name }} pediu "
            "{{ service_name }} para {{ appointment_date }} às "
            "{{ appointment_time }}. Contacto da cliente: "
            "{{ customer_phone }}. Referência {{ reference_code }} — falta "
            "confirmar na agenda interna."
        ),
        "meta_template_body": (
            "Novo pedido de marcação pelo site: {{1}} pediu {{2}} para {{3}} "
            "às {{4}}. Contacto da cliente: {{5}}. Referência {{6}} — falta "
            "confirmar na agenda interna."
        ),
        "content_variables": {
            "1": "{{ customer_name }}",
            "2": "{{ service_name }}",
            "3": "{{ appointment_date }}",
            "4": "{{ appointment_time }}",
            "5": "{{ customer_phone }}",
            "6": "{{ reference_code }}",
        },
    },
    {
        "event_type": "appointment_requested",
        "audience": "customer",
        "body_template": (
            "Olá {{ customer_name }}, recebemos o seu pedido de marcação para "
            "{{ service_name }}, no dia {{ appointment_date }} às "
            "{{ appointment_time }}. Falta ainda confirmarmos a agenda — "
            "assim que estiver tratado, avisamos por aqui. A referência é "
            "{{ reference_code }} e pode acompanhar a marcação em "
            "{{ appointment_link }}, onde também a pode cancelar."
        ),
        "meta_template_body": (
            "Olá {{1}}, recebemos o seu pedido de marcação para {{2}}, no dia "
            "{{3}} às {{4}}. Falta ainda confirmarmos a agenda — assim que "
            "estiver tratado, avisamos por aqui. A referência é {{5}} e pode "
            "acompanhar a marcação em {{6}}, onde também a pode cancelar."
        ),
        "content_variables": {
            "1": "{{ customer_name }}",
            "2": "{{ service_name }}",
            "3": "{{ appointment_date }}",
            "4": "{{ appointment_time }}",
            "5": "{{ reference_code }}",
            "6": "{{ appointment_link }}",
        },
    },
    {
        "event_type": "appointment_confirmed",
        "audience": "customer",
        "body_template": (
            "Olá {{ customer_name }}, o seu pedido está confirmado: "
            "{{ service_name }}, no dia {{ appointment_date }} às "
            "{{ appointment_time }}. "
            "{% if is_home_visit %}"
            "Desta vez somos nós a ir ter consigo, a {{ home_address }}. "
            "{% else %}"
            "Esperamos por si na " + MORADA + ". "
            "{% endif %}"
            "Guarde a referência {{ reference_code }}; em "
            "{{ appointment_link }} pode consultar ou cancelar a marcação. Se "
            "não puder vir, avise-nos com antecedência — assim o horário fica "
            "livre para outra pessoa."
        ),
        "meta_template_body": (
            "Olá {{1}}, o seu pedido está confirmado: {{2}}, no dia {{3}} às "
            "{{4}}. Esperamos por si na " + MORADA + ". Guarde a referência "
            "{{5}}; em {{6}} pode consultar ou cancelar a marcação. Se não "
            "puder vir, avise-nos com antecedência — assim o horário fica "
            "livre para outra pessoa."
        ),
        "content_variables": {
            "1": "{{ customer_name }}",
            "2": "{{ service_name }}",
            "3": "{{ appointment_date }}",
            "4": "{{ appointment_time }}",
            "5": "{{ reference_code }}",
            "6": "{{ appointment_link }}",
        },
    },
    {
        # A marcação combinada ao telefone ou ao balcão não responde a pedido
        # nenhum: para a cliente, esta mensagem é a primeira vez que vê a data
        # escrita. Por isso não diz "confirmado" — regista o que foi combinado.
        "event_type": "appointment_confirmed_internal",
        "audience": "customer",
        "body_template": (
            "Olá {{ customer_name }}, fica registada a sua marcação de "
            "{{ service_name }} para {{ appointment_date }} às "
            "{{ appointment_time }}, como combinámos. "
            "{% if is_home_visit %}"
            "Desta vez somos nós a ir ter consigo, a {{ home_address }}. "
            "{% else %}"
            "Esperamos por si na " + MORADA + ". "
            "{% endif %}"
            "Guarde a referência {{ reference_code }}; em "
            "{{ appointment_link }} pode consultar ou cancelar a marcação, se "
            "precisar."
        ),
        "meta_template_body": (
            "Olá {{1}}, fica registada a sua marcação de {{2}} para {{3}} às "
            "{{4}}, como combinámos. Esperamos por si na " + MORADA + ". Guarde "
            "a referência {{5}}; em {{6}} pode consultar ou cancelar a "
            "marcação, se precisar."
        ),
        "content_variables": {
            "1": "{{ customer_name }}",
            "2": "{{ service_name }}",
            "3": "{{ appointment_date }}",
            "4": "{{ appointment_time }}",
            "5": "{{ reference_code }}",
            "6": "{{ appointment_link }}",
        },
    },
    {
        "event_type": "appointment_cancelled",
        "audience": "customer",
        "body_template": (
            "Olá {{ customer_name }}, a sua marcação de {{ service_name }}, "
            "de {{ appointment_date }} às {{ appointment_time }}, foi "
            "cancelada e o horário ficou livre. Motivo: "
            "{{ cancellation_reason }}. A referência era "
            "{{ reference_code }}. Quando quiser remarcar, escolha um horário "
            "em {{ booking_link }} ou responda a esta mensagem — teremos todo "
            "o gosto em recebê-la."
        ),
        "meta_template_body": (
            "Olá {{1}}, a sua marcação de {{2}}, de {{3}} às {{4}}, foi "
            "cancelada e o horário ficou livre. Motivo: {{5}}. A referência "
            "era {{6}}. Quando quiser remarcar, escolha um horário em {{7}} "
            "ou responda a esta mensagem — teremos todo o gosto em recebê-la."
        ),
        "content_variables": {
            "1": "{{ customer_name }}",
            "2": "{{ service_name }}",
            "3": "{{ appointment_date }}",
            "4": "{{ appointment_time }}",
            "5": "{{ cancellation_reason }}",
            "6": "{{ reference_code }}",
            "7": "{{ booking_link }}",
        },
    },
    {
        "event_type": "appointment_cancelled",
        "audience": "professional",
        "body_template": (
            "Marcação cancelada: {{ customer_name }} — {{ service_name }}, "
            "{{ appointment_date }} às {{ appointment_time }}. Motivo: "
            "{{ cancellation_reason }}. Contacto da cliente: "
            "{{ customer_phone }}. Referência {{ reference_code }}. "
            "O horário voltou a ficar livre na agenda."
        ),
        "meta_template_body": (
            "Marcação cancelada: {{1}} — {{2}}, {{3}} às {{4}}. Motivo: "
            "{{5}}. Contacto da cliente: {{6}}. Referência {{7}}. O horário "
            "voltou a ficar livre na agenda."
        ),
        "content_variables": {
            "1": "{{ customer_name }}",
            "2": "{{ service_name }}",
            "3": "{{ appointment_date }}",
            "4": "{{ appointment_time }}",
            "5": "{{ cancellation_reason }}",
            "6": "{{ customer_phone }}",
            "7": "{{ reference_code }}",
        },
    },
    {
        "event_type": "appointment_reminder",
        "audience": "customer",
        "body_template": (
            "Olá {{ customer_name }}, é já: {{ service_name }} no dia "
            "{{ appointment_date }} às {{ appointment_time }}. Se não puder "
            "vir, avise-nos em {{ appointment_link }} — assim o horário fica "
            "livre para outra pessoa."
        ),
        "meta_template_body": (
            "Olá {{1}}, é já: {{2}} no dia {{3}} às {{4}}. Se não puder vir, "
            "avise-nos em {{5}} — assim o horário fica livre para outra pessoa."
        ),
        "content_variables": {
            "1": "{{ customer_name }}",
            "2": "{{ service_name }}",
            "3": "{{ appointment_date }}",
            "4": "{{ appointment_time }}",
            "5": "{{ appointment_link }}",
        },
    },
    {
        "event_type": "return_due",
        "audience": "customer",
        "body_template": (
            "Olá {{ customer_name }}, da última vez ficou combinado voltar por "
            "esta altura, para {{ service_name }}. Escolha o horário que lhe "
            "der melhor jeito em {{ booking_link }}, ou responda a esta "
            "mensagem e combinamos por aqui."
        ),
        "meta_template_body": (
            "Olá {{1}}, da última vez ficou combinado voltar por esta altura, "
            "para {{2}}. Escolha o horário que lhe der melhor jeito em {{3}}, "
            "ou responda a esta mensagem e combinamos por aqui."
        ),
        "content_variables": {
            "1": "{{ customer_name }}",
            "2": "{{ service_name }}",
            "3": "{{ booking_link }}",
        },
    },
    {
        "event_type": "appointment_completed",
        "audience": "customer",
        "body_template": (
            "Olá {{ customer_name }}, obrigada pela sua visita. Se lhe surgir "
            "alguma dúvida sobre os cuidados a ter depois do serviço de "
            "{{ service_name }}, responda a esta mensagem — respondemos com "
            "todo o gosto. Quando for altura de voltar, pode escolher horário "
            "em {{ booking_link }}, quando lhe for mais conveniente."
        ),
        "meta_template_body": (
            "Olá {{1}}, obrigada pela sua visita. Se lhe surgir alguma dúvida "
            "sobre os cuidados a ter depois do serviço de {{2}}, responda a "
            "esta mensagem — respondemos com todo o gosto. Quando for altura de "
            "voltar, pode escolher horário em {{3}}, quando lhe for mais "
            "conveniente."
        ),
        "content_variables": {
            "1": "{{ customer_name }}",
            "2": "{{ service_name }}",
            "3": "{{ booking_link }}",
        },
    },
]
