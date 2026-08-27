from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from appointments.availability import AvailabilityService
from appointments.customer_services import find_or_create_customer
from appointments.phone_form_field import PhoneField
from appointments.rich_text import esta_vazio
from notifications.models import BeforeAfterCase

from .models import (
    Appointment,
    BusinessHour,
    ClinicalNote,
    ConditionQuestion,
    Customer,
    PatientRecord,
    SchedulingSetting,
    ScheduleBlock,
    Service,
    TreatedCondition,
    get_default_service_category,
)


class BusinessHourForm(forms.ModelForm):
    # Form used to create and edit working hours.

    class Meta:
        model = BusinessHour
        fields = [
            "weekday",
            "start_time",
            "end_time",
            "second_start_time",
            "second_end_time",
            "is_active",
        ]
        labels = {
            "weekday": "Dia da semana",
            "start_time": "Hora inicial (manhã)",
            "end_time": "Hora final (manhã)",
            "second_start_time": "Hora inicial (tarde)",
            "second_end_time": "Hora final (tarde)",
            "is_active": "Ativo",
        }
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
            "second_start_time": forms.TimeInput(attrs={"type": "time"}),
            "second_end_time": forms.TimeInput(attrs={"type": "time"}),
        }


class ServiceForm(forms.ModelForm):
    # Form used to create and edit services.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Keep the category field flexible for older internal flows/tests that
        # predate service categories. When no category is posted, save() assigns
        # the first active category or creates a safe fallback category.
        self.fields["category"].required = False

        # Um serviço sem retorno sugerido é o caso normal — a maior parte não
        # tem. Obrigar a escrever um zero seria ruído no formulário.
        self.fields["return_days"].required = False

    def clean_return_days(self):
        return self.cleaned_data.get("return_days") or 0

    class Meta:
        model = Service
        fields = [
            "category",
            "name",
            "description",
            "duration_minutes",
            # O prazo proposto para voltar, ao concluir um atendimento deste
            # serviço. Uma unha encravada revê-se em duas semanas, um pé
            # diabético em três meses — quem sabe isso é quem trata.
            "return_days",
            "price",
            "is_active",
        ]

    def save(self, commit=True):
        instance = super().save(commit=False)

        if not instance.category_id:
            instance.category = get_default_service_category()

        if commit:
            instance.save()
            self.save_m2m()

        return instance


class BeforeAfterCaseForm(forms.ModelForm):
    """Formulário do caso antes e depois, na área interna.

    Ao editar, as fotografias já guardadas não têm de ser carregadas outra vez
    — é por isso que deixam de ser obrigatórias assim que existe uma no
    registo. Sem isto, mudar só a legenda obrigava a ir buscar os ficheiros ao
    computador.
    """

    class Meta:
        model = BeforeAfterCase
        fields = [
            "title",
            "caption",
            "before_image",
            "after_image",
            "reveal_orientation",
            "display_order",
            "is_active",
            # Escondidos: quem os mexe é o editor de enquadramento, à conta
            # da pré-visualização. Escritos à mão seriam seis números sem
            # significado nenhum para quem os lê.
            "before_zoom",
            "before_focus_x",
            "before_focus_y",
            "after_zoom",
            "after_focus_x",
            "after_focus_y",
        ]
        widgets = {
            # As duas opções à vista: escondida numa lista pendente, a
            # escolha passava despercebida a quem não soubesse que existe.
            "reveal_orientation": forms.RadioSelect(),
            "before_zoom": forms.HiddenInput(),
            "before_focus_x": forms.HiddenInput(),
            "before_focus_y": forms.HiddenInput(),
            "after_zoom": forms.HiddenInput(),
            "after_focus_x": forms.HiddenInput(),
            "after_focus_y": forms.HiddenInput(),
        }

    ENQUADRAMENTO = {
        "before_zoom": 100,
        "before_focus_x": 50,
        "before_focus_y": 50,
        "after_zoom": 100,
        "after_focus_x": 50,
        "after_focus_y": 50,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for campo in ("before_image", "after_image"):
            if getattr(self.instance, campo, None):
                self.fields[campo].required = False

        # O enquadramento vem de campos escondidos que o editor preenche. Um
        # formulário submetido sem eles é um enquadramento por decidir, não um
        # erro: vale o valor de origem, que é a fotografia inteira e centrada.
        for campo in self.ENQUADRAMENTO:
            self.fields[campo].required = False

        # Pela mesma razão: um formulário sem a direção da linha é uma
        # direção por decidir, e vale a que a página sempre teve.
        self.fields["reveal_orientation"].required = False

    def clean(self):
        dados = super().clean()

        for campo, omissao in self.ENQUADRAMENTO.items():
            if dados.get(campo) in (None, ""):
                dados[campo] = omissao

        if not dados.get("reveal_orientation"):
            dados["reveal_orientation"] = BeforeAfterCase.REVEAL_VERTICAL

        return dados


class CustomerForm(forms.ModelForm):
    # Form used to create and edit customers.

    # O indicativo deixa de ser escrito: vem de uma lista, e o que sai daqui
    # é sempre E.164. `clean_phone` fazia esse trabalho a adivinhar o país
    # pelo número de dígitos, e só sabia adivinhar dois.
    phone = PhoneField(label="Telefone")

    class Meta:
        model = Customer
        fields = [
            "full_name",
            "email",
            "phone",
        ]


class EncaixeMixin:
    """Aceita o horário mesmo fora do funcionamento ou sobre um bloqueio.

    Quem marca a partir da área interna está com a agenda à frente e decidiu
    encaixar a pessoa. O sistema regista que foi fora do normal em vez de
    recusar; o que continua a ser recusado é a sobreposição com outra marcação,
    que não é uma questão de política.

    Vive aqui e não numa das duas classes porque marcar e remarcar têm de tratar
    o encaixe da mesma maneira: escrito duas vezes, uma delas ficava para trás.
    """

    def resolve_schedule_override(self, cleaned_data):
        """Fica em `self.instance` porque `outside_schedule` não é um campo do
        formulário, e portanto `construct_instance` não lhe toca antes da
        validação do modelo."""

        self.schedule_override_reason = AvailabilityService.schedule_conflict(
            cleaned_data.get("service"),
            cleaned_data.get("date"),
            cleaned_data.get("start_time"),
        )

        self.instance.outside_schedule = bool(self.schedule_override_reason)


class AppointmentRescheduleForm(EncaixeMixin, forms.ModelForm):
    """Remarcar: muda-se o serviço, o dia, a hora e o estado. Mais nada.

    A cliente não se troca aqui. Trocá-la seria transformar a marcação de uma
    pessoa na marcação de outra, e o histórico ficava a dizer que a primeira
    tinha sido atendida — para marcar outra pessoa faz-se uma marcação nova.

    A morada do domicílio e as observações também não estão neste formulário.
    Não se perdem: um `ModelForm` só escreve os campos que tem, e o que já lá
    estava fica como estava.
    """

    class Meta:
        model = Appointment
        fields = [
            "service",
            "date",
            "start_time",
            "status",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Preenchido em clean() quando o horário sai do funcionamento normal,
        # para a vista o poder dizer a quem remarcou.
        self.schedule_override_reason = None

    def clean(self):
        cleaned_data = super().clean()

        self.resolve_schedule_override(cleaned_data)

        return cleaned_data


class AppointmentForm(EncaixeMixin, forms.ModelForm):
    # Form used to create and edit appointments. Permite registar um cliente
    # novo na mesma submissão, para não obrigar a sair para a página de
    # clientes a meio de uma marcação feita ao telefone.

    CUSTOMER_MODE_EXISTING = "existing"
    CUSTOMER_MODE_NEW = "new"

    CUSTOMER_MODE_CHOICES = [
        (CUSTOMER_MODE_EXISTING, "Escolher cliente já registado"),
        (CUSTOMER_MODE_NEW, "Registar cliente novo"),
    ]

    customer_mode = forms.ChoiceField(
        label="Cliente",
        choices=CUSTOMER_MODE_CHOICES,
        initial=CUSTOMER_MODE_EXISTING,
        widget=forms.RadioSelect,
    )

    new_customer_name = forms.CharField(
        label="Nome completo do cliente novo",
        max_length=255,
        required=False,
    )

    new_customer_phone = PhoneField(
        label="Telefone do cliente novo",
        required=False,
    )

    new_customer_email = forms.EmailField(
        label="Email do cliente novo",
        required=False,
        help_text="Opcional. Sem email, o cliente não recebe confirmação nem lembretes.",
    )

    # Preenchido pela janela que aparece ao gravar uma marcação nova. Fica num
    # campo escondido, e não numa caixa no meio do formulário, porque a pergunta
    # só faz sentido no momento de gravar: até lá ainda não há marcação nenhuma
    # para confirmar.
    send_confirmation = forms.BooleanField(
        required=False,
        widget=forms.HiddenInput,
    )

    # Campos declarados entram depois dos do modelo, o que deixaria a escolha
    # do tipo de cliente no fim do formulário. A ordem é fixada aqui.
    field_order = [
        "customer_mode",
        "customer",
        "new_customer_name",
        "new_customer_phone",
        "new_customer_email",
        "customer_speaks_english",
        "service",
        "date",
        "start_time",
        "status",
        "is_home_visit",
        "home_street",
        "home_number",
        "home_floor",
        "home_postal_code",
        "home_locality",
        "home_municipality",
        "home_district",
        "home_country",
        "home_directions",
        "notes",
    ]

    class Meta:
        model = Appointment
        fields = [
            "customer",
            "customer_speaks_english",
            "service",
            "date",
            "start_time",
            "status",
            "is_home_visit",
            "home_street",
            "home_number",
            "home_floor",
            "home_postal_code",
            "home_locality",
            "home_municipality",
            "home_district",
            "home_country",
            "home_directions",
            "notes",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "home_directions": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Preenchido em clean() quando o horário sai do funcionamento normal,
        # para a vista o poder dizer a quem marcou.
        self.schedule_override_reason = None

        # A obrigatoriedade passa a depender do modo escolhido e é verificada
        # em clean(), não pelo campo em si.
        self.fields["customer"].required = False
        self.fields["customer"].label = "Cliente já registado"

        # A pergunta é sobre a mensagem que anuncia a marcação, por isso só se
        # põe quando a marcação está a nascer. A editar, quem quiser avisar a
        # cliente tem o ecrã de detalhe.
        if self.instance.pk:
            del self.fields["send_confirmation"]

    def clean(self):
        cleaned_data = super().clean()
        mode = cleaned_data.get("customer_mode")

        if mode == self.CUSTOMER_MODE_NEW:
            cleaned_data["customer"] = self.resolve_new_customer(cleaned_data)
        elif not cleaned_data.get("customer"):
            self.add_error("customer", "Selecione o cliente ou registe um novo.")

        self.resolve_home_visit(cleaned_data)
        self.resolve_schedule_override(cleaned_data)

        return cleaned_data

    # Os campos da morada, para os limpar e os validar como um conjunto.
    CAMPOS_DA_MORADA = [
        "home_street",
        "home_number",
        "home_floor",
        "home_postal_code",
        "home_locality",
        "home_municipality",
        "home_district",
        "home_country",
        "home_directions",
    ]

    def resolve_home_visit(self, cleaned_data):
        """A rua só é obrigatória quando o atendimento é em domicílio.

        E o contrário também conta: desmarcar o domicílio limpa a morada e as
        indicações, senão ficavam guardadas numa marcação que passou a ser na
        clínica — e apareciam no ecrã do dia a mandar a profissional sair.
        """

        if not cleaned_data.get("is_home_visit"):
            for campo in self.CAMPOS_DA_MORADA:
                cleaned_data[campo] = ""

            return

        # Só a rua. Uma morada de aldeia pode não ter número nem código postal
        # conhecido, e exigi-los impedia de marcar um atendimento que existe.
        if not (cleaned_data.get("home_street") or "").strip():
            self.add_error(
                "home_street",
                "Indique a rua: é para onde a profissional se desloca.",
            )

    def resolve_new_customer(self, cleaned_data):
        # Reutiliza find_or_create_customer, que devolve o cliente existente
        # quando o email ou o telefone já são conhecidos. Assim, reenviar o
        # formulário depois de um erro de conflito não duplica o registo.
        name = (cleaned_data.get("new_customer_name") or "").strip()
        phone = (cleaned_data.get("new_customer_phone") or "").strip()
        email = (cleaned_data.get("new_customer_email") or "").strip()

        if not name:
            self.add_error("new_customer_name", "Indique o nome do cliente novo.")

        # O campo do telefone já devolve E.164 ou levanta o erro dele: aqui
        # só falta o caso de ninguém ter escrito nada.
        if not phone:
            self.add_error("new_customer_phone", "Indique o telefone do cliente novo.")

        if not name or not phone:
            return None

        return find_or_create_customer(name=name, phone=phone, email=email)


class PatientRecordForm(forms.ModelForm):
    """Anamnese podológica. Só usada na área interna: contém dados de saúde.

    Os campos estão agrupados em secções que o template usa para montar o
    acordeão. Manter os grupos aqui, e não no template, evita que um campo novo
    no modelo fique invisível por esquecimento.
    """

    # Antecedentes marcados com um toque. São caixas e não texto livre porque
    # alimentam os avisos que aparecem no atendimento.
    CAMPOS_ANTECEDENTES = [
        "has_diabetes",
        "has_neuropathy",
        "has_circulatory_issues",
        "has_cardiovascular_issues",
        "has_hypertension",
        "has_coagulation_issues",
        "has_rheumatic_disease",
        "has_thyroid_disease",
        "has_kidney_disease",
        "has_skin_condition",
        "is_pregnant",
        "is_smoker",
        "has_allergies",
    ]

    SECCOES = [
        (
            "identificacao",
            "Identificação",
            ["birth_date", "profession"],
        ),
        (
            "motivo",
            "Motivo da consulta",
            ["main_complaint"],
        ),
        (
            "antecedentes",
            "Antecedentes",
            CAMPOS_ANTECEDENTES
            + [
                "allergies",
                "medical_history",
                "current_medication",
                "previous_surgeries",
            ],
        ),
        (
            "exame",
            "Exame podológico",
            [
                "skin_assessment",
                "nail_assessment",
                "foot_deformities",
                "gait_assessment",
                "footwear_notes",
            ],
        ),
        (
            "vascular",
            "Vascular e neurológico",
            [
                "vascular_assessment",
                "neurological_assessment",
                "diabetic_foot_risk",
            ],
        ),
        (
            "plano",
            "Plano e observações",
            ["treatment_plan", "notes", "consent_confirmed"],
        ),
    ]

    class Meta:
        model = PatientRecord
        fields = [
            "birth_date",
            "profession",
            "main_complaint",
            "has_diabetes",
            "has_neuropathy",
            "has_circulatory_issues",
            "has_cardiovascular_issues",
            "has_hypertension",
            "has_coagulation_issues",
            "has_rheumatic_disease",
            "has_thyroid_disease",
            "has_kidney_disease",
            "has_skin_condition",
            "is_pregnant",
            "is_smoker",
            "has_allergies",
            "allergies",
            "medical_history",
            "current_medication",
            "previous_surgeries",
            "skin_assessment",
            "nail_assessment",
            "foot_deformities",
            "gait_assessment",
            "footwear_notes",
            "vascular_assessment",
            "neurological_assessment",
            "diabetic_foot_risk",
            "treatment_plan",
            "notes",
            "consent_confirmed",
        ]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "main_complaint": forms.Textarea(attrs={"rows": 3}),
            "allergies": forms.Textarea(attrs={"rows": 2}),
            "medical_history": forms.Textarea(attrs={"rows": 3}),
            "current_medication": forms.Textarea(attrs={"rows": 3}),
            "previous_surgeries": forms.Textarea(attrs={"rows": 3}),
            "skin_assessment": forms.Textarea(attrs={"rows": 3}),
            "nail_assessment": forms.Textarea(attrs={"rows": 3}),
            "foot_deformities": forms.Textarea(attrs={"rows": 3}),
            "gait_assessment": forms.Textarea(attrs={"rows": 2}),
            "footwear_notes": forms.Textarea(attrs={"rows": 3}),
            "vascular_assessment": forms.Textarea(attrs={"rows": 3}),
            "neurological_assessment": forms.Textarea(attrs={"rows": 3}),
            "treatment_plan": forms.Textarea(attrs={"rows": 4}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def sections(self):
        # Devolve (id, título, [campos ligados]) para o template iterar.
        for identificador, titulo, nomes in self.SECCOES:
            yield {
                "id": identificador,
                "title": titulo,
                "fields": [self[nome] for nome in nomes if nome in self.fields],
                "flags": [
                    self[nome]
                    for nome in nomes
                    if nome in self.CAMPOS_ANTECEDENTES and nome in self.fields
                ],
                "regular": [
                    self[nome]
                    for nome in nomes
                    if nome not in self.CAMPOS_ANTECEDENTES and nome in self.fields
                ],
            }

    def missing_fields(self):
        # Rede de segurança: um campo do modelo que fique fora das secções
        # deixaria de ser editável sem ninguém dar por isso.
        agrupados = {nome for _i, _t, nomes in self.SECCOES for nome in nomes}
        return [self[nome] for nome in self.fields if nome not in agrupados]


class ClinicalNoteForm(forms.ModelForm):
    # Nota de evolução de uma consulta: o que foi feito.

    class Meta:
        model = ClinicalNote
        fields = ["procedures", "observations", "recommendations"]
        widgets = {
            "procedures": forms.Textarea(attrs={"rows": 4}),
            "observations": forms.Textarea(attrs={"rows": 4}),
            "recommendations": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_procedures(self):
        procedures = (self.cleaned_data.get("procedures") or "").strip()

        if not procedures:
            raise ValidationError("Descreva os atos praticados nesta consulta.")

        return procedures


class CategoryServiceChoiceField(forms.ModelChoiceField):
    # Displays services grouped by category in human-friendly labels.

    def label_from_instance(self, obj):
        return f"{obj.category.display_name} — {obj.display_name}"


class PublicAppointmentForm(forms.Form):
    # Public booking form used by customers without login.

    service = CategoryServiceChoiceField(
        label="Serviço",
        queryset=Service.objects.filter(
            is_active=True,
            category__is_active=True,
            category__is_coming_soon=False,
        ).select_related("category"),
        empty_label="Selecione um serviço",
    )

    date = forms.DateField(
        label="Data",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    start_time = forms.CharField(
        label="Horário",
        required=True,
        widget=forms.Select(
            choices=[
                ("", "Selecione um horário"),
            ]
        ),
    )

    customer_name = forms.CharField(
        label="Nome completo",
        max_length=255,
        required=True,
    )

    customer_phone = PhoneField(label="Telefone")

    customer_email = forms.EmailField(
        label="Email",
        required=False,
    )

    notes = forms.CharField(
        label="Observações",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    privacy_policy_accepted = forms.BooleanField(
        label="Li e aceito a Política de Privacidade.",
        required=True,
        error_messages={
            "required": (
                "Tem de aceitar a Política de Privacidade para confirmar a marcação."
            ),
        },
    )


class ScheduleBlockForm(forms.ModelForm):
    # Form used to create and edit schedule blocks with weekday checkboxes.

    recurring_weekdays_checkboxes = forms.MultipleChoiceField(
        label="Dias da semana da recorrência",
        required=False,
        choices=ScheduleBlock.WEEKDAY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = ScheduleBlock
        fields = [
            # Sem título: o tipo já diz o que é ("Pausa", "Férias") e as notas
            # dizem o resto. Pedir os três era pedir a mesma coisa duas vezes.
            "block_type",
            "date",
            "start_time",
            "end_time",
            "is_full_day",
            "is_recurring",
            "recurring_weekdays_checkboxes",
            "recurrence_end_date",
            "is_active",
            "notes",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
            "recurrence_end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        # Load saved comma-separated weekdays into checkbox values.
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields["recurring_weekdays_checkboxes"].initial = (
                self.instance.get_recurring_weekday_list()
            )

    def clean(self):
        # Convert selected weekdays before model validation.
        cleaned_data = super().clean()

        is_recurring = cleaned_data.get("is_recurring")
        selected_weekdays = cleaned_data.get("recurring_weekdays_checkboxes") or []

        recurring_weekdays = ",".join(selected_weekdays)

        cleaned_data["recurring_weekdays"] = recurring_weekdays
        self.instance.recurring_weekdays = recurring_weekdays

        if is_recurring and not selected_weekdays:
            raise forms.ValidationError(
                "Selecione pelo menos um dia da semana para o bloqueio recorrente."
            )

        return cleaned_data

    def _post_clean(self):
        # Ensure the model receives checkbox values before full_clean.
        selected_weekdays = self.cleaned_data.get("recurring_weekdays_checkboxes") or []
        self.instance.recurring_weekdays = ",".join(selected_weekdays)

        super()._post_clean()

    def save(self, commit=True):
        # Save checkbox values into the model text field.
        instance = super().save(commit=False)

        selected_weekdays = self.cleaned_data.get("recurring_weekdays_checkboxes") or []
        instance.recurring_weekdays = ",".join(selected_weekdays)

        if commit:
            instance.save()

        return instance


class PublicCancelForm(forms.Form):
    # Form to cancel appointment by reference code.

    reference_code = forms.CharField(
        label="Código da marcação",
        max_length=20,
    )

    cancellation_reason = forms.CharField(
        label="Motivo do cancelamento",
        required=True,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Indique o motivo do cancelamento.",
            }
        ),
    )

    def clean_reference_code(self):
        # Normalize reference code before cancellation.
        reference_code = self.cleaned_data["reference_code"]

        return reference_code.strip().upper()

    def clean_cancellation_reason(self):
        # Normalize cancellation reason before saving.
        cancellation_reason = self.cleaned_data["cancellation_reason"].strip()

        if len(cancellation_reason) < 5:
            raise forms.ValidationError(
                "Indique um motivo com pelo menos 5 caracteres."
            )

        return cancellation_reason


class PublicAppointmentLookupForm(forms.Form):
    # Form used to search public appointments by reference code or request details by email.

    reference_code = forms.CharField(
        label="Código da marcação",
        max_length=20,
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Exemplo: AGD-8F3K2L",
                "class": "form-control text-uppercase",
                "autocomplete": "off",
            }
        ),
        help_text="Use esta opção se já tiver o código de referência da marcação.",
    )

    email = forms.EmailField(
        label="Email utilizado na marcação",
        required=False,
        widget=forms.EmailInput(
            attrs={
                "placeholder": "exemplo@email.com",
                "class": "form-control",
                "autocomplete": "email",
            }
        ),
        help_text=(
            "Use esta opção para receber no email os detalhes e o código "
            "das marcações em aberto."
        ),
    )

    def clean(self):
        # Require exactly one lookup method to avoid ambiguous public searches.
        cleaned_data = super().clean()

        if self.errors:
            return cleaned_data

        reference_code = (cleaned_data.get("reference_code") or "").strip().upper()
        email = (cleaned_data.get("email") or "").strip().lower()

        cleaned_data["reference_code"] = reference_code
        cleaned_data["email"] = email

        if not reference_code and not email:
            raise forms.ValidationError(
                "Indique o código da marcação ou o email utilizado na marcação."
            )

        if reference_code and email:
            raise forms.ValidationError(
                "Indique apenas uma das alternativas: código da marcação ou email."
            )

        return cleaned_data


class AppointmentCancelForm(forms.Form):
    # Internal form used by staff to cancel appointments with a required reason.

    cancellation_reason = forms.CharField(
        label="Motivo do cancelamento",
        required=True,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Indique o motivo do cancelamento.",
            }
        ),
    )

    def clean_cancellation_reason(self):
        # Normalize and validate cancellation reason.
        cancellation_reason = self.cleaned_data["cancellation_reason"].strip()

        if len(cancellation_reason) < 5:
            raise forms.ValidationError(
                "Indique um motivo com pelo menos 5 caracteres."
            )

        return cancellation_reason


class SchedulingSettingForm(forms.ModelForm):
    class Meta:
        model = SchedulingSetting
        fields = [
            "slot_minutes",
            "booking_min_advance_hours",
            "booking_horizon_days",
            "cancellation_min_advance_hours",
        ]
        widgets = {
            "slot_minutes": forms.RadioSelect,
        }

    def clean_booking_horizon_days(self):
        dias = self.cleaned_data["booking_horizon_days"]

        # Zero fechava o site a marcações sem o dizer em lado nenhum. Quem
        # quiser fechar a agenda desliga os serviços ou o horário.
        if dias < 1:
            raise forms.ValidationError(
                "Tem de haver pelo menos um dia, senão o site deixa de aceitar "
                "marcações sem o dizer."
            )

        return dias


class TreatedConditionForm(forms.ModelForm):
    """A página de um problema, editada na área interna.

    O que este formulário tem de diferente dos outros é a ordem: primeiro o
    que a pessoa lê, depois o que o Google lê. Postos ao contrário, quem
    escreve começa por preencher etiquetas antes de saber o que a página vai
    dizer.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # O endereço escreve-se uma vez. Mudá-lo depois de a página estar
        # indexada é começar do zero aos olhos do Google, e por isso ele avisa
        # em vez de se deixar mudar sem uma palavra.
        if self.instance.pk:
            self.fields["slug"].help_text = (
                "Já está a ser usado. Mudá-lo agora quebra as ligações que "
                "existirem para esta página e faz o Google recomeçar."
            )

        # O texto não é obrigatório: uma página escreve-se aos bocados, e um
        # formulário que recusa guardar meio texto obriga a escrever tudo de
        # uma vez. O que não se pode é publicá-la vazia — isso é o `clean()`.
        self.fields["body"].required = False

        self.fields["service"].help_text = (
            "O serviço que o botão do fim da página propõe. Sem serviço, o "
            "botão leva à agenda geral."
        )

    def clean(self):
        dados = super().clean()

        # Publicar uma página vazia é publicar um resultado de pesquisa que
        # não responde a nada. O interruptor só liga quando há o que ler.
        #
        # `esta_vazio` e não `.strip()`: um editor deixado por preencher
        # devolve `<p><br></p>`, que passa por preenchido em qualquer
        # verificação ingénua.
        if dados.get("is_published") and esta_vazio(dados.get("body", "")):
            raise ValidationError(
                {
                    "is_published": (
                        "Esta página ainda não tem texto escrito. "
                        "Escreva-o antes de a publicar."
                    )
                }
            )

        return dados

    class Meta:
        model = TreatedCondition
        fields = [
            "name",
            "slug",
            "summary",
            "hero_image",
            "hero_alt",
            "body",
            "service",
            "meta_title",
            "meta_description",
            "keywords",
            # A versão inglesa. Cada campo cai para o português quando fica
            # vazio, e isso vale campo a campo: uma tradução feita a meio não
            # deixa a página meio em branco, deixa-a meio traduzida.
            "name_en",
            "summary_en",
            "hero_image_en",
            "hero_alt_en",
            "body_en",
            "meta_title_en",
            "meta_description_en",
            "keywords_en",
            "display_order",
            "is_published",
        ]

        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3}),
            # A classe é o que o JavaScript da página procura para trocar
            # esta caixa pelo editor. Sem ele — sem JavaScript, ou se o
            # editor não carregar — continua a ser uma caixa de texto que
            # grava HTML: estraga-se o conforto, não o trabalho.
            "body": forms.Textarea(attrs={"rows": 20, "class": "editor-rico"}),
            "meta_description": forms.Textarea(attrs={"rows": 2}),
            "summary_en": forms.Textarea(attrs={"rows": 3}),
            "body_en": forms.Textarea(attrs={"rows": 20, "class": "editor-rico"}),
            "meta_description_en": forms.Textarea(attrs={"rows": 2}),
        }


class ConditionQuestionForm(forms.ModelForm):
    """Uma pergunta frequente. Vazia, não conta.

    É o que permite ter linhas em branco no fim do formulário sem obrigar a
    preenchê-las: quem tem duas perguntas guarda duas.
    """

    class Meta:
        model = ConditionQuestion
        fields = ["display_order", "question", "answer"]

        widgets = {
            "answer": forms.Textarea(attrs={"rows": 3}),
        }


ConditionQuestionFormSet = inlineformset_factory(
    TreatedCondition,
    ConditionQuestion,
    form=ConditionQuestionForm,
    extra=2,
    can_delete=True,
)
