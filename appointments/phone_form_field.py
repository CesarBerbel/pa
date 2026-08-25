"""O telefone no formulário: um seletor de indicativo e o número.

Era uma caixa de texto só, e o mesmo número chegava de cinco maneiras — com
`00`, com `+`, com o zero à frente, com o indicativo esquecido. O que ficava
guardado dependia de quem o tinha escrito, e o WhatsApp não perdoa nenhuma
dessas diferenças.

Em duas peças, o indicativo deixa de ser escrito: vem de uma lista, e o que
sobra para a pessoa escrever é só o número dela. O que sai daqui é sempre
E.164 — `+`, indicativo, número — que é o que a Meta e a Twilio esperam e a
única forma em que dois números iguais se parecem.

O que é guardado continua a ser um campo de texto só, com o número inteiro:
o país não é um dado à parte, é o princípio do número.
"""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from appointments import phone_countries
from appointments.customer_services import normalize_phone, validate_phone


class PhoneWidget(forms.MultiWidget):
    """O seletor de país e a caixa do número, lado a lado.

    O seletor é um `<select>` a sério, e não uma lista desenhada à mão: sem
    JavaScript continua a funcionar, e com ele ganha uma caixa de procura por
    cima. Duzentos países numa lista pendente encontram-se a escrever, mas só
    se o teclado ajudar — e num telemóvel não ajuda.
    """

    template_name = "appointments/widgets/phone.html"

    def __init__(self, attrs=None):
        atributos_do_numero = {
            "class": "form-control",
            "inputmode": "tel",
            "autocomplete": "tel-national",
            "placeholder": "912 345 678",
        }
        atributos_do_numero.update(attrs or {})

        super().__init__(
            widgets=[
                forms.Select(
                    choices=self.escolhas(),
                    attrs={"class": "form-select", "data-phone-country": ""},
                ),
                forms.TextInput(attrs=atributos_do_numero),
            ]
        )

    @staticmethod
    def escolhas():
        return [
            (iso, f"{nome} (+{indicativo})")
            for iso, nome, indicativo in phone_countries.ordenados()
        ]

    def value_from_datadict(self, data, files, name):
        """Aceita as duas caixas, ou o número inteiro num campo só.

        O campo passou a ter duas peças, mas um número inteiro continua a ser
        um número inteiro: um pedido escrito antes disto — ou de fora do
        formulário — não pode passar a ser recusado por ter escrito
        `phone=+351912345678` em vez de `phone_0` e `phone_1`.
        """

        if name in data and f"{name}_1" not in data:
            inteiro = data.get(name) or ""

            return self.decompress(inteiro) if inteiro else ["", ""]

        return super().value_from_datadict(data, files, name)

    def decompress(self, value):
        """Parte o número guardado nas duas caixas, para o poder editar."""

        if not value:
            return [phone_countries.PAIS_POR_OMISSAO, ""]

        pais, resto = phone_countries.separar(normalize_phone(value) or value)

        return [pais or phone_countries.PAIS_POR_OMISSAO, resto]


class PhoneField(forms.MultiValueField):
    """Um campo só, com duas caixas, que devolve o número em E.164."""

    widget = PhoneWidget

    def __init__(self, **kwargs):
        obrigatorio = kwargs.pop("required", True)

        campos = (
            forms.ChoiceField(choices=PhoneWidget.escolhas(), required=obrigatorio),
            forms.CharField(
                required=obrigatorio,
                # Sem isto sai "Introduza um valor completo", que não diz a
                # ninguém qual das duas caixas ficou por preencher.
                error_messages={"incomplete": "Indique o número de telefone."},
            ),
        )

        kwargs.setdefault("require_all_fields", False)

        super().__init__(fields=campos, required=obrigatorio, **kwargs)

    def compress(self, valores):
        if not valores:
            return ""

        pais, numero = valores[0], (valores[1] or "").strip()

        if not numero:
            if self.required:
                raise ValidationError("Indique o número de telefone.")

            return ""

        # O número escrito à mão pode trazer o indicativo outra vez, ou o zero
        # do trunk que se marca dentro do país. Nenhum dos dois entra no E.164.
        indicativo = phone_countries.indicativo(pais)
        digitos = "".join(caracter for caracter in numero if caracter.isdigit())

        if numero.strip().startswith("+"):
            # Escreveu o número internacional inteiro: manda ele, e o seletor
            # que se cale. Recusá-lo seria recusar o número certo.
            return validate_phone(numero)

        if digitos.startswith("00"):
            return validate_phone(f"+{digitos[2:]}")

        if digitos.startswith(indicativo):
            return validate_phone(f"+{digitos}")

        return validate_phone(f"+{indicativo}{digitos.lstrip('0')}")
