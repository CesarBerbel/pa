"""De onde vem o pedido, quando há um proxy pelo meio.

Em produção quem fala com o browser é o Caddy, e o Django só vê a ligação que
vem de `127.0.0.1`. Sem tratar disto, qualquer travão por endereço — o
django-axes no login, o django-ratelimit nos pontos públicos — via o mundo
inteiro como um único cliente: a primeira pessoa a esgotar o limite bloqueava
todas as outras.

O `X-Forwarded-For` resolve, mas não se lê de qualquer maneira. O cabeçalho é
uma lista a que cada proxy acrescenta o endereço de quem lhe falou, e o
primeiro elemento pode ter vindo do próprio cliente — quem quisesse escapar ao
travão bastava-lhe enviar um `X-Forwarded-For` diferente a cada pedido. Só os
elementos escritos pelos proxies de confiança valem, e são os últimos da lista.
"""

from django.conf import settings

CABECALHO = "HTTP_X_FORWARDED_FOR"


def endereco_do_cliente(request) -> str:
    """O endereço a usar para contar tentativas. Nunca devolve vazio."""

    proxies = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    remoto = request.META.get("REMOTE_ADDR") or ""

    if proxies < 1:
        return remoto

    encaminhado = request.META.get(CABECALHO) or ""
    enderecos = [parte.strip() for parte in encaminhado.split(",") if parte.strip()]

    if not enderecos:
        # Cabeçalho ausente num pedido que devia trazê-lo: é o que acontece
        # quando alguém chega ao Django sem passar pelo Caddy. Fica o endereço
        # da ligação, que nesse caso é mesmo o do cliente.
        return remoto

    # O último proxy da cadeia escreveu o endereço de quem lhe falou. Com N
    # proxies de confiança, o cliente é o elemento N a contar do fim.
    indice = len(enderecos) - proxies

    if indice < 0:
        # Menos elementos do que proxies configurados: alguém à frente não
        # escreveu o cabeçalho, ou o número está mal. O primeiro elemento é o
        # mais próximo do cliente que ainda se consegue justificar.
        indice = 0

    return enderecos[indice] or remoto
