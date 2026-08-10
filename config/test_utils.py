from django.conf import settings
from django.utils import translation


class ResetLanguageMixin:
    """Repõe o idioma ativo no fim de cada teste.

    O LocaleMiddleware ativa um idioma por pedido e não o desativa no fim. Num
    processo de testes isso é persistente: quem visitar /en/ deixa o inglês
    ativo para o teste seguinte, e aí tanto `reverse()` como as mensagens de
    validação mudam de resultado consoante a ordem de execução.

    Aplicar este mixin em qualquer classe que exercite a versão inglesa mantém
    os testes independentes uns dos outros.
    """

    def setUp(self):
        super().setUp()
        self.addCleanup(translation.activate, settings.LANGUAGE_CODE)
