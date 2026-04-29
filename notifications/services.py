from django.template import Context, Template

from .models import EmailTemplate


class EmailTemplateService:
    # Handles loading and rendering of email templates.

    @staticmethod
    def render(template_key, context_data, fallback_subject, fallback_body):
        # Render email using DB template or fallback.
        template = EmailTemplate.objects.filter(
            key=template_key,
            is_active=True,
        ).first()

        if not template:
            return {
                "subject": fallback_subject,
                "body_text": fallback_body,
                "body_html": "",
            }

        subject = Template(template.subject).render(Context(context_data))
        body_text = Template(template.body_text).render(Context(context_data))

        body_html = ""

        if template.body_html:
            body_html = Template(template.body_html).render(Context(context_data))

        return {
            "subject": subject,
            "body_text": body_text,
            "body_html": body_html,
        }

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
        }