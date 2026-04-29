from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from appointments.customer_services import (
    find_customer_by_email_or_phone,
    find_or_create_customer,
    validate_phone_for_brazil_or_portugal,
)


User = get_user_model()


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="Email")

    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(),
    )


class CustomerSignupForm(UserCreationForm):
    full_name = forms.CharField(label="Nome completo", max_length=255)
    phone = forms.CharField(label="Telefone", max_length=30)
    email = forms.EmailField(label="Email", required=True)

    class Meta:
        model = User
        fields = ["full_name", "phone", "email", "password1", "password2"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe uma conta com este email.")

        return email

    def clean_phone(self):
        phone = self.cleaned_data["phone"]
        return validate_phone_for_brazil_or_portugal(phone)

    def clean(self):
        cleaned_data = super().clean()

        email = cleaned_data.get("email")
        phone = cleaned_data.get("phone")

        if not email or not phone:
            return cleaned_data

        existing_customer = find_customer_by_email_or_phone(
            email=email,
            phone=phone,
        )

        if (
            existing_customer
            and existing_customer.user
            and existing_customer.user.email.lower() != email.lower()
        ):
            raise forms.ValidationError(
                "Este telefone já está associado a outra conta. Use outro telefone ou faça login na conta existente."
            )

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)

        email = self.cleaned_data["email"].strip().lower()
        full_name = self.cleaned_data["full_name"]
        phone = self.cleaned_data["phone"]

        user.email = email
        user.full_name = full_name
        user.phone = phone

        if commit:
            user.save()

            self.customer = find_or_create_customer(
                name=full_name,
                phone=phone,
                email=email,
                user=user,
            )

        return user