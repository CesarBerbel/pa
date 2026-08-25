"""As mensagens que saem uma vez por dia, num comando só.

Eram dois comandos e duas linhas no cron. Duas linhas são duas coisas para
lembrar, duas para configurar num servidor novo, e duas para descobrir que
faltavam quando alguém reparar que os emails deixaram de sair. Uma mensagem
diária que se acrescente amanhã entra aqui e não obriga a mexer no cron outra
vez.

Os lembretes das marcações **não** estão aqui: correm de meia em meia hora,
porque uma antecedência de duas horas não se cumpre com um comando que passa
uma vez por dia.

Falhar um não impede o outro de correr: são mensagens diferentes, para pessoas
diferentes, e uma falha do SMTP a meio não pode calar o resto do dia.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

# Pela ordem em que interessam a quem lê a saída: primeiro o que fecha um
# atendimento, depois o que abre o seguinte.
COMANDOS = [
    ("send_service_followups", "Seguimentos pós-atendimento"),
    ("send_return_reminders", "Avisos de retorno"),
]


class Command(BaseCommand):
    help = "Corre as mensagens diárias: seguimentos e avisos de retorno"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra o que seria enviado, sem enviar.",
        )

    def handle(self, *args, **options):
        falhas = []

        for comando, titulo in COMANDOS:
            self.stdout.write(self.style.MIGRATE_HEADING(f"{titulo}"))

            try:
                call_command(
                    comando,
                    dry_run=options["dry_run"],
                    stdout=self.stdout,
                    stderr=self.stderr,
                )
            except Exception as erro:  # noqa: BLE001 — registado, não escondido
                falhas.append(f"{comando}: {erro}")

                self.stderr.write(self.style.ERROR(f"{titulo} falhou: {erro}"))

            self.stdout.write("")

        if falhas:
            # Sai com erro para o cron poder avisar. A saída diz qual falhou.
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS("Mensagens diárias concluídas."))
