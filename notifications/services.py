from django.conf import settings
from django.template import Context, Template

from .models import EmailEventSetting, EmailTemplate


class EmailTemplateService:
    # Handles loading and rendering of email templates.

    # `language` atravessa os três: é a língua da cliente, e só ela decide
    # qual das versões do modelo se usa. Fica a `None` para os avisos à
    # profissional e para a pré-visualização no admin, que são em português.
    @staticmethod
    def render(
        template_key, context_data, fallback_subject, fallback_body, language=None
    ):
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
            language=language,
        )

    @staticmethod
    def render_template_or_fallback(
        email_template, context_data, fallback_subject, fallback_body, language=None
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
            language=language,
        )

    @staticmethod
    def render_template_object(email_template, context_data, language=None):
        # Render a specific EmailTemplate instance for admin preview.
        versao = email_template.for_language(language)

        subject = Template(versao["subject"]).render(Context(context_data))
        body_text = Template(versao["body_text"]).render(Context(context_data))

        body_html = ""

        if versao["body_html"]:
            body_html = Template(versao["body_html"]).render(Context(context_data))

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
            # Usa o domínio canónico real para a pré-visualização mostrar os
            # links tal como a cliente os vai receber.
            "magic_link": f"{settings.SITE_URL}/m/exemplo-token/",
            "cancellation_link": f"{settings.SITE_URL}/cancelar/AGD-EXEMPLO/",
            "booking_link": f"{settings.SITE_URL}/agenda-publica/",
            "intro": "A sua marcação foi confirmada.",
            # Usadas pelos avisos internos e pelos modelos por serviço. Estão
            # aqui para a pré-visualização não sair com buracos.
            "customer_phone": "+351910000000",
            "internal_link": f"{settings.SITE_URL}/marcacoes/1/",
            "days_after": 15,
            # A pré-visualização mostra o atendimento na clínica, que é
            # o caso comum. O texto do domicílio vê-se na janela que
            # pergunta se a cliente é avisada, com a marcação à frente.
            "is_home_visit": False,
            "home_address": "",
        }


class EmailEventSettingService:
    # Handles email event settings lookup.

    @staticmethod
    def get_active_setting(event_type, audience=EmailEventSetting.AUDIENCE_CUSTOMER):
        """A regra ativa para este acontecimento e este destinatário.

        O destinatário tem valor por omissão porque a esmagadora maioria dos
        emails é para a cliente; os avisos internos pedem-no à mão.
        """

        return (
            EmailEventSetting.objects.select_related("email_template")
            .filter(
                event_type=event_type,
                audience=audience,
                is_active=True,
            )
            .first()
        )
