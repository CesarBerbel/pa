from django.urls import path

from .views import (
    CustomerSignupView,
    DashboardView,
    PasskeyAuthOptionsView,
    PasskeyAuthVerifyView,
    PasskeyDeleteView,
    PasskeyDeviceListView,
    PasskeyRegisterOptionsView,
    PasskeyRegisterVerifyView,
    UserLoginView,
    UserLogoutView,
)

app_name = "accounts"

urlpatterns = [
    path("login/", UserLoginView.as_view(), name="login"),
    path("logout/", UserLogoutView.as_view(), name="logout"),
    path("cadastro/", CustomerSignupView.as_view(), name="customer_signup"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    # Entrada com biometria. As duas cerimónias têm dois passos cada: o
    # servidor emite um desafio e depois verifica a resposta assinada.
    path(
        "dispositivos/",
        PasskeyDeviceListView.as_view(),
        name="passkey_devices",
    ),
    path(
        "dispositivos/<int:pk>/remover/",
        PasskeyDeleteView.as_view(),
        name="passkey_delete",
    ),
    path(
        "passkey/registo/opcoes/",
        PasskeyRegisterOptionsView.as_view(),
        name="passkey_register_options",
    ),
    path(
        "passkey/registo/verificar/",
        PasskeyRegisterVerifyView.as_view(),
        name="passkey_register_verify",
    ),
    path(
        "passkey/entrar/opcoes/",
        PasskeyAuthOptionsView.as_view(),
        name="passkey_auth_options",
    ),
    path(
        "passkey/entrar/verificar/",
        PasskeyAuthVerifyView.as_view(),
        name="passkey_auth_verify",
    ),
]
