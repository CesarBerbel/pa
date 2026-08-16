"""Modelos de email que o sistema traz configurados.

Sem eles o sistema não fica mudo — cada função de envio tem um texto de reserva
embutido e é esse que sai. O que se ganha aqui é o controlo: o texto passa a
ser editável na área interna, e o cliente recebe um email com o aspeto da
clínica em vez de texto simples.

O HTML é deliberadamente conservador. Os clientes de email não são browsers:
não há folhas de estilo externas, `<style>` é ignorado por vários, e o que
funciona em todo o lado são tabelas com estilos em linha. A versão em texto
segue sempre junto, para quem lê sem HTML.
"""

RODAPE_TEXTO = "Priscila Arantes — Enfermeira e Podóloga\nCoimbra"


def _html(titulo, saudacao, corpo, detalhes=True, acao=None, aviso=None):
    """Monta o email a partir das partes que mudam entre eles."""

    bloco_detalhes = ""

    if detalhes:
        bloco_detalhes = """
        <table role="presentation" cellpadding="0" cellspacing="0" width="100%"
               style="background:#fff7f9;border:1px solid #f1d5db;border-radius:14px;margin:22px 0;">
          <tr><td style="padding:18px 20px;font-size:15px;color:#2b2b2b;line-height:1.9;">
            <strong>Serviço:</strong> {{ service_name }}<br>
            <strong>Data:</strong> {{ appointment_date }}<br>
            <strong>Horário:</strong> {{ appointment_time }}<br>
            <strong>Código:</strong> {{ reference_code }}
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
          Priscila Arantes — Enfermeira e Podóloga<br>
          Coimbra
        </p>

      </td></tr>
    </table>
  </td></tr>
</table>"""


DEFAULT_EMAIL_TEMPLATES = [
    {
        "key": "appointment_created",
        "name": "Pedido de marcação recebido",
        "event_type": "appointment_created",
        "subject": "Recebemos o seu pedido de marcação",
        "body_text": (
            "Olá {{ customer_name }},\n\n"
            "Recebemos o seu pedido de marcação. Entraremos em contacto "
            "assim que estiver confirmado.\n\n"
            "Serviço: {{ service_name }}\n"
            "Data: {{ appointment_date }}\n"
            "Horário: {{ appointment_time }}\n"
            "Código: {{ reference_code }}\n\n"
            "Ver os detalhes:\n{{ magic_link }}\n\n"
            f"{RODAPE_TEXTO}"
        ),
        "body_html": _html(
            titulo="Recebemos o seu pedido",
            saudacao="Olá {{ customer_name }},",
            corpo=(
                "O seu pedido de marcação chegou. Entraremos em contacto "
                "assim que estiver confirmado."
            ),
            acao=("Ver a minha marcação", "{{ magic_link }}"),
        ),
    },
    {
        "key": "appointment_confirmed",
        "name": "Marcação confirmada",
        "event_type": "appointment_confirmed",
        "subject": "A sua marcação está confirmada",
        "body_text": (
            "Olá {{ customer_name }},\n\n"
            "A sua marcação está confirmada. Contamos consigo.\n\n"
            "Serviço: {{ service_name }}\n"
            "Data: {{ appointment_date }}\n"
            "Horário: {{ appointment_time }}\n"
            "Código: {{ reference_code }}\n\n"
            "Ver os detalhes:\n{{ magic_link }}\n\n"
            "Se precisar de cancelar:\n{{ cancellation_link }}\n\n"
            f"{RODAPE_TEXTO}"
        ),
        "body_html": _html(
            titulo="Marcação confirmada",
            saudacao="Olá {{ customer_name }},",
            corpo="Está tudo tratado. Contamos consigo no dia e hora abaixo.",
            acao=("Ver a minha marcação", "{{ magic_link }}"),
            aviso=(
                "Se precisar de cancelar, use "
                '<a href="{{ cancellation_link }}" style="color:#8b5e66;">'
                "esta ligação</a>."
            ),
        ),
    },
    {
        "key": "appointment_reminder",
        "name": "Lembrete de marcação",
        "event_type": "appointment_reminder",
        "subject": "Lembrete: a sua marcação {{ reminder_label }}",
        "body_text": (
            "Olá {{ customer_name }},\n\n"
            "Este é um lembrete da sua marcação {{ reminder_label }}.\n\n"
            "Serviço: {{ service_name }}\n"
            "Data: {{ appointment_date }}\n"
            "Horário: {{ appointment_time }}\n"
            "Código: {{ reference_code }}\n\n"
            "Ver os detalhes:\n{{ magic_link }}\n\n"
            "Se precisar de cancelar:\n{{ cancellation_link }}\n\n"
            f"{RODAPE_TEXTO}"
        ),
        "body_html": _html(
            titulo="Lembrete da sua marcação",
            saudacao="Olá {{ customer_name }},",
            corpo="Passamos por aqui para lembrar a sua marcação {{ reminder_label }}.",
            acao=("Ver a minha marcação", "{{ magic_link }}"),
            aviso=(
                "Se já não puder comparecer, "
                '<a href="{{ cancellation_link }}" style="color:#8b5e66;">'
                "avise-nos por aqui</a> para libertarmos o horário."
            ),
        ),
    },
    {
        "key": "appointment_cancelled",
        "name": "Marcação cancelada",
        "event_type": "appointment_cancelled",
        # Mantém a expressão do assunto antigo — há quem filtre a caixa de
        # entrada por ela — e acrescenta o serviço, que ajuda a identificar
        # qual das marcações caiu.
        "subject": "Marcação cancelada — {{ service_name }}",
        "body_text": (
            "Olá {{ customer_name }},\n\n"
            "A sua marcação foi cancelada.\n\n"
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
            "Se quiser remarcar, é só responder a este email.\n\n"
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
                "Se quiser remarcar, é só responder a este email."
            ),
        ),
    },
]
