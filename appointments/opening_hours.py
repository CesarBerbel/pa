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


def _periodos(dia):
    """Os períodos do dia, com os que se tocam já juntos.

    Uma manhã que acaba à hora a que a tarde começa não são dois períodos: é
    um dia corrido. Escrito como dois lê-se como um lapso — "08:00 — 12:00 e
    12:00 — 14:00" —, e é assim que o sábado está gravado.

    Junta-se aqui e não no modelo: a agenda tem razões próprias para manter os
    dois registos, e é dela que vêm os horários que se marcam. O que muda é o
    que se anuncia, no rodapé e ao Google, onde só interessa a hora a que se
    abre e a hora a que se fecha.
    """

    juntos = []

    for inicio, fim in dia.periods:
        if juntos and juntos[-1][1] == inicio:
            juntos[-1] = (juntos[-1][0], fim)
        else:
            juntos.append((inicio, fim))

    return juntos


def _grupos():
    """Dias abertos, juntando os seguidos que têm exatamente o mesmo horário.

    "Segunda a sexta" em vez de cinco linhas iguais — que é como se lê um
    horário, e como um humano o escreveria.
    """

    dias = BusinessHour.objects.filter(is_active=True).order_by("weekday")
    grupos = []

    for dia in dias:
        periodos = _periodos(dia)

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


def _nome_do_dia(indice):
    """O nome do dia como cabe numa lista de sete linhas.

    "Segunda-feira" sete vezes enche a coluna de sufixos iguais e empurra as
    horas para longe do dia a que pertencem. Em inglês, onde os nomes não têm
    sufixo, isto não faz nada.
    """

    nome = str(WEEKDAYS[indice])

    if nome.endswith("-feira"):
        nome = nome[: -len("-feira")]

    return nome


def opening_hours():
    """O horário como se lê: uma linha por dia, a semana inteira.

    Os dias fechados vêm na lista, marcados, e não de fora. Um horário a que
    falta o domingo obriga a contar os dias para saber se está fechado ou se
    ninguém o escreveu — e isto é o rodapé, onde ninguém conta nada. A semana
    toda responde à pergunta antes de ela ser feita, e é também o que dá à
    coluna altura para acompanhar o mapa ao lado.

    Sem um único dia aberto devolve uma lista vazia: aí não é um horário com
    dias fechados, é um horário que ainda não foi configurado, e o rodapé não
    deve mostrar sete linhas a dizer que está sempre encerrado.
    """

    periodos_do_dia = {
        dia.weekday: _periodos(dia)
        for dia in BusinessHour.objects.filter(is_active=True)
    }

    if not any(periodos_do_dia.values()):
        return []

    return [
        {
            "day": _nome_do_dia(indice),
            "closed": not periodos_do_dia.get(indice),
            "periods": [
                f"{_horas(inicio)} — {_horas(fim)}"
                for inicio, fim in periodos_do_dia.get(indice) or []
            ],
        }
        for indice in range(7)
    ]


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
