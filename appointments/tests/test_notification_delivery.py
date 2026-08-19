import threading

from django.conf import settings
from django.db import transaction
from django.test import TestCase, override_settings

from appointments.emails import deliver_after_commit


class DeliveryAfterCommitTests(TestCase):
    """Quando e onde os emails e as mensagens de WhatsApp são enviados.

    São duas garantias que se somam: nada sai antes de a marcação estar
    gravada, e nada do que sai faz o pedido esperar.
    """

    def test_nothing_is_sent_before_the_transaction_commits(self):
        enviados = []

        with self.captureOnCommitCallbacks(execute=False):
            deliver_after_commit(enviados.append, "confirmação")

            self.assertEqual(enviados, [])

    def test_delivery_runs_once_the_transaction_commits(self):
        enviados = []

        with self.captureOnCommitCallbacks(execute=True):
            deliver_after_commit(enviados.append, "confirmação")

        self.assertEqual(enviados, ["confirmação"])

    def test_a_failing_send_is_logged_and_never_raised(self):
        # Um servidor de SMTP inacessível não pode desfazer uma marcação que
        # já está gravada.
        def rebentar():
            raise RuntimeError("SMTP em baixo")

        with self.assertLogs("appointments.emails", level="ERROR") as registo:
            with self.captureOnCommitCallbacks(execute=True):
                deliver_after_commit(rebentar)

        self.assertIn("SMTP em baixo", "\n".join(registo.output))

    @override_settings(NOTIFICATIONS_IN_BACKGROUND=True)
    def test_the_request_does_not_wait_for_a_slow_send(self):
        # O que este teste mede é a espera: com EMAIL_TIMEOUT a 30 segundos, um
        # envio preso segurava o pedido — e, com três workers, o site inteiro.
        comecou = threading.Event()
        libertar = threading.Event()
        terminou = threading.Event()

        def envio_lento():
            comecou.set()
            libertar.wait(timeout=10)
            terminou.set()

        with self.captureOnCommitCallbacks(execute=True):
            deliver_after_commit(envio_lento)

        # O envio já arrancou, mas continua preso — e mesmo assim voltámos aqui.
        self.assertTrue(comecou.wait(timeout=10), "o envio nunca arrancou")
        self.assertFalse(terminou.is_set(), "o pedido esperou pelo envio")

        libertar.set()

        self.assertTrue(terminou.wait(timeout=10), "o envio não chegou ao fim")

    def test_tests_deliver_immediately(self):
        # Quase 400 testes verificam o que foi enviado na linha a seguir à
        # chamada. Numa thread, isso passaria a corrida — por isso o modo em
        # segundo plano vem desligado debaixo do runner.
        self.assertFalse(settings.NOTIFICATIONS_IN_BACKGROUND)

    def test_delivery_is_skipped_when_the_transaction_rolls_back(self):
        enviados = []

        try:
            with transaction.atomic():
                deliver_after_commit(enviados.append, "confirmação")
                raise RuntimeError("marcação recusada")
        except RuntimeError:
            pass

        self.assertEqual(enviados, [])
