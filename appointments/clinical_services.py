from __future__ import annotations

from appointments.models import PatientRecordLog

# Comprimento a partir do qual o valor anterior é cortado no histórico. Guardar
# o texto integral duplicaria dados de saúde sem acrescentar utilidade prática.
LIMITE_VALOR = 120


def resumir_valor(valor):
    if valor is True:
        return "sim"

    if valor is False:
        return "não"

    texto = str(valor or "").strip()

    if not texto:
        return "vazio"

    if len(texto) > LIMITE_VALOR:
        return f"{texto[:LIMITE_VALOR]}…"

    return texto


def describe_changes(form):
    """Devolve uma descrição legível do que mudou num formulário guardado.

    Regista o valor anterior porque é isso que permite perceber, mais tarde,
    que uma alergia foi apagada — saber apenas que "o campo mudou" não chega
    para reconstituir um registo clínico.
    """

    linhas = []

    for nome in form.changed_data:
        campo = form.fields.get(nome)

        if campo is None:
            continue

        rotulo = campo.label or nome
        anterior = form.initial.get(nome)
        atual = form.cleaned_data.get(nome)

        linhas.append(
            f"{rotulo}: «{resumir_valor(anterior)}» → «{resumir_valor(atual)}»"
        )

    return "\n".join(linhas)


def log_patient_record_change(record, user, form):
    # Não regista nada quando o formulário foi submetido sem alterações.
    descricao = describe_changes(form)

    if not descricao:
        return None

    return PatientRecordLog.objects.create(
        record=record,
        performed_by=user if user and user.is_authenticated else None,
        description=descricao,
    )
