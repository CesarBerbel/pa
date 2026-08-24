"""O travão do login, feito pelo django-axes.

O formulário de entrada aceitava palavras-passe sem conta nenhuma: quem
quisesse podia experimentá-las às centenas de milhar. Estes testes fixam as
duas metades da decisão — que o bloqueio existe, e que é largo o suficiente
para não apanhar quem se engana algumas vezes.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

PALAVRA_PASSE = "PalavraPasseForte123"


@override_settings(AXES_ENABLED=True)
class LoginLockoutTests(TestCase):
    def setUp(self):
        cache.clear()

        User = get_user_model()

        self.utilizador = User.objects.create_superuser(
            email="profissional@example.com",
            password=PALAVRA_PASSE,
            full_name="Priscila Arantes",
        )

        self.url = reverse("accounts:login")

    def tentar(self, palavra_passe):
        return self.client.post(
            self.url,
            data={
                "username": self.utilizador.email,
                "password": palavra_passe,
            },
        )

    def test_bloqueia_depois_de_esgotar_as_tentativas(self):
        # O limite conta as falhas: a que o atinge já é recusada pelo axes.
        for _ in range(settings.AXES_FAILURE_LIMIT - 1):
            resposta = self.tentar("errada")
            self.assertEqual(resposta.status_code, 200)

        resposta = self.tentar("errada")

        self.assertEqual(resposta.status_code, 429)

    def test_bloqueio_nao_cede_a_palavra_passe_certa(self):
        # O ponto do bloqueio: depois dele, acertar deixa de bastar. Sem isto,
        # quem estivesse a adivinhar entrava assim que acertasse.
        for _ in range(settings.AXES_FAILURE_LIMIT):
            self.tentar("errada")

        resposta = self.tentar(PALAVRA_PASSE)

        self.assertEqual(resposta.status_code, 429)
        self.assertFalse(resposta.wsgi_request.user.is_authenticated)

    def test_entrada_correta_a_primeira_nao_e_travada(self):
        resposta = self.tentar(PALAVRA_PASSE)

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.utilizador.pk)

    def test_alguns_enganos_seguidos_de_um_acerto_deixam_entrar(self):
        # O caso que motivou o limite generoso: a palavra-passe guardada no
        # telemóvel está desatualizada e o browser tenta-a várias vezes antes
        # de a pessoa a escrever à mão.
        for _ in range(settings.AXES_FAILURE_LIMIT - 1):
            self.tentar("errada")

        resposta = self.tentar(PALAVRA_PASSE)

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.utilizador.pk)

    def test_o_limite_configurado_continua_generoso(self):
        # Três — o valor de fábrica do axes — apanhava um dia mau. Se alguém o
        # baixar, que seja com este teste à frente.
        self.assertGreaterEqual(settings.AXES_FAILURE_LIMIT, 5)
