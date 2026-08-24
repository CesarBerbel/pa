"""O travão das portas públicas.

Os números vivem em `appointments/ratelimit.py` e nas próprias views, com a
justificação de cada um. Aqui fixa-se o que interessa a quem lá mexer depois:
que o travão dispara, que conta cada endereço por si — e, sobretudo, que o uso
normal de uma cliente passa sem tropeçar nele.
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from appointments.views.public import (
    PublicAppointmentByCodeView,
    PublicCancelAppointmentByCodeView,
)

CODIGO_INEXISTENTE = "AGD-XXXXXX"


@override_settings(RATELIMIT_ENABLE=True)
class TravaoDosPontosPublicosTests(TestCase):
    def setUp(self):
        # A cache é de memória e vive enquanto o processo viver: sem limpar,
        # um teste herdava a contagem do anterior.
        cache.clear()

        self.consulta = reverse("appointments:public_appointment_lookup")
        self.por_codigo = reverse(
            "appointments:public_appointment_by_code",
            kwargs={"reference_code": CODIGO_INEXISTENTE},
        )

    def test_consulta_por_email_trava_ao_fim_do_limite(self):
        # Doze por hora é o limite escrito na view. À décima terceira, para.
        for _ in range(12):
            resposta = self.client.post(self.consulta, data={"email": "a@b.pt"})
            self.assertEqual(resposta.status_code, 302)

        resposta = self.client.post(self.consulta, data={"email": "a@b.pt"})

        self.assertEqual(resposta.status_code, 429)

    def test_uso_normal_da_consulta_nao_e_travado(self):
        # O que uma cliente faz mesmo: engana-se no código uma ou duas vezes e
        # acerta à terceira. Isto nunca pode dar 429.
        for _ in range(3):
            resposta = self.client.post(
                self.consulta,
                data={"reference_code": CODIGO_INEXISTENTE},
            )

            self.assertEqual(resposta.status_code, 200)

    def test_consulta_por_codigo_trava_tambem_os_gets(self):
        # É a leitura, e não o cancelamento, que serve para adivinhar códigos.
        # O limite verdadeiro são 40/h; aqui baixa-se só para o teste não ter
        # de fazer quarenta pedidos para provar o mesmo.
        with patch.object(PublicAppointmentByCodeView, "ratelimit_rate", "3/h"):
            for _ in range(3):
                self.assertEqual(self.client.get(self.por_codigo).status_code, 200)

            self.assertEqual(self.client.get(self.por_codigo).status_code, 429)

    def test_consultar_e_cancelar_partilham_o_contador(self):
        # É o mesmo código que abre as duas páginas. Contadores separados
        # davam o dobro das tentativas a quem alternasse entre elas.
        cancelar = reverse(
            "appointments:public_cancel_by_code",
            kwargs={"reference_code": CODIGO_INEXISTENTE},
        )

        with patch.object(PublicAppointmentByCodeView, "ratelimit_rate", "2/h"):
            with patch.object(
                PublicCancelAppointmentByCodeView, "ratelimit_rate", "2/h"
            ):
                self.client.get(self.por_codigo)
                self.client.get(cancelar)

                resposta = self.client.get(self.por_codigo)

        self.assertEqual(resposta.status_code, 429)

    def test_cada_endereco_conta_por_si(self):
        # Atrás do Caddy todos os pedidos chegam de 127.0.0.1; é o
        # X-Forwarded-For que distingue as clientes. Sem isto, a primeira
        # pessoa a esgotar o limite bloqueava todas as outras.
        with override_settings(TRUSTED_PROXY_COUNT=1):
            with patch.object(PublicAppointmentByCodeView, "ratelimit_rate", "2/h"):
                for _ in range(2):
                    self.client.get(self.por_codigo, HTTP_X_FORWARDED_FOR="203.0.113.1")

                travada = self.client.get(
                    self.por_codigo, HTTP_X_FORWARDED_FOR="203.0.113.1"
                )
                outra = self.client.get(
                    self.por_codigo, HTTP_X_FORWARDED_FOR="203.0.113.2"
                )

        self.assertEqual(travada.status_code, 429)
        self.assertEqual(outra.status_code, 200)

    def test_desligado_por_omissao_nos_testes(self):
        # A restante suite corre com o travão desligado de propósito: quase mil
        # testes a marcar e a consultar do mesmo endereço esgotariam qualquer
        # limite razoável. Se alguém ligar isto por omissão, é aqui que se vê.
        with override_settings(RATELIMIT_ENABLE=False):
            with patch.object(PublicAppointmentByCodeView, "ratelimit_rate", "1/h"):
                for _ in range(5):
                    resposta = self.client.get(self.por_codigo)

        self.assertEqual(resposta.status_code, 200)
