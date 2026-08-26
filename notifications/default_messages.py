"""Catálogo das mensagens de WhatsApp que o sistema traz configuradas.

``body_template`` é o texto que sai, com as mesmas variáveis dos emails. Sai
pelo número da clínica, ligado como um dispositivo — não há modelos para
aprovar nem posições numeradas.

Houve um tempo em que cada entrada trazia também o texto no formato que a Meta
aprova, com as posições numeradas, para colar no construtor de modelos de um
serviço contratado. Esse caminho saiu do projeto, e com ele esses campos.

A morada aparece escrita por extenso nas confirmações, em vez de sair de uma
variável: é a mensagem que a cliente vai reler à porta do prédio.
"""

MORADA = "Galeria Avenida, Av. Sá da Bandeira 33, Loja 108, Coimbra"

# (evento, destinatário, texto de envio)
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
    },
]
