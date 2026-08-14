import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from webauthn.helpers import bytes_to_base64url

from accounts import passkey_services
from accounts.models import WebAuthnCredential

# Os valores reais são gravados já em base64url; usar texto simples nos
# testes rebentaria na descodificação e escondia o que se quer verificar.
CHAVE = bytes_to_base64url(b"chave-publica-de-teste")


@override_settings(SITE_URL="http://testserver")
class PasskeyRegistrationTests(TestCase):
    """Registo de um aparelho para entrar com biometria.

    A cerimónia real precisa de um autenticador com hardware, que não existe
    nos testes. O que é verificado aqui é o código deste lado: o desafio, o
    domínio, o que fica guardado e o que acontece quando a verificação falha.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.options_url = reverse("accounts:passkey_register_options")
        self.verify_url = reverse("accounts:passkey_register_verify")

    def test_options_require_login(self):
        response = self.client.post(self.options_url)

        self.assertEqual(response.status_code, 302)

    def test_options_are_issued_for_the_canonical_domain(self):
        self.client.force_login(self.user)

        response = self.client.post(self.options_url)
        options = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(options["rp"]["id"], "testserver")
        self.assertEqual(
            options["authenticatorSelection"]["userVerification"], "required"
        )

    def test_challenge_is_stored_in_the_session(self):
        self.client.force_login(self.user)
        self.client.post(self.options_url)

        self.assertIn(
            passkey_services.SESSION_REGISTRATION_CHALLENGE,
            self.client.session,
        )

    @override_settings(SITE_URL="https://priarantes.com")
    def test_registration_is_refused_from_another_domain(self):
        # Uma chave criada noutro endereço não funcionaria no principal, e o
        # erro do browser não explicaria porquê.
        self.client.force_login(self.user)

        response = self.client.post(self.options_url)

        self.assertEqual(response.status_code, 400)
        self.assertIn("priarantes.com", json.loads(response.content)["error"])

    def test_verification_without_a_challenge_is_refused(self):
        self.client.force_login(self.user)

        response = self.client.post(
            self.verify_url,
            data=json.dumps({"credential": {}, "name": "Telemóvel"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(WebAuthnCredential.objects.count(), 0)

    def test_successful_registration_stores_the_public_key(self):
        self.client.force_login(self.user)
        self.client.post(self.options_url)

        verificacao = SimpleNamespace(
            credential_id=b"credencial-1",
            credential_public_key=b"chave-publica",
            sign_count=0,
        )

        with patch(
            "accounts.passkey_services.verify_registration_response",
            return_value=verificacao,
        ):
            response = self.client.post(
                self.verify_url,
                data=json.dumps({"credential": {}, "name": "Telemóvel pessoal"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)

        credential = WebAuthnCredential.objects.get()

        self.assertEqual(credential.user, self.user)
        self.assertEqual(credential.name, "Telemóvel pessoal")
        self.assertTrue(credential.public_key)

    def test_device_without_a_name_gets_a_default(self):
        self.client.force_login(self.user)
        self.client.post(self.options_url)

        verificacao = SimpleNamespace(
            credential_id=b"credencial-2",
            credential_public_key=b"chave",
            sign_count=0,
        )

        with patch(
            "accounts.passkey_services.verify_registration_response",
            return_value=verificacao,
        ):
            self.client.post(
                self.verify_url,
                data=json.dumps({"credential": {}, "name": "   "}),
                content_type="application/json",
            )

        self.assertEqual(WebAuthnCredential.objects.get().name, "Dispositivo")

    def test_failed_verification_stores_nothing(self):
        self.client.force_login(self.user)
        self.client.post(self.options_url)

        with patch(
            "accounts.passkey_services.verify_registration_response",
            side_effect=ValueError("assinatura inválida"),
        ):
            response = self.client.post(
                self.verify_url,
                data=json.dumps({"credential": {}, "name": "X"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(WebAuthnCredential.objects.count(), 0)


@override_settings(SITE_URL="http://testserver")
class PasskeyAuthenticationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.credential = WebAuthnCredential.objects.create(
            user=self.user,
            credential_id="credencial-registada",
            public_key=CHAVE,
            sign_count=4,
            name="Telemóvel",
        )

        self.options_url = reverse("accounts:passkey_auth_options")
        self.verify_url = reverse("accounts:passkey_auth_verify")

    def payload(self, credential_id="credencial-registada"):
        return json.dumps({"credential": {"id": credential_id}})

    def test_options_do_not_require_login(self):
        response = self.client.post(self.options_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["rpId"], "testserver")

    def test_unknown_credential_is_refused(self):
        self.client.post(self.options_url)

        response = self.client.post(
            self.verify_url,
            data=self.payload("nao-existe"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_account_cannot_sign_in(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        self.client.post(self.options_url)

        response = self.client.post(
            self.verify_url,
            data=self.payload(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_successful_authentication_signs_the_user_in(self):
        self.client.post(self.options_url)

        with patch(
            "accounts.passkey_services.verify_authentication_response",
            return_value=SimpleNamespace(new_sign_count=9),
        ):
            response = self.client.post(
                self.verify_url,
                data=self.payload(),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content)["redirect_url"], reverse("dashboard")
        )
        self.assertEqual(
            int(self.client.session["_auth_user_id"]),
            self.user.pk,
        )

    def test_sign_count_is_updated(self):
        # O contador subir é o que permite detetar uma credencial clonada.
        self.client.post(self.options_url)

        with patch(
            "accounts.passkey_services.verify_authentication_response",
            return_value=SimpleNamespace(new_sign_count=9),
        ):
            self.client.post(
                self.verify_url,
                data=self.payload(),
                content_type="application/json",
            )

        self.credential.refresh_from_db()

        self.assertEqual(self.credential.sign_count, 9)
        self.assertIsNotNone(self.credential.last_used_at)

    def test_reusing_a_challenge_fails(self):
        # O desafio é retirado da sessão ao ser usado: uma resposta capturada
        # não pode ser reenviada.
        self.client.post(self.options_url)

        with patch(
            "accounts.passkey_services.verify_authentication_response",
            return_value=SimpleNamespace(new_sign_count=9),
        ):
            primeira = self.client.post(
                self.verify_url,
                data=self.payload(),
                content_type="application/json",
            )
            segunda = self.client.post(
                self.verify_url,
                data=self.payload(),
                content_type="application/json",
            )

        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(segunda.status_code, 400)


@override_settings(SITE_URL="http://testserver")
class PasskeyDeviceManagementTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.other = User.objects.create_user(
            email="outro@example.com",
            password="StrongPassword123",
            full_name="Outro",
        )

        self.credential = WebAuthnCredential.objects.create(
            user=self.other,
            credential_id="do-outro",
            public_key=CHAVE,
            name="Telemóvel do outro",
        )

    def test_page_lists_only_your_own_devices(self):
        WebAuthnCredential.objects.create(
            user=self.user,
            credential_id="meu",
            public_key=CHAVE,
            name="O meu telemóvel",
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:passkey_devices"))

        self.assertContains(response, "O meu telemóvel")
        self.assertNotContains(response, "Telemóvel do outro")

    def test_cannot_delete_someone_elses_device(self):
        self.client.force_login(self.user)

        self.client.post(
            reverse("accounts:passkey_delete", kwargs={"pk": self.credential.pk})
        )

        self.assertTrue(
            WebAuthnCredential.objects.filter(pk=self.credential.pk).exists()
        )

    def test_can_delete_your_own_device(self):
        minha = WebAuthnCredential.objects.create(
            user=self.user,
            credential_id="minha",
            public_key=CHAVE,
            name="A minha",
        )

        self.client.force_login(self.user)
        self.client.post(reverse("accounts:passkey_delete", kwargs={"pk": minha.pk}))

        self.assertFalse(WebAuthnCredential.objects.filter(pk=minha.pk).exists())

    def test_login_page_offers_biometrics(self):
        response = self.client.get(reverse("accounts:login"))

        self.assertContains(response, "data-passkey-login")
        self.assertContains(response, "Entrar com digital")

    def test_password_login_still_works(self):
        # A biometria é uma alternativa, nunca uma substituição: sem isto,
        # perder o telemóvel deixaria a conta inacessível.
        response = self.client.post(
            reverse("accounts:login"),
            data={"username": "admin@example.com", "password": "StrongPassword123"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)
