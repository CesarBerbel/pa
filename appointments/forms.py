from django import forms

from appointments.customer_services import validate_phone_for_brazil_or_portugal

from .models import Appointment, Customer, ScheduleBlock, Service


class ServiceForm(forms.ModelForm):
    # Form used to create and edit services.

    class Meta:
        model = Service
        fields = [
            "name",
            "description",
            "duration_minutes",
            "price",
            "is_active",
        ]


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
    # Form used to create and edit appointments.

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


class PublicAppointmentForm(forms.Form):
    # Public booking form used by customers without login.

    service = forms.ModelChoiceField(
        label="Serviço",
        queryset=Service.objects.filter(is_active=True),
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
                "placeholder": "Informe o motivo do cancelamento.",
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
                "Informe um motivo com pelo menos 5 caracteres."
            )

        return cancellation_reason


class PublicAppointmentLookupForm(forms.Form):
    # Form used to search public appointment by reference code.

    reference_code = forms.CharField(
        label="Código da marcação",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Exemplo: AGD-8F3K2L",
                "class": "form-control text-uppercase",
            }
        ),
    )

    def clean_reference_code(self):
        # Normalize reference code before search.
        reference_code = self.cleaned_data["reference_code"]

        return reference_code.strip().upper()


class AppointmentCancelForm(forms.Form):
    # Internal form used by staff to cancel appointments with a required reason.

    cancellation_reason = forms.CharField(
        label="Motivo do cancelamento",
        required=True,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Informe o motivo do cancelamento.",
            }
        ),
    )

    def clean_cancellation_reason(self):
        # Normalize and validate cancellation reason.
        cancellation_reason = self.cleaned_data["cancellation_reason"].strip()

        if len(cancellation_reason) < 5:
            raise forms.ValidationError(
                "Informe um motivo com pelo menos 5 caracteres."
            )

        return cancellation_reason
