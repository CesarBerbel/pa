from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Max
from django.utils import timezone

from appointments.models import Appointment, ClinicalNote, PatientRecord


class Command(BaseCommand):
    """Lista registos clínicos que ultrapassaram o prazo de conservação.

    Não elimina nada, por decisão deliberada: a orientação recebida é que a
    eliminação não deve ser automática sem uma política de retenção definida, e
    cada caso pode ter fundamento clínico ou legal para continuar guardado.

    O prazo vem de CLINICAL_RECORD_RETENTION_YEARS. Com o valor a zero, o
    comando limita-se a avisar que o prazo ainda não foi definido.
    """

    help = "Reportar fichas clínicas que ultrapassaram o prazo de conservação"

    def add_arguments(self, parser):
        parser.add_argument(
            "--anos",
            type=int,
            default=None,
            help="Simular outro prazo, sem alterar a configuração.",
        )

    def handle(self, *args, **options):
        anos = options["anos"]

        if anos is None:
            anos = getattr(settings, "CLINICAL_RECORD_RETENTION_YEARS", 0)

        if anos <= 0:
            self.stdout.write(
                self.style.WARNING(
                    "Prazo de conservação por definir "
                    "(CLINICAL_RECORD_RETENTION_YEARS=0).\n"
                    "Defina-o antes de usar este relatório, ou simule com --anos."
                )
            )
            return

        # timedelta não tem anos; 365 dias é suficiente para um relatório de
        # revisão manual e evita depender de bibliotecas externas.
        limite = timezone.now().date() - timedelta(days=365 * anos)

        self.stdout.write(f"Prazo: {anos} ano(s). Sem atividade desde {limite}.\n")

        vencidos = []

        for record in PatientRecord.objects.select_related("customer"):
            ultima_consulta = (
                Appointment.objects.filter(customer=record.customer)
                .aggregate(ultima=Max("date"))
                .get("ultima")
            )

            ultima_atividade = ultima_consulta or record.updated_at.date()

            if ultima_atividade <= limite:
                vencidos.append((record, ultima_atividade))

        if not vencidos:
            self.stdout.write(self.style.SUCCESS("Nenhuma ficha ultrapassou o prazo."))
            return

        for record, ultima_atividade in sorted(vencidos, key=lambda item: item[1]):
            notas = ClinicalNote.objects.filter(
                appointment__customer=record.customer,
            ).count()

            self.stdout.write(
                self.style.WARNING(
                    f"  {record.customer.full_name} "
                    f"(última atividade: {ultima_atividade}, {notas} nota(s))"
                )
            )

        self.stdout.write("")
        self.stdout.write(
            f"{len(vencidos)} ficha(s) para revisão. "
            "Nada foi eliminado: decida caso a caso."
        )
