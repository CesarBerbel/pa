from django import forms
from django.core.exceptions import ValidationError

from appointments.customer_services import (
    find_or_create_customer,
    validate_phone_for_brazil_or_portugal,
)

from .models import (
    Appointment,
    BusinessHour,
    Customer,
    ScheduleBlock,
    Service,
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
            "is_active",
        ]
        labels = {
            "weekday": "Dia da semana",
            "start_time": "Hora inicial",
            "end_time": "Hora final",
            "is_active": "Ativo",
        }
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }


class ServiceForm(forms.ModelForm):
    # Form used to create and edit services.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Keep the category field flexible for older internal flows/tests that
        # predate service categories. When no category is posted, save() assigns
        # the first active category or creates a safe fallback category.
        self.fields["category"].required = False

    class Meta:
        model = Service
        fields = [
            "category",
            "name",
            "description",
            "duration_minutes",
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


class CustomerForm(forms.ModelForm):
    # Form used to create and edit customers.

    class Meta:
        model = Customer
        fields = [
            "full_name",
            "email",
            "phone",
        ]

    def clean_phone(self):
        # Validate and normalize customer phone before saving.
        phone = self.cleaned_data["phone"]

        return validate_phone_for_brazil_or_portugal(phone)


class AppointmentForm(forms.ModelForm):
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

    new_customer_phone = forms.CharField(
        label="Telefone do cliente novo",
        max_length=30,
        required=False,
    )

    new_customer_email = forms.EmailField(
        label="Email do cliente novo",
        required=False,
        help_text="Opcional. Sem email, o cliente não recebe confirmação nem lembretes.",
    )

    # Campos declarados entram depois dos do modelo, o que deixaria a escolha
    # do tipo de cliente no fim do formulário. A ordem é fixada aqui.
    field_order = [
        "customer_mode",
        "customer",
        "new_customer_name",
        "new_customer_phone",
        "new_customer_email",
        "service",
        "date",
        "start_time",
        "status",
        "notes",
    ]

    class Meta:
        model = Appointment
        fields = [
            "customer",
            "service",
            "date",
            "start_time",
            "status",
            "notes",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # A obrigatoriedade passa a depender do modo escolhido e é verificada
        # em clean(), não pelo campo em si.
        self.fields["customer"].required = False
        self.fields["customer"].label = "Cliente já registado"

    def clean(self):
        cleaned_data = super().clean()
        mode = cleaned_data.get("customer_mode")

        if mode == self.CUSTOMER_MODE_NEW:
            cleaned_data["customer"] = self.resolve_new_customer(cleaned_data)
        elif not cleaned_data.get("customer"):
            self.add_error("customer", "Selecione o cliente ou registe um novo.")

        return cleaned_data

    def resolve_new_customer(self, cleaned_data):
        # Reutiliza find_or_create_customer, que devolve o cliente existente
        # quando o email ou o telefone já são conhecidos. Assim, reenviar o
        # formulário depois de um erro de conflito não duplica o registo.
        name = (cleaned_data.get("new_customer_name") or "").strip()
        phone = (cleaned_data.get("new_customer_phone") or "").strip()
        email = (cleaned_data.get("new_customer_email") or "").strip()

        if not name:
            self.add_error("new_customer_name", "Indique o nome do cliente novo.")

        if not phone:
            self.add_error("new_customer_phone", "Indique o telefone do cliente novo.")
        else:
            try:
                phone = validate_phone_for_brazil_or_portugal(phone)
            except ValidationError as error:
                self.add_error("new_customer_phone", error.messages[0])
                phone = ""

        if not name or not phone:
            return None

        return find_or_create_customer(name=name, phone=phone, email=email)


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

    customer_phone = forms.CharField(
        label="Telefone",
        max_length=30,
        required=True,
    )

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

    def clean_customer_phone(self):
        # Validate and normalize public customer phone before booking.
        phone = self.cleaned_data["customer_phone"]

        return validate_phone_for_brazil_or_portugal(phone)


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
            "title",
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
