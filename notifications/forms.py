from django import forms
from django.core.exceptions import ValidationError
from django.template import Template, TemplateSyntaxError

from appointments.models import Service

from .models import (
    EmailTemplate,
    MessagingSetting,
    ServiceFollowUp,
    WhatsAppEventSetting,
)


class EmailTemplateForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # A antecedência só faz sentido no lembrete: é a única mensagem que
        # sai a contar do relógio. Nas outras seria um campo a pedir um número
        # que nunca ia ser usado.
        if self.instance.key != EmailTemplate.REMINDER_KEY:
            del self.fields["reminder_hours_before"]

    def clean_reminder_hours_before(self):
        return self.cleaned_data.get("reminder_hours_before") or 0

    class Meta:
        model = EmailTemplate
        fields = [
            "name",
            "key",
            "reminder_hours_before",
            "subject",
            "body_text",
            "body_html",
            "subject_en",
            "body_text_en",
            "body_html_en",
            "is_active",
        ]
        labels = {
            "name": "Nome",
            "key": "Identificador",
            "subject": "Assunto",
            "body_text": "Texto",
            "body_html": "HTML (opcional)",
            "subject_en": "Assunto (inglês)",
            "body_text_en": "Texto (inglês)",
            "body_html_en": "HTML (inglês)",
            "is_active": "Ativo",
            "reminder_hours_before": "Antecedência (horas)",
        }
        help_texts = {
            "key": ("Identificador interno, sem espaços. Exemplo: cuidados_pos_calos."),
            "reminder_hours_before": (
                "Quantas horas antes da marcação sai este lembrete. Zero "
                "desliga-o. O comando dos lembretes corre de meia em meia "
                "hora e vem cá buscar este número."
            ),
            "body_html": (
                "Deixe vazio para enviar só texto. Se preencher, o cliente vê "
                "esta versão e o texto acima serve de alternativa."
            ),
            "subject_en": (
                "Para quem marcou na versão inglesa do site. Vazio envia o "
                "texto português."
            ),
        }
        widgets = {
            "subject": forms.TextInput(attrs={"class": "form-control"}),
            "body_text": forms.Textarea(attrs={"rows": 14}),
            "body_html": forms.Textarea(attrs={"rows": 10}),
            "subject_en": forms.TextInput(attrs={"class": "form-control"}),
            "body_text_en": forms.Textarea(attrs={"rows": 14}),
            "body_html_en": forms.Textarea(attrs={"rows": 10}),
        }

    def clean_key(self):
        return (self.cleaned_data.get("key") or "").strip().lower().replace(" ", "_")

    def _validar_sintaxe(self, campo):
        """Um erro de sintaxe só apareceria na hora de enviar, e aí é tarde.

        O corpo é renderizado como template Django para as variáveis
        funcionarem. Uma chaveta mal fechada rebentaria durante o envio, com o
        email já a caminho de ninguém.
        """

        conteudo = self.cleaned_data.get(campo) or ""

        try:
            Template(conteudo)
        except TemplateSyntaxError as erro:
            self.add_error(campo, f"Erro na sintaxe do modelo: {erro}")

        return conteudo

    def clean(self):
        cleaned_data = super().clean()

        # A versão inglesa leva as mesmas variáveis, portanto pode ter os
        # mesmos erros de sintaxe — e um erro só descoberto no envio é tarde.
        for campo in [
            "subject",
            "body_text",
            "body_html",
            "subject_en",
            "body_text_en",
            "body_html_en",
        ]:
            self._validar_sintaxe(campo)

        return cleaned_data


class ServiceFollowUpForm(forms.ModelForm):
    class Meta:
        model = ServiceFollowUp
        fields = [
            "service",
            "trigger",
            "email_template",
            "days_after",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["service"].queryset = Service.objects.filter(
            is_active=True
        ).select_related("category")

        # Um modelo inativo nunca chegaria a ser enviado; oferecê-lo aqui só
        # criaria uma regra que parece configurada e não faz nada.
        self.fields["email_template"].queryset = EmailTemplate.objects.filter(
            is_active=True
        )

        # O prazo só conta num dos três momentos. Dizê-lo aqui evita a
        # pergunta seguinte: "e se eu puser 15 dias numa mensagem manual?"
        self.fields["days_after"].label = "Dias depois (só para 'Alguns dias depois')"

    def clean(self):
        cleaned_data = super().clean()

        # Um prazo guardado numa mensagem que não é de prazo fica lá a sugerir
        # um envio que nunca acontece. Zero é o valor honesto.
        if cleaned_data.get("trigger") != ServiceFollowUp.TRIGGER_DELAYED:
            cleaned_data["days_after"] = 0

        return cleaned_data


class WhatsAppEventSettingForm(forms.ModelForm):
    class Meta:
        model = WhatsAppEventSetting
        fields = [
            "event_type",
            "audience",
            "custom_recipients",
            "body_template",
            "body_template_en",
            "is_active",
        ]
        widgets = {
            "body_template": forms.Textarea(attrs={"rows": 5}),
            "body_template_en": forms.Textarea(attrs={"rows": 5}),
        }

    def clean_body_template(self):
        # Um erro de sintaxe só apareceria no momento do envio, quando já não
        # há ninguém a olhar para o ecrã.
        corpo = self.cleaned_data.get("body_template") or ""

        try:
            Template(corpo)
        except TemplateSyntaxError as erro:
            raise ValidationError(f"Erro na sintaxe da mensagem: {erro}") from erro

        return corpo


class WhatsAppTestForm(forms.Form):
    recipient = forms.CharField(
        label="Enviar teste para",
        max_length=30,
        help_text="Com indicativo, por exemplo +351912345678.",
    )


class MessagingSettingForm(forms.ModelForm):
    class Meta:
        model = MessagingSetting
        fields = ["send_emails", "send_whatsapp"]
        widgets = {
            campo: forms.CheckboxInput(
                attrs={"class": "form-check-input", "role": "switch"}
            )
            for campo in ["send_emails", "send_whatsapp"]
        }
