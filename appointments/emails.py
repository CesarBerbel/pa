import logging

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.urls import reverse
from django.utils.html import escape

from notifications.models import EmailEventSetting
from notifications.services import EmailEventSettingService, EmailTemplateService

logger = logging.getLogger(__name__)


def deliver_after_commit(send_function, *args, **kwargs):
    # Transactional emails must never decide whether a business operation
    # survives. Delivery runs only after the surrounding transaction commits,
    # and a mail failure is logged instead of raised, so an unreachable SMTP
    # server can no longer roll back or break a booking.
    # Outside a transaction, on_commit() runs the callback immediately.
    def deliver():
        try:
            send_function(*args, **kwargs)
        except Exception:
            logger.exception(
                "Failed to send email through %s.",
                getattr(send_function, "__name__", repr(send_function)),
            )

    transaction.on_commit(deliver)


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


def build_full_url(path):
    # Builds an absolute URL for emails using the canonical domain.
    # SITE_URL sempre existe (tem default em settings.py) e já vem sem barra
    # final, por isso não há fallback: um placeholder aqui só produziria links
    # partidos dentro de emails já enviados.
    return f"{settings.SITE_URL}{path}"


def send_rendered_email(subject, body_text, body_html, recipient_list):
    # Sends text email with optional HTML alternative.
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

    context = {
        "customer_name": appointment.customer.full_name,
        "service_name": appointment.service.name,
        "cancellation_link": cancel_url,
        "appointment_date": appointment.date.strftime("%d/%m/%Y"),
        "appointment_time": appointment.start_time.strftime("%H:%M"),
        "reference_code": appointment.reference_code,
        "magic_link": full_url,
        "intro": intro,
    }

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


def send_appointment_reminder_email(
    appointment, reminder_label="", email_template=None
):
    # Sends appointment reminder email.
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

    context = {
        "customer_name": appointment.customer.full_name,
        "service_name": appointment.service.name,
        "appointment_date": appointment.date.strftime("%d/%m/%Y"),
        "appointment_time": appointment.start_time.strftime("%H:%M"),
        "reference_code": appointment.reference_code,
        "magic_link": full_url,
        "cancellation_link": cancel_url,
        "reminder_label": reminder_label,
    }

    fallback_subject = f"Lembrete da sua marcação {reminder_label}".strip()

    fallback_body = (
        f"Olá {context['customer_name']},\n\n"
        f"Este é um lembrete da sua marcação {context['reminder_label']}.\n\n"
        f"Serviço: {context['service_name']}\n"
        f"Data: {context['appointment_date']}\n"
        f"Horário: {context['appointment_time']}\n"
        f"Código: {context['reference_code']}\n\n"
        f"Ver detalhes:\n{context['magic_link']}\n\n"
        f"Cancelar marcação:\n{context['cancellation_link']}\n\n"
        f"Obrigada,\n"
        f"Priscila Arantes PA"
    )

    rendered_email = render_email_for_event(
        event_type=EmailEventSetting.EVENT_APPOINTMENT_REMINDER,
        template_key="appointment_reminder",
        context=context,
        fallback_subject=fallback_subject,
        fallback_body=fallback_body,
        email_template=email_template,
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

