from django.template import Context, Template

from .models import EmailEventSetting, EmailTemplate


class EmailTemplateService:
    # Handles loading and rendering of email templates.

    @staticmethod
    def render(template_key, context_data, fallback_subject, fallback_body):
        # Render email using DB template or fallback.
        template = EmailTemplate.objects.filter(
            key=template_key,
            is_active=True,
        ).first()

        return EmailTemplateService.render_template_or_fallback(
            email_template=template,
            context_data=context_data,
            fallback_subject=fallback_subject,
            fallback_body=fallback_body,
        )

    @staticmethod
    def render_template_or_fallback(
        email_template, context_data, fallback_subject, fallback_body
    ):
        # Render a specific template when available; otherwise use fallback content.
        if not email_template or not email_template.is_active:
            return {
                "subject": fallback_subject,
                "body_text": fallback_body,
                "body_html": "",
            }

        return EmailTemplateService.render_template_object(
            email_template=email_template,
            context_data=context_data,
        )

    @staticmethod
    def render_template_object(email_template, context_data):
        # Render a specific EmailTemplate instance for admin preview.
        subject = Template(email_template.subject).render(Context(context_data))
        body_text = Template(email_template.body_text).render(Context(context_data))

        body_html = ""

        if email_template.body_html:
            body_html = Template(email_template.body_html).render(Context(context_data))

        return {
            "subject": subject,
            "body_text": body_text,
            "body_html": body_html,
        }

    @staticmethod
    def get_sample_context():
        # Provides safe sample data for admin email preview.
        return {
            "customer_name": "Maria Silva",
            "service_name": "Podologia",
            "appointment_date": "30/04/2026",
            "appointment_time": "10:30",
            "reference_code": "AGD-EXEMPLO",
            "cancellation_reason": "Cliente informou que não poderá comparecer.",
            "magic_link": "https://seudominio.com/m/exemplo-token/",
            "cancellation_link": "https://seudominio.com/cancelar/AGD-EXEMPLO/",
            "reminder_label": "1 dia antes",
            "intro": "A sua marcação foi confirmada.",
        }


class EmailEventSettingService:
    # Handles email event settings lookup.

    @staticmethod
    def get_active_setting(event_type):
        # Returns the active setting for non-reminder email events.
        return (
            EmailEventSetting.objects.select_related("email_template")
            .filter(
                event_type=event_type,
                is_active=True,
            )
            .first()
        )

    @staticmethod
    def get_active_reminder_settings():
        # Returns all active reminder settings configured in admin.
        return (
            EmailEventSetting.objects.select_related("email_template")
            .filter(
                event_type=EmailEventSetting.EVENT_APPOINTMENT_REMINDER,
                is_active=True,
            )
            .order_by("lead_time_unit", "lead_time_value", "id")
        )
