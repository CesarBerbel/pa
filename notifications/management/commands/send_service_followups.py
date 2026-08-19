from django.core.management.base import BaseCommand

from notifications.followup_services import (
    DEFAULT_MAX_DELAY_DAYS,
    eligible_appointments,
    send_followup,
)
from notifications.models import ServiceFollowUp


class Command(BaseCommand):
    """Envia os emails de seguimento cujo prazo chegou.

    Feito para correr uma vez por dia. Correr duas vezes não duplica nada: o
    registo de envios é consultado antes de cada email.
    """

    help = "Envia os emails de seguimento pós-atendimento configurados por serviço"

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-age-days",
            type=int,
            default=DEFAULT_MAX_DELAY_DAYS,
            help=(
                "Não envia seguimentos cujo prazo passou há mais dias do que "
                "isto. Evita despejar emails atrasados depois de o comando "
                "estar parado."
            ),
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra o que seria enviado, sem enviar.",
        )

    def handle(self, *args, **options):
        # As do fim do atendimento e as manuais não passam por aqui: saem
        # quando a marcação é concluída, ou quando alguém as manda à mão.
        seguimentos = ServiceFollowUp.objects.filter(
            is_active=True,
            trigger=ServiceFollowUp.TRIGGER_DELAYED,
        ).select_related("service", "email_template")

        if not seguimentos:
            self.stdout.write(self.style.WARNING("Nenhum seguimento ativo."))
            return

        enviados = 0
        falhados = 0

        for seguimento in seguimentos:
            marcacoes = eligible_appointments(
                seguimento,
                max_delay_days=options["max_age_days"],
            )

            for marcacao in marcacoes:
                if options["dry_run"]:
                    self.stdout.write(
                        f"[simulação] {seguimento} -> {marcacao.reference_code} "
                        f"({marcacao.customer.email})"
                    )
                    enviados += 1
                    continue

                resultado = send_followup(marcacao, seguimento)

                if resultado.success:
                    enviados += 1
                else:
                    falhados += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"{marcacao.reference_code}: {resultado.message}"
                        )
                    )

        self.stdout.write(self.style.SUCCESS(f"{enviados} seguimento(s) enviado(s)."))

        if falhados:
            self.stdout.write(self.style.WARNING(f"{falhados} falha(s)."))
