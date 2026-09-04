"""Alterações à mensagem que valem só para este envio.

Quem confirma uma marcação vê, na janela de confirmação, o texto que a cliente
vai receber — e às vezes quer mudar-lhe uma frase: acrescentar uma indicação de
estacionamento, avisar que a porta da galeria fecha ao almoço, dizer que traga
as meias de compressão. Sem isto, as opções eram enviar o texto genérico ou
abrir o modelo e reescrevê-lo, o que mudava a mensagem de todas as clientes
para arranjar uma frase para uma.

Por isso esta alteração **não é gravada em lado nenhum**. Nasce no formulário,
viaja no pedido, é usada no envio e morre com a resposta. Não há aqui `save()`
nenhum, e é essa ausência que garante que o modelo original fica como estava —
não uma regra escrita num comentário que alguém um dia esquece.

A língua segue a mesma lógica: escolher inglês nesta janela manda esta mensagem
em inglês, e não muda a língua registada na cliente. Quem quiser mudar isso
muda-o na ficha dela, que é onde a decisão dura.
"""

from __future__ import annotations

from dataclasses import dataclass

# As duas línguas em que o site fala. Uma escolha fora desta lista é ignorada
# em silêncio: o pior que pode acontecer é sair na língua de sempre, e isso é
# melhor do que rebentar uma confirmação por causa de um valor inesperado.
LINGUA_PT = "pt-pt"
LINGUA_EN = "en"
LINGUAS = (LINGUA_PT, LINGUA_EN)


@dataclass(frozen=True)
class MessageOverride:
    """O que esta janela mudou para este envio, e mais nada."""

    language: str = ""
    email_body: str = ""
    whatsapp_body: str = ""

    @classmethod
    def from_request(cls, request):
        """Lê a escolha feita na janela de confirmação.

        Tudo é opcional. Um pedido que não traga nada disto — o formulário
        submetido sem JavaScript, por exemplo — produz um override vazio, que
        se comporta exatamente como o comportamento anterior.
        """

        lingua = (request.POST.get("message_language", "") or "").strip().lower()

        if lingua not in LINGUAS:
            lingua = ""

        return cls(
            language=lingua,
            email_body=(request.POST.get("message_email_body", "") or "").strip(),
            whatsapp_body=(request.POST.get("message_whatsapp_body", "") or "").strip(),
        )

    @property
    def is_empty(self):
        return not (self.language or self.email_body or self.whatsapp_body)

    def language_or(self, fallback):
        """A língua escolhida, ou a que se usaria se ninguém tivesse escolhido."""

        return self.language or fallback


def language_from_request(request):
    """A língua pedida para a pré-visualização, se alguma foi pedida.

    A janela volta a pedir a pré-visualização de cada vez que se troca de
    língua, e é por aqui que o pedido chega.
    """

    lingua = (request.POST.get("message_language", "") or "").strip().lower()

    return lingua if lingua in LINGUAS else ""
