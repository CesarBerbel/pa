from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import get_user_model

from appointments.models import Customer


User = get_user_model()

class EmailAuthenticationForm(AuthenticationForm):
    # Login form using email instead of username

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "Digite seu email",
                "autocomplete": "email",
            }
        ),
    )

    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Digite sua senha",
                "autocomplete": "current-password",
            }
        ),
    )

class CustomerSignupForm(UserCreationForm):
    full_name = forms.CharField(
        label="Nome completo",
        max_length=255,
    )

    phone = forms.CharField(
        label="Telefone",
        max_length=30,
    )

    email = forms.EmailField(
        label="Email",
        required=True,
    )

    class Meta:
        model = User
        fields = [
            "full_name",
            "phone",
            "email",
            "password1",
            "password2",
        ]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe uma conta com este email.")

        return email

    def save(self, commit=True):
        user = super().save(commit=False)

        email = self.cleaned_data["email"].strip().lower()
        full_name = self.cleaned_data["full_name"]
        phone = self.cleaned_data["phone"]

        user.username = email
        user.email = email
        user.first_name = full_name

        if commit:
            user.save()

            customer = Customer.objects.filter(
                email__iexact=email,
            ).order_by("id").first()

            if customer:
                customer.user = user
                customer.full_name = full_name
                customer.phone = phone
                customer.email = email
                customer.save(update_fields=["user", "full_name", "phone", "email", "updated_at"])
            else:
                Customer.objects.create(
                    user=user,
                    full_name=full_name,
                    phone=phone,
                    email=email,
                )

        return user