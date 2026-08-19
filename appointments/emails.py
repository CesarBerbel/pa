import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.db import connections, transaction
from django.urls import reverse
from django.utils.html import escape

from notifications.models import EmailEventSetting, MessagingSetting
from notifications.services import EmailEventSettingService, EmailTemplateService

logger = logging.getLogger(__name__)


_entregadores = None
_entregadores_lock = threading.Lock()


def _obter_entregadores():
    """Pool de threads das entregas, criado à primeira que houver.

    Não é criado no arranque porque a maior parte dos processos que importam
    este módulo — migrações, comandos de gestão, shell — nunca envia nada.

    As threads do pool não são daemon: um comando de gestão que termine com
    entregas a meio espera por elas antes de o processo fechar.
    """

    global _entregadores

    if _entregadores is None:
        with _entregadores_lock:
            if _entregadores is None:
                _entregadores = ThreadPoolExecutor(
                    max_workers=settings.NOTIFICATIONS_MAX_WORKERS,
                    thread_name_prefix="entrega",
                )

    return _entregadores


def _entregar(send_function, args, kwargs):
    try:
        send_function(*args, **kwargs)
    except Exception:
        logger.exception(
            "Failed to send email through %s.",
            getattr(send_function, "__name__", repr(send_function)),
        )


def _entregar_em_thread(send_function, args, kwargs):
    try:
        _entregar(send_function, args, kwargs)
    finally:
        # Cada thread abre a sua própria ligação à base de dados. Sem isto,
        # com CONN_MAX_AGE ligado, ficava uma ligação aberta por cada entrega.
        connections.close_all()


def deliver_after_commit(send_function, *args, **kwargs):
    """Envia depois de a transação fechar, e fora do caminho do pedido.

    Duas garantias diferentes, pela mesma ordem de sempre:

    1. **Depois do commit.** Um email ou um WhatsApp nunca decide se uma
       marcação sobrevive. Uma falha do envio é registada, não levantada, para
       um servidor de SMTP inacessível não desfazer uma marcação já gravada.
       Fora de uma transação, `on_commit()` corre o callback de imediato.

    2. **Fora do pedido.** O envio passa para uma thread do pool, e quem marcou
       recebe a resposta sem esperar pelo SMTP nem pelo WhatsApp. Com
       `NOTIFICATIONS_IN_BACKGROUND` desligado — como acontece nos testes — o
       envio volta a ser imediato e no mesmo sítio.
    """

    def agendar():
        if not settings.NOTIFICATIONS_IN_BACKGROUND:
            _entregar(send_function, args, kwargs)
            return

        _obter_entregadores().submit(_entregar_em_thread, send_function, args, kwargs)

    transaction.on_commit(agendar)


def generate_secure_link(appointment):
    # Generate a signed appointment access link.
    payload = {
        "reference_code": appointment.reference_code,
        "updated_at": appointment.updated_at.isoformat(),
    }

    token = signing.dumps(payload, salt="appointment-magic-link")

    return reverse(
        "appointments:public_appointment_magic",
        kwargs={"token": token},
    )


def internal_link(appointment):
    """Ecrã interno desta marcação, em endereço absoluto.

    Quem recebe um aviso interno vai agir sobre a marcação, não sobre o email:
    sem esta ligação, o passo seguinte é procurá-la na lista à mão.
    """

    return build_full_url(
        reverse("appointments:appointment_detail", kwargs={"pk": appointment.pk})
    )


def booking_link():
    """Página pública onde se escolhe um horário novo."""

    return build_full_url(reverse("appointments:public_visual_schedule"))


def build_appointment_context(appointment):
    """As variáveis que qualquer email sobre uma marcação tem à disposição."""

    return {
        "customer_name": appointment.customer.full_name,
        "customer_phone": appointment.customer.phone,
        "service_name": appointment.service.name,
        "appointment_date": appointment.date.strftime("%d/%m/%Y"),
        "appointment_time": appointment.start_time.strftime("%H:%M"),
        "reference_code": appointment.reference_code,
        "booking_link": booking_link(),
    }


def build_full_url(path):
    # Builds an absolute URL for emails using the canonical domain.
    # SITE_URL sempre existe (tem default em settings.py) e já vem sem barra
    # final, por isso não há fallback: um placeholder aqui só produziria links
    # partidos dentro de emails já enviados.
    return f"{settings.SITE_URL}{path}"


def send_rendered_email(subject, body_text, body_html, recipient_list):
    # Sends text email with optional HTML alternative.
    #
    # Todos os emails do site passam por aqui, e é por isso que o interruptor
    # geral é lido neste ponto e não em cada função de envio: um email novo
    # escrito daqui a uns meses fica coberto sem ninguém se lembrar disso.
    if not MessagingSetting.messaging_enabled():
        logger.info("Envio de mensagens desligado: email %r não foi enviado.", subject)

        return

    email = EmailMultiAlternatives(
        subject=subject,
        body=body_text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipient_list,
    )

    if body_html:
        email.attach_alternative(body_html, "text/html")

    email.send(fail_silently=False)


def render_email_for_event(
    event_type,
    template_key,
    context,
    fallback_subject,
    fallback_body,
    email_template=None,
):
    # Render an email for an event setting, selected template, default template key, or fallback text.
    selected_template = email_template

    if selected_template:
        return EmailTemplateService.render_template_or_fallback(
            email_template=selected_template,
            context_data=context,
            fallback_subject=fallback_subject,
            fallback_body=fallback_body,
        )

    event_setting = EmailEventSettingService.get_active_setting(event_type)

    if event_setting and event_setting.email_template:
        return EmailTemplateService.render_template_or_fallback(
            email_template=event_setting.email_template,
            context_data=context,
            fallback_subject=fallback_subject,
            fallback_body=fallback_body,
        )

    return EmailTemplateService.render(
        template_key=template_key,
        context_data=context,
        fallback_subject=fallback_subject,
        fallback_body=fallback_body,
    )


def send_appointment_confirmation_email(appointment):
    # Sends appointment creation or confirmation email.
    customer_email = appointment.customer.email

    if not customer_email:
        return

    link = generate_secure_link(appointment)
    full_url = build_full_url(link)

    cancel_path = reverse(
        "appointments:public_cancel_by_code",
        kwargs={
            "reference_code": appointment.reference_code,
        },
    )

    cancel_url = build_full_url(cancel_path)

    is_confirmed = appointment.status == appointment.STATUS_CONFIRMED

    if is_confirmed:
        # Uma marcação combinada ao balcão não responde a pedido nenhum: para
        # a cliente, este email é a primeira vez que vê a data escrita.
        if appointment.origin == appointment.ORIGIN_INTERNAL:
            event_type = EmailEventSetting.EVENT_APPOINTMENT_CONFIRMED_INTERNAL
            template_key = "appointment_confirmed_internal"
            fallback_subject = "A sua marcação ficou registada"
            intro = "Fica registada a marcação que combinámos."
        else:
            event_type = EmailEventSetting.EVENT_APPOINTMENT_CONFIRMED
            template_key = "appointment_confirmed"
            fallback_subject = "Confirmação da sua marcação"
            intro = "A sua marcação foi confirmada."
    else:
        event_type = EmailEventSetting.EVENT_APPOINTMENT_CREATED
        template_key = "appointment_created"
        fallback_subject = "Pedido de marcação recebido"
        intro = "Recebemos o seu pedido de marcação. Em breve será confirmado."

    event_setting = EmailEventSettingService.get_active_setting(event_type)

    if not event_setting:
        return

    context = build_appointment_context(appointment)
    context.update(
        {
            "cancellation_link": cancel_url,
            "magic_link": full_url,
            "intro": intro,
        }
    )

    fallback_body = (
        f"Olá {context['customer_name']},\n\n"
        f"{context['intro']}\n\n"
        f"Serviço: {context['service_name']}\n"
        f"Data: {context['appointment_date']}\n"
        f"Horário: {context['appointment_time']}\n"
        f"Código: {context['reference_code']}\n\n"
        f"Ver detalhes:\n{context['magic_link']}\n\n"
        f"Obrigada,\n"
        f"Priscila Arantes - Enfermeira e Podóloga"
    )

    rendered_email = render_email_for_event(
        event_type=event_type,
        template_key=template_key,
        context=context,
        fallback_subject=fallback_subject,
        fallback_body=fallback_body,
        email_template=event_setting.email_template,
    )

    send_rendered_email(
        subject=rendered_email["subject"],
        body_text=rendered_email["body_text"],
        body_html=rendered_email["body_html"],
        recipient_list=[customer_email],
    )


def send_appointment_cancelled_email(appointment, cancellation_reason=""):
    # Sends appointment cancellation email.
    customer_email = appointment.customer.email

    if not customer_email:
        return

    event_setting = EmailEventSettingService.get_active_setting(
        EmailEventSetting.EVENT_APPOINTMENT_CANCELLED,
    )

    if not event_setting:
        return

    context = {
        "customer_name": appointment.customer.full_name,
        "service_name": appointment.service.name,
        "appointment_date": appointment.date.strftime("%d/%m/%Y"),
        "appointment_time": appointment.start_time.strftime("%H:%M"),
        "reference_code": appointment.reference_code,
        "cancellation_reason": cancellation_reason or appointment.cancellation_reason,
    }

    fallback_subject = "Marcação cancelada"

    fallback_body = (
        f"Olá {context['customer_name']},\n\n"
        f"A sua marcação foi cancelada.\n\n"
        f"Serviço: {context['service_name']}\n"
        f"Data: {context['appointment_date']}\n"
        f"Horário: {context['appointment_time']}\n"
        f"Código: {context['reference_code']}\n\n"
        f"Motivo:\n{context['cancellation_reason']}\n\n"
        f"Obrigada,\n"
        f"Priscila Arantes PA"
    )

    rendered_email = render_email_for_event(
        event_type=EmailEventSetting.EVENT_APPOINTMENT_CANCELLED,
        template_key="appointment_cancelled",
        context=context,
        fallback_subject=fallback_subject,
        fallback_body=fallback_body,
        email_template=event_setting.email_template,
    )

    send_rendered_email(
        subject=rendered_email["subject"],
        body_text=rendered_email["body_text"],
        body_html=rendered_email["body_html"],
        recipient_list=[customer_email],
    )


def send_appointment_completed_email(appointment):
    """Agradecimento no fim do atendimento.

    Não sai sozinho: quem conclui a marcação é que decide se a cliente recebe
    alguma coisa. Aqui é só o texto e a entrega.
    """

    customer_email = appointment.customer.email

    if not customer_email:
        return

    event_setting = EmailEventSettingService.get_active_setting(
        EmailEventSetting.EVENT_APPOINTMENT_COMPLETED,
    )

    if not event_setting:
        return

    context = build_appointment_context(appointment)

    fallback_body = (
        f"Olá {context['customer_name']},\n\n"
        "Obrigada pela sua visita. Se lhe surgir alguma dúvida sobre os "
        "cuidados a ter nos próximos dias, responda a este email.\n\n"
        f"Serviço: {context['service_name']}\n"
        f"Data: {context['appointment_date']}\n"
        f"Código: {context['reference_code']}\n\n"
        "Com os melhores cumprimentos,\n"
        "Priscila Arantes — Enfermeira e Podóloga"
    )

    rendered_email = render_email_for_event(
        event_type=EmailEventSetting.EVENT_APPOINTMENT_COMPLETED,
        template_key="appointment_completed",
        context=context,
        fallback_subject="Obrigada pela sua visita",
        fallback_body=fallback_body,
        email_template=event_setting.email_template,
    )

    send_rendered_email(
        subject=rendered_email["subject"],
        body_text=rendered_email["body_text"],
        body_html=rendered_email["body_html"],
        recipient_list=[customer_email],
    )


def send_professional_notification_email(appointment, event_type, template_key):
    """Aviso interno: um pedido à espera de resposta, um horário que vagou.

    Vai para `PROFESSIONAL_EMAIL` e não para a cliente, e por isso leva o
    contacto dela e a ligação para o ecrã interno — quem o lê vai agir sobre a
    marcação, não responder ao email.
    """

    destinatario = settings.PROFESSIONAL_EMAIL

    if not destinatario:
        return

    event_setting = EmailEventSettingService.get_active_setting(
        event_type,
        audience=EmailEventSetting.AUDIENCE_PROFESSIONAL,
    )

    if not event_setting:
        return

    context = build_appointment_context(appointment)
    context.update(
        {
            "internal_link": internal_link(appointment),
            "cancellation_reason": appointment.cancellation_reason,
        }
    )

    fallback_body = (
        f"Cliente: {context['customer_name']}\n"
        f"Contacto: {context['customer_phone']}\n"
        f"Serviço: {context['service_name']}\n"
        f"Data: {context['appointment_date']}\n"
        f"Horário: {context['appointment_time']}\n"
        f"Código: {context['reference_code']}\n\n"
        f"Ver na agenda interna:\n{context['internal_link']}"
    )

    rendered_email = render_email_for_event(
        event_type=event_type,
        template_key=template_key,
        context=context,
        fallback_subject=f"Marcação: {context['customer_name']}",
        fallback_body=fallback_body,
        email_template=event_setting.email_template,
    )

    send_rendered_email(
        subject=rendered_email["subject"],
        body_text=rendered_email["body_text"],
        body_html=rendered_email["body_html"],
        recipient_list=[destinatario],
    )


def send_service_followup_email(appointment, followup):
    """Email de cuidados posteriores, uns dias depois do atendimento.

    Ao contrário dos outros, este não tem texto de reserva: o conteúdo é a
    razão de existir do seguimento, e enviar um email genérico em vez do manual
    de cuidados que a profissional escreveu seria pior do que não enviar nada.
    """

    customer_email = appointment.customer.email

    if not customer_email:
        return

    template = followup.email_template

    if not template or not template.is_active:
        raise ValueError("O modelo de email deste seguimento está inativo.")

    link = generate_secure_link(appointment)

    context = build_appointment_context(appointment)
    context.update(
        {
            "magic_link": build_full_url(link),
            "days_after": followup.days_after,
        }
    )

    rendered_email = EmailTemplateService.render_template_object(
        email_template=template,
        context_data=context,
    )

    send_rendered_email(
        subject=rendered_email["subject"],
        body_text=rendered_email["body_text"],
        body_html=rendered_email["body_html"],
        recipient_list=[customer_email],
    )


def send_open_appointments_lookup_email(recipient_email, appointments):
    # Sends open appointment details and reference codes to the email owner.
    appointments = list(appointments)

    if not recipient_email or not appointments:
        return

    subject = "Detalhes das suas marcações em aberto"
    appointment_count = len(appointments)

    if appointment_count == 1:
        intro = "Encontramos 1 marcação em aberto associada a este email."
    else:
        intro = (
            f"Encontramos {appointment_count} marcações em aberto associadas "
            "a este email."
        )

    text_lines = [
        "Olá,",
        "",
        "Recebemos uma solicitação para consultar marcações associadas a este email.",
        intro,
        "",
    ]

    html_items = []

    for appointment in appointments:
        detail_url = build_full_url(generate_secure_link(appointment))
        cancel_url = build_full_url(
            reverse(
                "appointments:public_cancel_by_code",
                kwargs={
                    "reference_code": appointment.reference_code,
                },
            )
        )

        status_label = appointment.get_status_display()
        appointment_date = appointment.date.strftime("%d/%m/%Y")
        appointment_time = appointment.start_time.strftime("%H:%M")

        text_lines.extend(
            [
                f"Código: {appointment.reference_code}",
                f"Estado: {status_label}",
                f"Cliente: {appointment.customer.full_name}",
                f"Serviço: {appointment.service.name}",
                f"Data: {appointment_date}",
                f"Horário: {appointment_time}",
                f"Ver detalhes: {detail_url}",
                f"Cancelar marcação: {cancel_url}",
                "",
            ]
        )

        html_items.append(
            "<li style='margin-bottom:16px;'>"
            f"<strong>Código:</strong> {escape(appointment.reference_code)}<br>"
            f"<strong>Estado:</strong> {escape(status_label)}<br>"
            f"<strong>Cliente:</strong> {escape(appointment.customer.full_name)}<br>"
            f"<strong>Serviço:</strong> {escape(appointment.service.name)}<br>"
            f"<strong>Data:</strong> {escape(appointment_date)}<br>"
            f"<strong>Horário:</strong> {escape(appointment_time)}<br>"
            f"<a href='{escape(detail_url)}'>Ver detalhes</a> | "
            f"<a href='{escape(cancel_url)}'>Cancelar marcação</a>"
            "</li>"
        )

    text_lines.extend(
        [
            "Se não foi você que solicitou esta consulta, ignore este email.",
            "",
            "Obrigada,",
            "Priscila Arantes PA",
        ]
    )

    body_text = "\n".join(text_lines)
    body_html = (
        "<p>Olá,</p>"
        "<p>Recebemos uma solicitação para consultar marcações associadas "
        "a este email.</p>"
        f"<p>{escape(intro)}</p>"
        f"<ul>{''.join(html_items)}</ul>"
        "<p>Se não foi você que solicitou esta consulta, ignore este email.</p>"
        "<p>Obrigada,<br>Priscila Arantes PA</p>"
    )

    send_rendered_email(
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        recipient_list=[recipient_email],
    )
