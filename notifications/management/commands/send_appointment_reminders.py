"""Avisa quem tem marcação a chegar.

Feito para correr de meia em meia hora. A antecedência não é deste comando — é
uma definição da clínica, em *Mensagens > Envio de mensagens* — e por isso o
comando não sabe nem decide quantas horas antes se avisa: pergunta.

Correr de meia em meia hora não manda meia dúzia de lembretes: cada marcação
avisada fica registada, e um registo de sucesso tira-a da lista. Uma passagem
falhada é apanhada na seguinte, dentro da tolerância.
"""

from django.core.management.base import BaseCommand

from appointments import reminder_services
from appointments.emails import send_appointment_reminder_email
from notifications.models import EmailTemplate, WhatsAppEventSetting
from notifications.whatsapp_dispatch import notify as notify_whatsapp


class Command(BaseCommand):
    help = "Envia os lembretes das marcações que estão a chegar"

    def add_arguments(self, parser):
        parser.add_argument(
            "--horas",
            type=int,
            default=None,
            help=(
                "Antecedência, em horas. Por omissão usa a do modelo do "
                "lembrete — que é onde ela deve ser mudada, e não aqui."
            ),
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra quem seria avisada, sem avisar ninguém.",
        )

    def handle(self, *args, **options):
        horas = options["horas"]

        if horas is None:
            horas = EmailTemplate.reminder_hours()

        if horas <= 0:
            self.stdout.write(
                self.style.WARNING(
                    "Lembretes desligados: a antecedência do modelo está a zero."
                )
            )

            return

        marcacoes = reminder_services.due(horas)

        if not marcacoes:
            self.stdout.write(
                self.style.WARNING(f"Nada a lembrar com {horas}h de antecedência.")
            )

            return

        enviados = 0

        for marcacao in marcacoes:
            if options["dry_run"]:
                self.stdout.write(
                    f"[simulação] {marcacao.customer.full_name} — "
                    f"{marcacao.date:%d/%m/%Y} {marcacao.start_time:%H:%M}"
                )

                continue

            self.lembrar(marcacao, horas)

            enviados += 1

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"{len(marcacoes)} por lembrar."))

            return

        self.stdout.write(self.style.SUCCESS(f"{enviados} lembrete(s) enviado(s)."))

    def lembrar(self, marcacao, horas):
        """Manda o lembrete e regista que foi mandado.

        O registo é escrito mesmo quando o envio falha — como erro. Sem ele, o
        comando voltava a tentar de meia em meia hora e transformava uma falha
        de SMTP numa enxurrada de tentativas.
        """

        erro = ""

        try:
            send_appointment_reminder_email(marcacao)

            notify_whatsapp(
                marcacao,
                WhatsAppEventSetting.EVENT_APPOINTMENT_REMINDER,
            )
        except Exception as falha:  # noqa: BLE001 — registado, não escondido
            erro = str(falha)

            self.stderr.write(f"{marcacao.reference_code}: {erro}")

        reminder_services.record(marcacao, horas, error=erro)

        self.stdout.write(
            f"- {marcacao.customer.full_name} "
            f"({marcacao.date:%d/%m/%Y} {marcacao.start_time:%H:%M})"
        )
