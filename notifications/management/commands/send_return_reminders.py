"""Avisa quem está na altura de voltar.

Feito para correr uma vez por dia, como o `send_service_followups`. Correr
duas vezes no mesmo dia não duplica nada: cada retorno guarda a data em que foi
avisado, e um retorno já avisado não volta a entrar na lista.

O que este comando **não** faz é marcar seja o que for. Manda a mensagem com a
ligação para marcar, e o retorno continua por marcar até alguém escolher uma
hora — a cliente no site, ou a clínica ao telefone. Marcar por ela ocupava uma
vaga que ninguém combinou.
"""

from django.core.management.base import BaseCommand

from appointments import return_services
from appointments.emails import send_return_due_email
from notifications.models import WhatsAppEventSetting
from notifications.whatsapp_dispatch import notify as notify_whatsapp


class Command(BaseCommand):
    help = "Avisa as clientes cujo retorno está a chegar e continua por marcar"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dias",
            type=int,
            default=return_services.DIAS_DE_AVISO,
            help=(
                "Com quantos dias de antecedência avisar. Por omissão, uma "
                "semana: dá tempo de escolher um horário que preste, e não é "
                "tão cedo que a mensagem se perca."
            ),
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra quem seria avisada, sem avisar ninguém.",
        )

    def handle(self, *args, **options):
        retornos = return_services.due_for_notice(lead_days=options["dias"])

        if not retornos:
            self.stdout.write(self.style.WARNING("Nenhum retorno a avisar hoje."))

            return

        avisados = 0
        saltados = 0

        for retorno in retornos:
            # Acontece: a pessoa marcou sozinha depois de sair da clínica.
            # Mandar-lhe "está na altura de voltar" seria falar com quem já
            # voltou.
            if return_services.already_booked(retorno):
                saltados += 1

                self.stdout.write(
                    f"- {retorno.customer.full_name}: já tem marcação, não avisado."
                )

                continue

            if options["dry_run"]:
                self.stdout.write(
                    f"[simulação] {retorno.customer.full_name} "
                    f"({retorno.target_date:%d/%m/%Y})"
                )

                continue

            self.avisar(retorno)

            avisados += 1

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"{len(retornos)} por avisar."))

            return

        self.stdout.write(
            self.style.SUCCESS(
                f"{avisados} avisadas, {saltados} saltadas por já terem marcação."
            )
        )

    def avisar(self, retorno):
        """Manda a mensagem e marca o retorno como avisado.

        A marca é posta mesmo que o email falhe: o envio já regista o erro por
        si, e voltar a tentar todos os dias transformaria uma falha numa
        enxurrada de mensagens no dia em que voltasse a funcionar.
        """

        send_return_due_email(retorno)

        # O WhatsApp segue as regras de sempre: só sai se a regra estiver
        # ligada, e o texto livre só chega dentro das 24 horas seguintes a uma
        # mensagem da cliente. Pelo número da clínica não há essa limitação.
        #
        # Vai pela marcação de origem porque é dela que o envio sabe ir buscar
        # o número e o nome. Um retorno aberto à mão, sem origem, sai só por
        # email — e é por isso que a lista tem o botão para falar por WhatsApp.
        if retorno.origin:
            notify_whatsapp(
                retorno.origin,
                WhatsAppEventSetting.EVENT_RETURN_DUE,
            )

        return_services.mark_notified(retorno)

        self.stdout.write(
            f"- {retorno.customer.full_name} ({retorno.target_date:%d/%m/%Y})"
        )
