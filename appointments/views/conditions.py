"""As páginas dos problemas que a pedicure terapêutica trata.

Existem por uma razão de tráfego que vale a pena escrever: quem tem uma unha
encravada não procura "pedicure terapêutica" — procura "unha encravada dói". A
página de serviços responde à segunda pergunta que a pessoa faz, não à
primeira. Estas respondem à primeira, e é por isso que são a porta de entrada.
"""

from uuid import uuid4

from django.contrib import messages
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Prefetch
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)
from django.views.generic.detail import SingleObjectMixin

from appointments.forms import ConditionQuestionFormSet, TreatedConditionForm
from appointments.mixins import InternalAreaRequiredMixin
from appointments.models import ConditionQuestion, TreatedCondition
from config.seo import build_condition_structured_data


def publicadas():
    """As que estão no ar, já com as perguntas carregadas.

    Um único sítio a decidir o que é público: enquanto isto estiver certo, não
    há caminho pelo qual um rascunho apareça — nem na lista, nem numa página
    direta, nem no sitemap.
    """

    return TreatedCondition.objects.filter(is_published=True).prefetch_related(
        Prefetch(
            "questions",
            queryset=ConditionQuestion.objects.order_by("display_order", "id"),
        )
    )


class TreatedConditionListView(ListView):
    """O índice: uma linha por problema, com o resumo de cada um."""

    template_name = "appointments/treated_condition_list.html"
    context_object_name = "conditions"

    def get_queryset(self):
        return publicadas().select_related("service")


class TreatedConditionDetailView(DetailView):
    """A página de um problema.

    Um rascunho responde 404 e não 403: uma página por publicar não é uma
    página proibida, é uma página que ainda não existe — e é isso que se deve
    dizer a quem chegue ao endereço por adivinhação ou por um link antigo.
    """

    template_name = "appointments/treated_condition_detail.html"
    context_object_name = "condition"

    def get_queryset(self):
        return publicadas().select_related("service")

    def get_object(self, queryset=None):
        try:
            return super().get_object(queryset)
        except TreatedCondition.DoesNotExist as erro:
            raise Http404("Esta página não existe.") from erro

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        condicao = context["condition"]

        context["structured_data"] = build_condition_structured_data(
            condicao,
            self.request.build_absolute_uri(condicao.get_absolute_url()),
        )

        context["related"] = self.relacionadas(condicao)

        return context

    def relacionadas(self, condicao, quantas=4):
        """As páginas que se seguem a esta, dando a volta no fim da lista.

        Ligações internas entre páginas do mesmo assunto são das poucas coisas
        de SEO que dependem só de nós — e a pessoa que veio pela unha encravada
        muitas vezes também tem a pele do calcanhar gretada.

        A primeira versão disto era `exclude(pk=...)[:4]`, e parecia bem até se
        contarem as ligações recebidas: as quatro primeiras por ordem apareciam
        em toda a gente e as últimas em ninguém. A órtese ungueal, publicada,
        não tinha uma única página a apontar-lhe.

        Rodar resolve as duas metades do problema de uma vez: cada página
        aponta a quatro e é apontada por quatro, seja qual for a ordem dela.
        """

        todas = list(publicadas())

        if len(todas) <= 1:
            return []

        posicao = next(
            (i for i, outra in enumerate(todas) if outra.pk == condicao.pk), 0
        )

        seguintes = todas[posicao + 1 :] + todas[:posicao]

        return seguintes[:quantas]


# ---------------------------------------------------------------------------
# Área interna
# ---------------------------------------------------------------------------


class ConditionAdminListView(InternalAreaRequiredMixin, ListView):
    """A lista de páginas, com o estado de cada uma bem à vista.

    O que interessa saber de relance não é o nome — é quais estão no ar. Uma
    lista onde isso se descobre a abrir cada linha não serve para nada quando
    metade delas está por rever.
    """

    template_name = "appointments/condition_admin_list.html"
    context_object_name = "conditions"

    def get_queryset(self):
        return TreatedCondition.objects.prefetch_related("questions").select_related(
            "service"
        )


class ConditionFormMixin:
    """O que criar e editar têm em comum: o formulário e as perguntas.

    As perguntas são guardadas na mesma submissão que o texto porque são a
    mesma coisa — uma pergunta frequente só faz sentido ao lado da página que
    a motivou, e obrigar a guardar duas vezes é obrigar a lembrar-se de duas.
    """

    model = TreatedCondition
    form_class = TreatedConditionForm
    template_name = "appointments/condition_admin_form.html"
    success_url = reverse_lazy("appointments:condition_admin_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if "questions" not in context:
            context["questions"] = ConditionQuestionFormSet(
                instance=self.object,
                data=self.request.POST if self.request.method == "POST" else None,
            )

        return context

    def form_valid(self, form):
        perguntas = ConditionQuestionFormSet(
            instance=form.instance if form.instance.pk else None,
            data=self.request.POST,
        )

        # As duas metades gravam juntas ou não gravam: uma página guardada com
        # as perguntas por guardar seria pior do que um erro, porque parecia
        # ter corrido bem.
        with transaction.atomic():
            self.object = form.save()

            perguntas.instance = self.object

            if not perguntas.is_valid():
                transaction.set_rollback(True)

                return self.render_to_response(
                    self.get_context_data(form=form, questions=perguntas)
                )

            perguntas.save()

        messages.success(self.request, self.mensagem)

        return redirect(self.get_success_url())


class ConditionCreateView(ConditionFormMixin, InternalAreaRequiredMixin, CreateView):
    mensagem = "Página criada."

    def get_context_data(self, **kwargs):
        # Sem instância ainda: o formset nasce vazio e ganha dono no save.
        self.object = getattr(self, "object", None)

        return super().get_context_data(**kwargs)


class ConditionUpdateView(ConditionFormMixin, InternalAreaRequiredMixin, UpdateView):
    mensagem = "Página atualizada."


class ConditionDeleteView(InternalAreaRequiredMixin, DeleteView):
    """Apagar uma página é apagar um endereço que pode estar indexado.

    Por isso o ecrã de confirmação diz se ela está publicada: apagar um
    rascunho é deitar fora um texto, apagar uma publicada é deixar um 404 onde
    o Google mandava gente.
    """

    model = TreatedCondition
    template_name = "appointments/condition_admin_confirm_delete.html"
    success_url = reverse_lazy("appointments:condition_admin_list")

    def post(self, request, *args, **kwargs):
        messages.success(request, "Página apagada.")

        return super().post(request, *args, **kwargs)


class ConditionPublishToggleView(InternalAreaRequiredMixin, SingleObjectMixin, View):
    """Publicar e despublicar a partir da lista, sem abrir a página.

    Rever oito páginas é abrir, ler, voltar, ligar — e o voltar-e-ligar é o
    passo que se perde. Aqui liga-se de onde se está a ver a lista.

    **Só por POST**, e é por isso que não é uma `DetailView`: um endereço que
    muda o estado do site num GET é um endereço que qualquer rastreador
    dispara sozinho. Sem `get()`, o Django responde 405 — que é a recusa
    certa, e não o erro de servidor que a primeira versão dava.
    """

    model = TreatedCondition
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        condicao = self.get_object()

        if not condicao.is_published and not condicao.has_body():
            messages.error(
                request,
                f"«{condicao.name}» ainda não tem texto escrito.",
            )

            return redirect("appointments:condition_admin_list")

        condicao.is_published = not condicao.is_published
        condicao.save(update_fields=["is_published", "updated_at"])

        messages.success(
            request,
            f"«{condicao.name}» "
            + ("está publicada." if condicao.is_published else "voltou a rascunho."),
        )

        return redirect("appointments:condition_admin_list")


class ConditionImageUploadView(InternalAreaRequiredMixin, View):
    """Recebe uma imagem largada dentro do editor e devolve o endereço dela.

    O editor precisa de um sítio para onde enviar o ficheiro e de uma resposta
    com o endereço onde ele ficou. É só isso — mas é um ponto que aceita
    ficheiros, e um ponto que aceita ficheiros merece ser lido com atenção:

    * **só da área interna**, pelo mixin, e só por POST;
    * **só imagens a sério**: a extensão e o `Content-Type` são o que o
      browser diz, e o browser repete o que o ficheiro diz de si. Quem valida
      é o Pillow, a tentar abrir a imagem — um `.png` que não abre não é um
      `.png`;
    * **com um teto de tamanho**, porque sem ele o limite é o disco;
    * **o nome do ficheiro não é usado**. Vem de fora, pode trazer `../` ou
      um `.php`, e não vale nada: o que interessa é a extensão que o Pillow
      confirmou.

    A resposta é `{"location": ...}` porque é o formato que o editor espera.
    """

    http_method_names = ["post"]

    # Dois megabytes chegam para uma fotografia de página. Acima disto o
    # problema é a página, não o limite.
    TAMANHO_MAXIMO = 2 * 1024 * 1024

    FORMATOS = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif", "WEBP": ".webp"}

    def post(self, request, *args, **kwargs):
        ficheiro = request.FILES.get("file")

        if not ficheiro:
            return JsonResponse({"error": "Nenhum ficheiro recebido."}, status=400)

        if ficheiro.size > self.TAMANHO_MAXIMO:
            return JsonResponse(
                {"error": "A imagem não pode passar de 2 MB."}, status=400
            )

        from PIL import Image, UnidentifiedImageError

        try:
            imagem = Image.open(ficheiro)
            imagem.verify()
        except (UnidentifiedImageError, OSError, ValueError):
            return JsonResponse({"error": "Isto não é uma imagem."}, status=400)

        extensao = self.FORMATOS.get(imagem.format)

        if not extensao:
            return JsonResponse({"error": "Use JPG, PNG, GIF ou WEBP."}, status=400)

        # `verify()` deixa o ficheiro na posição errada para o voltar a ler.
        ficheiro.seek(0)

        nome = default_storage.save(
            f"o-que-tratamos/texto/{uuid4().hex}{extensao}",
            ficheiro,
        )

        return JsonResponse({"location": default_storage.url(nome)})
