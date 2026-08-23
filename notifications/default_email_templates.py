"""Modelos de email que o sistema traz configurados.

Sem eles o sistema não fica mudo — cada função de envio tem um texto de reserva
embutido e é esse que sai. O que se ganha aqui é o controlo: o texto passa a
ser editável na área interna, e o cliente recebe um email com o aspeto da
clínica em vez de texto simples.

O HTML é deliberadamente conservador. Os clientes de email não são browsers:
não há folhas de estilo externas, `<style>` é ignorado por vários, e o que
funciona em todo o lado são tabelas com estilos em linha. A versão em texto
segue sempre junto, para quem lê sem HTML.

Há três famílias aqui dentro:

* os emails para a cliente, ligados a um acontecimento da marcação;
* os avisos para a profissional, com o contacto da cliente e a ligação para o
  ecrã interno, porque quem os lê vai agir sobre a marcação e não sobre o email;
* os modelos por serviço — o seguimento de uns dias depois e o texto que se
  manda à mão. Estes não estão ligados a acontecimento nenhum: ficam à espera
  de ser escolhidos numa mensagem de serviço.
"""

RODAPE_TEXTO = "Priscila Arantes — Enfermeira e Podóloga\nCoimbra"

MORADA = "Galeria Avenida, Av. Sá da Bandeira 33, Loja 108, 3000-351 Coimbra"


# Os rótulos do quadro de detalhes e a assinatura, por língua. O esqueleto do
# email é o mesmo nas duas: só estas palavras mudam.
ROTULOS_PT = {
    "servico": "Serviço",
    "data": "Data",
    "horario": "Horário",
    "codigo": "Código",
    "assinatura": "Priscila Arantes — Enfermeira e Podóloga<br>Coimbra",
}

ROTULOS_EN = {
    "servico": "Service",
    "data": "Date",
    "horario": "Time",
    "codigo": "Reference",
    "assinatura": "Priscila Arantes — Nurse and Podologist<br>Coimbra, Portugal",
}


def _html(
    titulo,
    saudacao,
    corpo,
    detalhes=True,
    acao=None,
    aviso=None,
    detalhes_extra="",
    rotulos=None,
):
    """Monta o email a partir das partes que mudam entre eles."""

    rotulos = rotulos or ROTULOS_PT

    bloco_detalhes = ""

    if detalhes:
        bloco_detalhes = f"""
        <table role="presentation" cellpadding="0" cellspacing="0" width="100%"
               style="background:#fff7f9;border:1px solid #f1d5db;border-radius:14px;margin:22px 0;">
          <tr><td style="padding:18px 20px;font-size:15px;color:#2b2b2b;line-height:1.9;">
{detalhes_extra}            <strong>{rotulos['servico']}:</strong> {{{{ service_name }}}}<br>
            <strong>{rotulos['data']}:</strong> {{{{ appointment_date }}}}<br>
            <strong>{rotulos['horario']}:</strong> {{{{ appointment_time }}}}<br>
            <strong>{rotulos['codigo']}:</strong> {{{{ reference_code }}}}
          </td></tr>
        </table>"""

    bloco_acao = ""

    if acao:
        texto_acao, url_acao = acao
        bloco_acao = f"""
        <table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 0 22px;">
          <tr><td style="background:#8b5e66;border-radius:999px;">
            <a href="{url_acao}"
               style="display:inline-block;padding:13px 28px;color:#ffffff;
                      text-decoration:none;font-weight:700;font-size:15px;">
              {texto_acao}
            </a>
          </td></tr>
        </table>"""

    bloco_aviso = ""

    if aviso:
        bloco_aviso = f"""
        <p style="margin:0 0 18px;font-size:14px;color:#6b6b6b;">{aviso}</p>"""

    return f"""<table role="presentation" cellpadding="0" cellspacing="0" width="100%"
       style="background:#faf7f7;padding:28px 12px;">
  <tr><td align="center">
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%"
           style="max-width:560px;background:#ffffff;border:1px solid #f1d5db;
                  border-radius:20px;font-family:Helvetica,Arial,sans-serif;">
      <tr><td style="padding:32px 30px;">

        <p style="margin:0 0 6px;font-size:11px;letter-spacing:0.14em;
                  text-transform:uppercase;color:#8b5e66;font-weight:700;">
          Priscila Arantes
        </p>

        <h1 style="margin:0 0 20px;font-size:23px;color:#2b2b2b;font-weight:600;">
          {titulo}
        </h1>

        <p style="margin:0 0 14px;font-size:16px;color:#2b2b2b;">{saudacao}</p>

        <p style="margin:0 0 4px;font-size:15px;color:#2b2b2b;line-height:1.6;">
          {corpo}
        </p>
{bloco_detalhes}
{bloco_aviso}
{bloco_acao}
        <hr style="border:0;border-top:1px solid #f1d5db;margin:26px 0 16px;">

        <p style="margin:0;font-size:13px;color:#6b6b6b;line-height:1.7;">
          {rotulos['assinatura']}
        </p>

      </td></tr>
    </table>
  </td></tr>
</table>"""


# Linhas que só os avisos internos levam: quem os lê precisa de saber a quem
# ligar, e o nome sozinho não chega.
DETALHES_CLIENTE = (
    "            <strong>Cliente:</strong> {{ customer_name }}<br>\n"
    "            <strong>Contacto:</strong> {{ customer_phone }}<br>\n"
)


DEFAULT_EMAIL_TEMPLATES = [
    # ------------------------------------------------------------------
    # Pedido de marcação feito no site
    # ------------------------------------------------------------------
    {
        "key": "appointment_created",
        "name": "Pedido de marcação recebido (cliente)",
        "event_type": "appointment_created",
        "audience": "customer",
        "subject": "Recebemos o seu pedido de marcação",
        "body_text": (
            "Olá {{ customer_name }},\n\n"
            "Recebemos o seu pedido de marcação. Falta ainda confirmarmos a "
            "agenda: assim que estiver tratado, receberá a confirmação por "
            "email.\n\n"
            "Serviço: {{ service_name }}\n"
            "Data: {{ appointment_date }}\n"
            "Horário: {{ appointment_time }}\n"
            "Código: {{ reference_code }}\n\n"
            "Pode acompanhar ou cancelar o pedido aqui:\n{{ magic_link }}\n\n"
            "Com os melhores cumprimentos,\n"
            f"{RODAPE_TEXTO}"
        ),
        "body_html": _html(
            titulo="Recebemos o seu pedido",
            saudacao="Olá {{ customer_name }},",
            corpo=(
                "O seu pedido de marcação chegou. Falta ainda confirmarmos a "
                "agenda — assim que estiver tratado, receberá a confirmação "
                "por email."
            ),
            acao=("Acompanhar o pedido", "{{ magic_link }}"),
        ),
    },
    {
        "key": "appointment_created_professional",
        "name": "Pedido de marcação recebido (profissional)",
        "event_type": "appointment_created",
        "audience": "professional",
        "subject": "Por confirmar: {{ customer_name }}, {{ appointment_date }}",
        "body_text": (
            "Entrou um pedido de marcação pelo site e está à espera de "
            "confirmação.\n\n"
            "Cliente: {{ customer_name }}\n"
            "Contacto: {{ customer_phone }}\n"
            "Serviço: {{ service_name }}\n"
            "Data: {{ appointment_date }}\n"
            "Horário: {{ appointment_time }}\n"
            "Código: {{ reference_code }}\n\n"
            "Confirmar na agenda interna:\n{{ internal_link }}\n"
        ),
        "body_html": _html(
            titulo="Pedido por confirmar",
            saudacao="Entrou um pedido de marcação pelo site.",
            corpo=(
                "O horário fica reservado, mas a cliente só recebe a "
                "confirmação depois de a marcação ser confirmada na agenda."
            ),
            detalhes_extra=DETALHES_CLIENTE,
            acao=("Abrir na agenda interna", "{{ internal_link }}"),
        ),
    },
    # ------------------------------------------------------------------
    # Confirmação — o pedido do site e a marcação combinada dizem-se
    # de maneiras diferentes
    # ------------------------------------------------------------------
    {
        "key": "appointment_confirmed",
        "name": "Marcação confirmada (pedida no site)",
        "event_type": "appointment_confirmed",
        "audience": "customer",
        "subject": "A sua marcação está confirmada — {{ appointment_date }}",
        "body_text": (
            "Olá {{ customer_name }},\n\n"
            "O seu pedido está confirmado. Contamos consigo.\n\n"
            "Serviço: {{ service_name }}\n"
            "Data: {{ appointment_date }}\n"
            "Horário: {{ appointment_time }}\n"
            "Código: {{ reference_code }}\n\n"
            f"Onde: {MORADA}\n\n"
            "Ver os detalhes da marcação:\n{{ magic_link }}\n\n"
            "Se não puder vir, avise-nos com antecedência para o horário "
            "ficar livre para outra pessoa:\n{{ cancellation_link }}\n\n"
            "Com os melhores cumprimentos,\n"
            f"{RODAPE_TEXTO}"
        ),
        "body_html": _html(
            titulo="Marcação confirmada",
            saudacao="Olá {{ customer_name }},",
            corpo=(
                "Está tudo tratado — contamos consigo no dia e hora abaixo, "
                f"na {MORADA}."
            ),
            acao=("Ver a minha marcação", "{{ magic_link }}"),
            aviso=(
                "Se não puder vir, "
                '<a href="{{ cancellation_link }}" style="color:#8b5e66;">'
                "avise-nos com antecedência</a> — assim o horário fica livre "
                "para outra pessoa."
            ),
        ),
    },
    {
        "key": "appointment_confirmed_internal",
        "name": "Marcação confirmada (combinada na clínica)",
        "event_type": "appointment_confirmed_internal",
        "audience": "customer",
        "subject": "A sua marcação ficou registada — {{ appointment_date }}",
        "body_text": (
            "Olá {{ customer_name }},\n\n"
            "Fica registada a marcação que combinámos. Este email serve de "
            "comprovativo.\n\n"
            "Serviço: {{ service_name }}\n"
            "Data: {{ appointment_date }}\n"
            "Horário: {{ appointment_time }}\n"
            "Código: {{ reference_code }}\n\n"
            f"Onde: {MORADA}\n\n"
            "Ver os detalhes da marcação:\n{{ magic_link }}\n\n"
            "Se precisar de alterar ou cancelar, é só responder a este email "
            "ou usar esta ligação:\n{{ cancellation_link }}\n\n"
            "Com os melhores cumprimentos,\n"
            f"{RODAPE_TEXTO}"
        ),
        "body_html": _html(
            titulo="A sua marcação ficou registada",
            saudacao="Olá {{ customer_name }},",
            corpo=(
                "Fica registada a marcação que combinámos, para ter por "
                f"escrito. Esperamos por si na {MORADA}."
            ),
            acao=("Ver a minha marcação", "{{ magic_link }}"),
            aviso=(
                "Se precisar de alterar ou cancelar, responda a este email "
                'ou use <a href="{{ cancellation_link }}" style="color:#8b5e66;">'
                "esta ligação</a>."
            ),
        ),
    },
    # ------------------------------------------------------------------
    # Cancelamento
    # ------------------------------------------------------------------
    {
        "key": "appointment_cancelled",
        "name": "Marcação cancelada (cliente)",
        "event_type": "appointment_cancelled",
        "audience": "customer",
        # Mantém a expressão do assunto antigo — há quem filtre a caixa de
        # entrada por ela — e acrescenta o serviço, que ajuda a identificar
        # qual das marcações caiu.
        "subject": "Marcação cancelada — {{ service_name }}",
        "body_text": (
            "Olá {{ customer_name }},\n\n"
            "A sua marcação foi cancelada e o horário voltou a ficar livre.\n\n"
            "Serviço: {{ service_name }}\n"
            "Data: {{ appointment_date }}\n"
            "Horário: {{ appointment_time }}\n"
            "Código: {{ reference_code }}\n"
            # O motivo faz parte da informação: sem ele o cliente fica sem
            # saber porque é que a marcação caiu. O condicional evita um
            # "Motivo:" solto quando o cancelamento não trouxe explicação.
            "{% if cancellation_reason %}\n"
            "Motivo: {{ cancellation_reason }}\n"
            "{% endif %}\n"
            "Quando quiser remarcar, é só responder a este email — teremos "
            "todo o gosto em recebê-la.\n\n"
            "Com os melhores cumprimentos,\n"
            f"{RODAPE_TEXTO}"
        ),
        "body_html": _html(
            titulo="Marcação cancelada",
            saudacao="Olá {{ customer_name }},",
            corpo="A marcação abaixo foi cancelada e o horário voltou a ficar livre.",
            aviso=(
                "{% if cancellation_reason %}"
                "<strong>Motivo:</strong> {{ cancellation_reason }}<br><br>"
                "{% endif %}"
                "Quando quiser remarcar, é só responder a este email — teremos "
                "todo o gosto em recebê-la."
            ),
        ),
    },
    {
        "key": "appointment_cancelled_professional",
        "name": "Marcação cancelada (profissional)",
        "event_type": "appointment_cancelled",
        "audience": "professional",
        "subject": "Cancelamento: {{ customer_name }}, {{ appointment_date }}",
        "body_text": (
            "Uma marcação foi cancelada e o horário voltou a ficar livre na "
            "agenda.\n\n"
            "Cliente: {{ customer_name }}\n"
            "Contacto: {{ customer_phone }}\n"
            "Serviço: {{ service_name }}\n"
            "Data: {{ appointment_date }}\n"
            "Horário: {{ appointment_time }}\n"
            "Código: {{ reference_code }}\n"
            "{% if cancellation_reason %}\n"
            "Motivo indicado: {{ cancellation_reason }}\n"
            "{% endif %}\n"
            "Ver na agenda interna:\n{{ internal_link }}\n"
        ),
        "body_html": _html(
            titulo="Marcação cancelada",
            saudacao="O horário voltou a ficar livre na agenda.",
            corpo="A marcação abaixo foi cancelada.",
            detalhes_extra=DETALHES_CLIENTE,
            aviso=(
                "{% if cancellation_reason %}"
                "<strong>Motivo indicado:</strong> {{ cancellation_reason }}"
                "{% endif %}"
            ),
            acao=("Abrir na agenda interna", "{{ internal_link }}"),
        ),
    },
    # ------------------------------------------------------------------
    # Fim do atendimento
    # ------------------------------------------------------------------
    {
        "key": "appointment_completed",
        "name": "Atendimento concluído (cliente)",
        "event_type": "appointment_completed",
        "audience": "customer",
        "subject": "Obrigada pela sua visita",
        "body_text": (
            "Olá {{ customer_name }},\n\n"
            "Obrigada pela sua visita de hoje. Foi um gosto recebê-la.\n\n"
            "Serviço: {{ service_name }}\n"
            "Data: {{ appointment_date }}\n"
            "Código: {{ reference_code }}\n\n"
            "Se lhe surgir alguma dúvida sobre os cuidados a ter nos "
            "próximos dias, responda a este email — respondemos com todo o "
            "gosto.\n\n"
            "Quando for altura de voltar, pode marcar aqui:\n"
            "{{ booking_link }}\n\n"
            "Com os melhores cumprimentos,\n"
            f"{RODAPE_TEXTO}"
        ),
        "body_html": _html(
            titulo="Obrigada pela sua visita",
            saudacao="Olá {{ customer_name }},",
            corpo=(
                "Foi um gosto recebê-la. Se lhe surgir alguma dúvida sobre os "
                "cuidados a ter nos próximos dias, responda a este email — "
                "respondemos com todo o gosto."
            ),
            acao=("Marcar a próxima visita", "{{ booking_link }}"),
        ),
    },
    # ------------------------------------------------------------------
    # Modelos por serviço: sem acontecimento associado, escolhidos numa
    # mensagem de serviço
    # ------------------------------------------------------------------
    {
        "key": "service_followup",
        "name": "Seguimento alguns dias depois (por serviço)",
        "event_type": None,
        "audience": None,
        "subject": "Como tem corrido depois do seu {{ service_name }}?",
        "body_text": (
            "Olá {{ customer_name }},\n\n"
            "Passaram {{ days_after }} dias desde o seu atendimento de "
            "{{ service_name }}, a {{ appointment_date }}. Escrevemos só para "
            "saber como tem corrido.\n\n"
            "Se notar dor, vermelhidão, inchaço ou qualquer alteração que a "
            "preocupe, responda a este email ou contacte-nos: vale sempre mais "
            "esclarecer cedo do que esperar.\n\n"
            "Quando for altura de voltar, pode marcar aqui:\n"
            "{{ booking_link }}\n\n"
            "Com os melhores cumprimentos,\n"
            f"{RODAPE_TEXTO}"
        ),
        "body_html": _html(
            titulo="Como tem corrido?",
            saudacao="Olá {{ customer_name }},",
            corpo=(
                "Passaram {{ days_after }} dias desde o seu atendimento e "
                "escrevemos só para saber como tem corrido. Se notar dor, "
                "vermelhidão, inchaço ou qualquer alteração que a preocupe, "
                "responda a este email — vale sempre mais esclarecer cedo do "
                "que esperar."
            ),
            acao=("Marcar a próxima visita", "{{ booking_link }}"),
        ),
    },
    {
        "key": "service_manual",
        "name": "Recomendações do serviço (envio manual)",
        "event_type": None,
        "audience": None,
        "subject": "Recomendações após o seu {{ service_name }}",
        "body_text": (
            "Olá {{ customer_name }},\n\n"
            "Ficam por escrito as recomendações do seu atendimento de "
            "{{ service_name }}, a {{ appointment_date }}, para as ter à mão "
            "quando precisar.\n\n"
            "Recomendações gerais:\n"
            "- mantenha a zona limpa e seca;\n"
            "- use calçado confortável, que não aperte;\n"
            "- não retire pensos nem crostas antes do tempo indicado;\n"
            "- em caso de dor, calor, vermelhidão ou pus, contacte-nos.\n\n"
            "Este texto é geral. Se lhe foi dada alguma indicação específica "
            "no atendimento, é essa que conta.\n\n"
            "Qualquer dúvida, responda a este email.\n\n"
            "Com os melhores cumprimentos,\n"
            f"{RODAPE_TEXTO}"
        ),
        "body_html": _html(
            titulo="Recomendações do seu atendimento",
            saudacao="Olá {{ customer_name }},",
            corpo=(
                "Ficam por escrito as recomendações do seu atendimento, para "
                "as ter à mão quando precisar: mantenha a zona limpa e seca, "
                "use calçado confortável, não retire pensos nem crostas antes "
                "do tempo indicado e contacte-nos em caso de dor, calor, "
                "vermelhidão ou pus."
            ),
            aviso=(
                "Este texto é geral. Se lhe foi dada alguma indicação "
                "específica no atendimento, é essa que conta."
            ),
        ),
    },
]
