import re

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
    class Meta:
        model = EmailTemplate
        fields = [
            "name",
            "key",
            "subject",
            "body_text",
            "body_html",
            "is_active",
        ]
        labels = {
            "name": "Nome",
            "key": "Identificador",
            "subject": "Assunto",
            "body_text": "Texto",
            "body_html": "HTML (opcional)",
            "is_active": "Ativo",
        }
        help_texts = {
            "key": ("Identificador interno, sem espaços. Exemplo: cuidados_pos_calos."),
            "body_html": (
                "Deixe vazio para enviar só texto. Se preencher, o cliente vê "
                "esta versão e o texto acima serve de alternativa."
            ),
        }
        widgets = {
            "subject": forms.TextInput(attrs={"class": "form-control"}),
            "body_text": forms.Textarea(attrs={"rows": 14}),
            "body_html": forms.Textarea(attrs={"rows": 10}),
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

        for campo in ["subject", "body_text", "body_html"]:
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
            "provider",
            "body_template",
            "meta_template_body",
            "content_sid",
            "content_variables",
            "is_active",
        ]
        widgets = {
            "body_template": forms.Textarea(attrs={"rows": 5}),
            "meta_template_body": forms.Textarea(attrs={"rows": 5}),
            "content_variables": forms.Textarea(attrs={"rows": 5}),
        }

    def clean_content_sid(self):
        sid = (self.cleaned_data.get("content_sid") or "").strip()

        if sid and not sid.startswith("HX"):
            raise ValidationError(
                "O Content SID da Twilio começa por HX. Confirme que não colou "
                "outro identificador."
            )

        return sid

    def clean_body_template(self):
        # Um erro de sintaxe só apareceria no momento do envio, quando já não
        # há ninguém a olhar para o ecrã.
        corpo = self.cleaned_data.get("body_template") or ""

        try:
            Template(corpo)
        except TemplateSyntaxError as erro:
            raise ValidationError(f"Erro na sintaxe da mensagem: {erro}") from erro

        return corpo

    def clean_meta_template_body(self):
        """As regras que mais rejeições causam na revisão da Meta.

        Descobri-las por um email de recusa, dias depois de submeter, custa
        muito mais do que apanhá-las aqui.
        """

        corpo = (self.cleaned_data.get("meta_template_body") or "").strip()

        if not corpo:
            return corpo

        posicoes = re.findall(r"\{\{\s*(\d+)\s*\}\}", corpo)

        if re.match(r"^\{\{\s*\d+\s*\}\}", corpo):
            raise ValidationError(
                "O texto não pode começar por uma posição. A Meta rejeita."
            )

        if re.search(r"\{\{\s*\d+\s*\}\}$", corpo):
            raise ValidationError(
                "O texto não pode terminar numa posição. A Meta rejeita."
            )

        if re.search(r"\}\}\s*\{\{", corpo):
            raise ValidationError(
                "Duas posições seguidas sem texto entre elas. A Meta rejeita."
            )

        if posicoes:
            numeros = [int(n) for n in posicoes]

            if sorted(set(numeros)) != list(range(1, max(numeros) + 1)):
                raise ValidationError(
                    "As posições têm de ser seguidas a partir de 1, sem saltos."
                )

        if len(corpo) > 1024:
            raise ValidationError("A Meta limita o corpo a 1024 caracteres.")

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
        fields = ["is_enabled"]
        labels = {
            "is_enabled": "Enviar mensagens",
        }
        widgets = {
            "is_enabled": forms.CheckboxInput(
                attrs={"class": "form-check-input", "role": "switch"}
            ),
        }
