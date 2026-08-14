"""Registo e autenticação por biometria (WebAuthn / passkeys).

O servidor guarda apenas chaves públicas. A digital fica no dispositivo; o que
chega aqui é uma assinatura de um desafio aleatório, que a chave pública
permite verificar.

O desafio vive na sessão entre os dois passos de cada cerimónia. Sem isso, uma
resposta capturada podia ser reenviada mais tarde.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from accounts.models import WebAuthnCredential

SESSION_REGISTRATION_CHALLENGE = "webauthn_registration_challenge"
SESSION_AUTHENTICATION_CHALLENGE = "webauthn_authentication_challenge"


@dataclass
class PasskeyResult:
    success: bool
    message: str
    credential: WebAuthnCredential | None = None
    user: object | None = None


def get_expected_origin():
    # A origem esperada vem do domínio canónico, e não do pedido: aceitar o que
    # o pedido diz destruiria a proteção contra phishing que o WebAuthn dá.
    return settings.SITE_URL.rstrip("/")


def get_rp_id():
    # O "relying party id" é o domínio a que a credencial fica amarrada. Uma
    # passkey criada em priarantes.com não funciona noutro domínio — é por isso
    # que este valor tem de vir de um sítio só.
    return urlparse(get_expected_origin()).hostname or "localhost"


def host_matches_canonical_domain(request):
    # Registar a partir de outro domínio criaria uma credencial que depois não
    # funcionaria no domínio principal. Vale mais recusar com uma mensagem
    # clara do que deixar o browser falhar com um erro incompreensível.
    return request.get_host().split(":")[0] == get_rp_id()


def build_registration_options(request, user):
    options = generate_registration_options(
        rp_id=get_rp_id(),
        rp_name=settings.SEO_SITE_NAME,
        user_id=str(user.pk).encode("utf-8"),
        user_name=user.email,
        user_display_name=user.full_name or user.email,
        # Credencial detetável: permite entrar sem escrever o email primeiro.
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        # Impede registar duas vezes o mesmo aparelho.
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(credential_id))
            for credential_id in user.webauthn_credentials.values_list(
                "credential_id", flat=True
            )
        ],
    )

    request.session[SESSION_REGISTRATION_CHALLENGE] = bytes_to_base64url(
        options.challenge
    )

    return options_to_json(options)


def complete_registration(request, user, credential, device_name):
    desafio = request.session.pop(SESSION_REGISTRATION_CHALLENGE, None)

    if not desafio:
        return PasskeyResult(False, "Pedido expirado. Tente novamente.")

    try:
        verificacao = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(desafio),
            expected_rp_id=get_rp_id(),
            expected_origin=get_expected_origin(),
            require_user_verification=True,
        )
    except Exception:
        return PasskeyResult(False, "Não foi possível validar este dispositivo.")

    credential_id = bytes_to_base64url(verificacao.credential_id)

    if WebAuthnCredential.objects.filter(credential_id=credential_id).exists():
        return PasskeyResult(False, "Este dispositivo já está registado.")

    registo = WebAuthnCredential.objects.create(
        user=user,
        credential_id=credential_id,
        public_key=bytes_to_base64url(verificacao.credential_public_key),
        sign_count=verificacao.sign_count,
        name=(device_name or "").strip() or "Dispositivo",
    )

    return PasskeyResult(True, "Dispositivo registado com sucesso.", credential=registo)


def build_authentication_options(request):
    options = generate_authentication_options(
        rp_id=get_rp_id(),
        user_verification=UserVerificationRequirement.REQUIRED,
    )

    request.session[SESSION_AUTHENTICATION_CHALLENGE] = bytes_to_base64url(
        options.challenge
    )

    return options_to_json(options)


def complete_authentication(request, credential):
    desafio = request.session.pop(SESSION_AUTHENTICATION_CHALLENGE, None)

    if not desafio:
        return PasskeyResult(False, "Pedido expirado. Tente novamente.")

    credential_id = credential.get("id") if isinstance(credential, dict) else None

    if not credential_id:
        return PasskeyResult(False, "Resposta do dispositivo inválida.")

    registo = (
        WebAuthnCredential.objects.filter(credential_id=credential_id)
        .select_related("user")
        .first()
    )

    if not registo:
        return PasskeyResult(False, "Dispositivo não reconhecido.")

    if not registo.user.is_active:
        return PasskeyResult(False, "Esta conta está inativa.")

    try:
        verificacao = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(desafio),
            expected_rp_id=get_rp_id(),
            expected_origin=get_expected_origin(),
            credential_public_key=base64url_to_bytes(registo.public_key),
            credential_current_sign_count=registo.sign_count,
            require_user_verification=True,
        )
    except Exception:
        return PasskeyResult(False, "Não foi possível validar este dispositivo.")

    registo.sign_count = verificacao.new_sign_count
    registo.last_used_at = timezone.now()
    registo.save(update_fields=["sign_count", "last_used_at"])

    return PasskeyResult(True, "Autenticado.", credential=registo, user=registo.user)
