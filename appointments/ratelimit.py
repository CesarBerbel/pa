"""Travão de tentativas nos pontos de entrada públicos.

Três das portas públicas do site fazem trabalho que compensa abusar:

* `/consultar/<código>/` e `/cancelar/<código>/` abrem uma marcação sem sessão
  iniciada — o código é a credencial. São `AGD-` mais seis caracteres de
  `A-Z0-9`, ou seja 36^6 combinações; adivinhar uma à sorte é impossível, mas
  não é impossível tentar milhões de vezes.
* `/marcar/` grava uma marcação e ocupa um horário na agenda. Sem travão,
  encher a semana de marcações falsas custa um script de dez linhas.
* `/consultar/` envia um email a partir do domínio da clínica. Repetido em
  série, é o domínio a servir de trampolim para spam — e a reputação de envio a
  pagar por isso.

Os limites são por endereço e deliberadamente largos. Isto é uma clínica com
uma profissional: o pior erro que este ficheiro pode cometer é impedir uma
cliente de cancelar. Cada número está justificado onde é definido.

**O travão conta por processo.** A cache por omissão é a de memória local e o
gunicorn corre com três workers, cada um com a sua: na prática o limite real é
o triplo do escrito. Continua a travar um script, que é o que se quer, e o
número exato só passa a ser exato no dia em que houver um Redis partilhado.
"""

from django.shortcuts import render
from django_ratelimit.core import is_ratelimited

from config.client_ip import endereco_do_cliente


def chave_por_endereco(group, request):
    # O `key="ip"` do django-ratelimit lê o REMOTE_ADDR, que atrás do Caddy é
    # sempre 127.0.0.1 — o limite passaria a ser global em vez de por cliente.
    return endereco_do_cliente(request)


class RateLimitedMixin:
    """Trava a view quando o mesmo endereço insiste demais.

    Devolve 429 e uma página que explica o que aconteceu, em vez do 403 seco
    que o `django_ratelimit` levanta por omissão: quem bate no limite é, quase
    sempre, uma pessoa a carregar no botão vezes de mais, e não um atacante.
    """

    ratelimit_rate = None
    ratelimit_methods = ("POST",)
    ratelimit_group = None
    ratelimit_template = "429.html"

    def dispatch(self, request, *args, **kwargs):
        if self.ratelimit_rate and is_ratelimited(
            request=request,
            group=self.ratelimit_group or self.__class__.__name__,
            fn=None,
            key=chave_por_endereco,
            rate=self.ratelimit_rate,
            method=self.ratelimit_methods,
            increment=True,
        ):
            return render(request, self.ratelimit_template, status=429)

        return super().dispatch(request, *args, **kwargs)
