"""Registo de quem mexeu em cada marcação, quando, de onde e o que mudou.

O registo existe para responder a perguntas feitas depois do facto: quem
desmarcou esta cliente, foi ela pelo site ou alguém aqui, a que horas estava
antes de ser mudada. Por isso guarda sempre as quatro coisas juntas — autor,
momento, origem e alteração — e não texto livre a descrever a ação.
"""

from appointments.models import FIELD_LABELS, Appointment, AppointmentLog

# Os campos que vale a pena seguir. Deixar de fora o `updated_at` e afins é
# deliberado: enchiam o registo de ruído sem dizer nada a quem o consulta.
TRACKED_FIELDS = tuple(FIELD_LABELS.keys())


def display_value(appointment, field):
    """O valor de um campo como uma pessoa o lê, não como está na base."""

    valor = getattr(appointment, field, None)

    if valor is None or valor == "":
        return ""

    if field == "status":
        return appointment.get_status_display()

    if field == "date":
        return valor.strftime("%d/%m/%Y")

    if field == "start_time":
        return valor.strftime("%H:%M")

    if field == "outside_schedule":
        return "Sim" if valor else "Não"

    return str(valor)


def snapshot(appointment):
    """O estado atual da marcação, pronto a comparar."""

    if appointment is None:
        return {}

    return {campo: display_value(appointment, campo) for campo in TRACKED_FIELDS}


def diff(before, after):
    """O que mudou entre dois retratos, no formato que o registo guarda.

    Só regista os campos que mudaram mesmo. Uma gravação que não altere nada
    não deve deixar uma linha a dizer que alterou.
    """

    before = before or {}
    after = after or {}

    alteracoes = {}

    for campo in TRACKED_FIELDS:
        anterior = before.get(campo, "")
        atual = after.get(campo, "")

        if anterior != atual:
            alteracoes[campo] = {"de": anterior, "para": atual}

    return alteracoes


class AppointmentAuditService:
    # Centralizes appointment audit log creation.

    @staticmethod
    def log(
        appointment,
        action,
        user=None,
        description="",
        source=None,
        changes=None,
    ):
        # Create an audit log entry for appointment changes.
        #
        # Sem `source` explícito, a ação herda a origem da própria marcação: um
        # cancelamento feito pelo site sobre uma marcação do site é do site.
        # Quem sabe melhor — as views públicas e internas — passa o valor.
        if source is None:
            source = AppointmentAuditService.source_for(appointment)

        return AppointmentLog.objects.create(
            appointment=appointment,
            action=action,
            performed_by=user if user and user.is_authenticated else None,
            description=description,
            source=source,
            changes=changes or {},
        )

    @staticmethod
    def source_for(appointment):
        origem = getattr(appointment, "origin", None)

        if origem == Appointment.ORIGIN_PUBLIC:
            return AppointmentLog.SOURCE_PUBLIC

        if origem == Appointment.ORIGIN_INTERNAL:
            return AppointmentLog.SOURCE_INTERNAL

        return AppointmentLog.SOURCE_UNKNOWN

    @staticmethod
    def snapshot(appointment):
        return snapshot(appointment)

    @staticmethod
    def creation_changes(appointment):
        """O estado inicial, no mesmo formato de/para do resto do registo.

        Numa criação não há valor anterior, mas guardar com que dados a
        marcação nasceu é o que permite ler a história toda a partir da
        primeira linha, em vez de só as alterações que vieram depois.
        """

        return {
            campo: {"de": "", "para": valor}
            for campo, valor in snapshot(appointment).items()
            if valor != ""
        }

    @staticmethod
    def diff(before, after):
        return diff(before, after)
