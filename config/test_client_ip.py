"""De onde vem o pedido, quando há um proxy pelo meio.

O `X-Forwarded-For` é uma lista a que qualquer um pode acrescentar do lado de
fora. Estes testes fixam a regra que torna a leitura segura: só valem os
elementos escritos pelos proxies de confiança, e esses estão no fim.
"""

from django.test import RequestFactory, TestCase, override_settings

from config.client_ip import endereco_do_cliente


class EnderecoDoClienteTests(TestCase):
    def setUp(self):
        self.pedidos = RequestFactory()

    def pedido(self, encaminhado=None, remoto="127.0.0.1"):
        extra = {"REMOTE_ADDR": remoto}

        if encaminhado is not None:
            extra["HTTP_X_FORWARDED_FOR"] = encaminhado

        return self.pedidos.get("/", **extra)

    @override_settings(TRUSTED_PROXY_COUNT=0)
    def test_sem_proxy_usa_a_ligacao(self):
        # Em desenvolvimento não há proxy nenhum à frente, e o cabeçalho — se
        # vier — vem de quem quiser inventá-lo.
        pedido = self.pedido(encaminhado="203.0.113.9", remoto="198.51.100.5")

        self.assertEqual(endereco_do_cliente(pedido), "198.51.100.5")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_com_um_proxy_usa_o_ultimo_elemento(self):
        # O Caddy acrescenta ao fim o endereço de quem lhe falou. Tudo o que
        # esteja antes pode ter vindo do próprio cliente.
        pedido = self.pedido(encaminhado="203.0.113.9")

        self.assertEqual(endereco_do_cliente(pedido), "203.0.113.9")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_o_cliente_nao_escolhe_o_seu_endereco(self):
        # Um cliente a enviar o cabeçalho já preenchido para escapar ao travão:
        # o Caddy acrescenta o endereço real a seguir, e é esse que conta.
        pedido = self.pedido(encaminhado="1.2.3.4, 203.0.113.9")

        self.assertEqual(endereco_do_cliente(pedido), "203.0.113.9")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_sem_cabecalho_fica_a_ligacao(self):
        # Alguém que chegue ao gunicorn sem passar pelo Caddy. Aí o endereço da
        # ligação é mesmo o do cliente.
        pedido = self.pedido(remoto="198.51.100.5")

        self.assertEqual(endereco_do_cliente(pedido), "198.51.100.5")

    @override_settings(TRUSTED_PROXY_COUNT=2)
    def test_menos_elementos_do_que_proxies_configurados(self):
        # Configuração errada ou um proxy que não escreveu o cabeçalho. Fica o
        # primeiro elemento — o mais próximo do cliente que ainda se justifica
        # — em vez de rebentar ou de devolver vazio.
        pedido = self.pedido(encaminhado="203.0.113.9")

        self.assertEqual(endereco_do_cliente(pedido), "203.0.113.9")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_espacos_e_elementos_vazios_nao_contam(self):
        pedido = self.pedido(encaminhado=" 1.2.3.4 , , 203.0.113.9 ")

        self.assertEqual(endereco_do_cliente(pedido), "203.0.113.9")
