"""O horário de funcionamento, num sítio só.

Estava escrito em três lados que não falavam entre si: o rodapé do site tinha
o texto fixo "Todos os dias: 08:00 — 20:00", os dados estruturados para o
Google liam duas variáveis de ambiente, e a agenda funcionava pelos registos
de `BusinessHour` que a profissional configura. Mudar o horário obrigava a
mudar nos três, e quem se esquecesse de um passava a anunciar uma hora a que
não atende — ou a recusar marcações a uma hora que anuncia.

A partir daqui manda quem já mandava na agenda: os `BusinessHour`. O rodapé e
o Google passam a ler daí.
"""

from django.utils.dates import WEEKDAYS
from django.utils.translation import gettext as _

from appointments.models import BusinessHour

# Os nomes que o Google espera, por índice de dia da semana. O `weekday` do
# modelo segue o Python: 0 é segunda-feira.
SCHEMA_DAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def _horas(hora):
    return hora.strftime("%H:%M")


def _grupos():
    """Dias abertos, juntando os seguidos que têm exatamente o mesmo horário.

    "Segunda a sexta" em vez de cinco linhas iguais — que é como se lê um
    horário, e como um humano o escreveria.
    """

    dias = BusinessHour.objects.filter(is_active=True).order_by("weekday")
    grupos = []

    for dia in dias:
        periodos = dia.periods

        if not periodos:
            continue

        anterior = grupos[-1] if grupos else None
        seguido = anterior and anterior["last"] + 1 == dia.weekday

        if seguido and anterior["periods"] == periodos:
            anterior["last"] = dia.weekday
        else:
            grupos.append(
                {"first": dia.weekday, "last": dia.weekday, "periods": periodos}
            )

    return grupos


def opening_hours():
    """O horário como se lê: uma linha por grupo de dias."""

    linhas = []

    for grupo in _grupos():
        primeiro = str(WEEKDAYS[grupo["first"]])
        ultimo = str(WEEKDAYS[grupo["last"]])

        # "Segunda-feira a Sexta-feira" repete o "-feira" sem necessidade.
        # Em português diz-se "Segunda a sexta-feira"; em inglês, onde os
        # nomes não têm sufixo, isto não faz nada.
        if primeiro.endswith("-feira") and ultimo.endswith("-feira"):
            primeiro = primeiro[: -len("-feira")]
            ultimo = ultimo.lower()

        if grupo["first"] == grupo["last"]:
            dias = f"{primeiro}"
        elif grupo["last"] - grupo["first"] == 1:
            dias = _("%(primeiro)s e %(ultimo)s") % {
                "primeiro": primeiro,
                "ultimo": ultimo,
            }
        else:
            dias = _("%(primeiro)s a %(ultimo)s") % {
                "primeiro": primeiro,
                "ultimo": ultimo,
            }

        linhas.append(
            {
                "days": dias,
                "periods": [
                    f"{_horas(inicio)} — {_horas(fim)}"
                    for inicio, fim in grupo["periods"]
                ],
            }
        )

    return linhas


def structured_data_specification():
    """O mesmo horário na forma que o Google lê, ou `None` se não houver.

    Sem nenhum `BusinessHour` configurado devolve `None`, e quem chama volta
    ao horário das definições — melhor um horário genérico do que uma ficha
    sem horário nenhum.
    """

    especificacao = []

    for grupo in _grupos():
        dias = [
            SCHEMA_DAYS[indice]
            for indice in range(grupo["first"], grupo["last"] + 1)
        ]

        for inicio, fim in grupo["periods"]:
            especificacao.append(
                {
                    "@type": "OpeningHoursSpecification",
                    "dayOfWeek": dias,
                    "opens": _horas(inicio),
                    "closes": _horas(fim),
                }
            )

    return especificacao or None
