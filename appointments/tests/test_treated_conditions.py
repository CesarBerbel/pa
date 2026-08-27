"""As páginas dos problemas tratados.

Duas coisas se testam aqui, e a primeira importa mais do que a segunda: que um
rascunho não aparece a ninguém, e que uma página publicada leva o que o Google
precisa de ler.
"""

import json
import re
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import translation
from django.urls import reverse

from appointments.models import ConditionQuestion, TreatedCondition

# As fotografias dos testes não têm nada que fazer no `media/` do projeto: sem
# isto, cada passagem deixava lá ficheiros que ninguém volta a apagar.
MEDIA_DE_TESTE = tempfile.mkdtemp(prefix="pa-o-que-tratamos-")


class TreatedConditionBase(TestCase):
    def condicao(self, slug="unha-encravada", publicada=True, **extra):
        campos = {
            "slug": slug,
            "name": "Unha encravada",
            "summary": "O canto da unha entra na pele e o dedo dói ao mais leve toque.",
            "body": (
                "<h2>O que é</h2>"
                "<p>É o bordo da unha a crescer para dentro da pele.</p>"
                "<h2>Sinais de alerta</h2>"
                "<p>Dor ao calçar, vermelhidão, pus.</p>"
            ),
            "is_published": publicada,
        }
        campos.update(extra)

        return TreatedCondition.objects.create(**campos)


class DraftsAreInvisibleTests(TreatedConditionBase):
    """Um rascunho não é uma página escondida: é uma página que não existe.

    O texto é sobre saúde e nasce por rever. Se um rascunho escapasse por
    algum caminho — a lista, o endereço direto, o sitemap — a revisão deixava
    de ser uma porta e passava a ser uma sugestão.
    """

    def setUp(self):
        # As migrações semeiam oito, todas por publicar. Ficam de fora para
        # cada teste dizer o seu mundo.
        TreatedCondition.objects.all().delete()

    def test_a_draft_is_not_on_the_index(self):
        rascunho = self.condicao(publicada=False)

        resposta = self.client.get(reverse("appointments:treated_condition_list"))

        # Pelo endereço e não pelo nome: "unha encravada" também está nas
        # palavras-chave do índice, e procurar o nome encontrava a etiqueta em
        # vez da lista.
        self.assertNotContains(resposta, rascunho.get_absolute_url())

    def test_a_draft_answers_404_at_its_own_address(self):
        rascunho = self.condicao(publicada=False)

        resposta = self.client.get(rascunho.get_absolute_url())

        self.assertEqual(resposta.status_code, 404)

    def test_a_draft_is_not_in_the_sitemap(self):
        rascunho = self.condicao(publicada=False)

        resposta = self.client.get(reverse("sitemap_xml"))

        self.assertNotContains(resposta, rascunho.slug)

    def test_publishing_puts_it_in_all_three(self):
        condicao = self.condicao(publicada=False)

        condicao.is_published = True
        condicao.save()

        indice = self.client.get(reverse("appointments:treated_condition_list"))
        pagina = self.client.get(condicao.get_absolute_url())
        sitemap = self.client.get(reverse("sitemap_xml"))

        self.assertContains(indice, condicao.name)
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(sitemap, condicao.slug)


class SeededConditionsTests(TestCase):
    """O que a migração semeou, tal como ela o deixou.

    Sem apagar nada primeiro: o que se está a medir é o estado em que as
    páginas nascem, e apagá-las para as recriar mediria outra coisa.
    """

    def test_everything_seeded_starts_unpublished(self):
        from appointments.default_conditions import CONDICOES

        semeadas = TreatedCondition.objects.filter(
            slug__in=[entrada["slug"] for entrada in CONDICOES]
        )

        self.assertEqual(semeadas.count(), len(CONDICOES))
        self.assertEqual(semeadas.filter(is_published=True).count(), 0)

    def test_the_podiatric_risk_page_keeps_the_searched_term_where_google_reads_it(
        self,
    ):
        """O nome muda onde se lê; o termo procurado fica onde é procurado.

        O card da página inicial sempre lhe chamou "Risco Podológico". O que
        as pessoas escrevem no Google é "pé diabético", e é por isso que o
        endereço e o título ficaram como estavam.
        """

        condicao = TreatedCondition.objects.get(slug="pe-diabetico")

        self.assertEqual(condicao.name, "Risco Podológico")
        self.assertEqual(condicao.slug, "pe-diabetico")
        self.assertIn("Pé diabético", condicao.meta_title)
        self.assertIn("pé diabético", condicao.keywords)

    def test_every_seeded_page_is_complete(self):
        # Uma página semeada com uma secção em branco seria trabalho a menos
        # feito aqui e trabalho a mais para quem a for rever.
        for condicao in TreatedCondition.objects.all():
            with self.subTest(slug=condicao.slug):
                self.assertTrue(condicao.has_body())
                self.assertTrue(condicao.questions.exists())
                self.assertTrue(condicao.meta_description.strip())
                self.assertLessEqual(len(condicao.meta_title), 70)


class ConditionPageTests(TreatedConditionBase):
    def setUp(self):
        TreatedCondition.objects.all().delete()

        self.condition = self.condicao()

        ConditionQuestion.objects.create(
            condition=self.condition,
            question="O tratamento dói?",
            answer="O que dói é a unha encravada.",
            display_order=10,
        )

    def json_ld(self, resposta):
        bloco = re.search(
            r'<script type="application/ld\+json">(.*?)</script>',
            resposta.content.decode(),
            re.DOTALL,
        )

        self.assertIsNotNone(bloco, "A página ficou sem JSON-LD.")

        return json.loads(bloco.group(1))

    def tipos(self, dados):
        return {no["@type"] for no in dados["@graph"]}

    def test_the_text_is_shown_as_written(self):
        # Os títulos são agora parte do texto, e é a profissional que os
        # escolhe: a página deixou de ter cinco secções fixas.
        resposta = self.client.get(self.condition.get_absolute_url())

        self.assertContains(resposta, "<h2>O que é</h2>", html=False)
        self.assertContains(resposta, "Sinais de alerta")

    def test_a_page_can_carry_a_table(self):
        # É metade da razão de existir um editor: uma tabela de sintomas não
        # cabia em cinco caixas de texto simples.
        self.condition.body = "<table><tbody><tr><th>Sinal</th><td>Dor ao calçar</td></tr></tbody></table>"
        self.condition.save()

        resposta = self.client.get(self.condition.get_absolute_url())

        self.assertContains(resposta, "<table>")
        self.assertContains(resposta, "Dor ao calçar")

    def test_the_questions_become_a_faq_for_google(self):
        # É a única peça daqui que muda o aspeto do resultado da pesquisa.
        dados = self.json_ld(self.client.get(self.condition.get_absolute_url()))

        self.assertIn("FAQPage", self.tipos(dados))

        faq = next(no for no in dados["@graph"] if no["@type"] == "FAQPage")

        self.assertEqual(faq["mainEntity"][0]["name"], "O tratamento dói?")

    def test_without_questions_there_is_no_empty_faq(self):
        # Um FAQPage sem perguntas é uma promessa por cumprir.
        self.condition.questions.all().delete()

        dados = self.json_ld(self.client.get(self.condition.get_absolute_url()))

        self.assertNotIn("FAQPage", self.tipos(dados))

    def test_the_breadcrumb_says_the_same_as_the_page(self):
        resposta = self.client.get(self.condition.get_absolute_url())
        dados = self.json_ld(resposta)

        trilho = next(no for no in dados["@graph"] if no["@type"] == "BreadcrumbList")
        nomes = [item["name"] for item in trilho["itemListElement"]]

        self.assertEqual(nomes, ["Início", "O que tratamos", self.condition.name])

        # E o mesmo caminho está desenhado na página: um caminho estruturado
        # que ninguém vê é uma afirmação que ninguém pode verificar.
        self.assertContains(resposta, "O que tratamos")

    def test_the_written_meta_description_wins_over_the_summary(self):
        self.condition.meta_description = "Uma descrição escrita à mão."
        self.condition.save()

        resposta = self.client.get(self.condition.get_absolute_url())

        self.assertContains(resposta, "Uma descrição escrita à mão.")

    def test_without_one_the_summary_is_cut_at_a_word(self):
        # O Google corta aos ~155 caracteres, e um corte a meio de uma palavra
        # é o que faz uma descrição parecer partida.
        self.condition.summary = "palavra " * 40
        self.condition.save()

        descricao = self.condition.seo_description()

        self.assertLessEqual(len(descricao), 156)
        self.assertTrue(descricao.endswith("…"))
        self.assertFalse(descricao[:-1].endswith("palavr"))

    def test_a_script_never_reaches_the_page(self):
        """A página mostra HTML, e por isso o HTML é limpo à entrada.

        Antes, o texto era escapado à saída e nada disto era preciso. Com um
        editor, o que se escreve é HTML e a página tem de o mostrar como tal —
        a garantia mudou de sítio, e é o `save()` do modelo que a dá.

        O caso a apanhar não é a profissional a escrever `<script>`: é o que
        vem colado de outra página web.
        """

        self.condition.body = "<p>Texto</p><script>alert(1)</script>"
        self.condition.save()

        # Já não está guardado — não é escondido à saída.
        self.assertNotIn("<script>", self.condition.body)

        resposta = self.client.get(self.condition.get_absolute_url())

        self.assertNotContains(resposta, "<script>alert(1)</script>")
        self.assertContains(resposta, "<p>Texto</p>")

    def test_an_event_handler_is_stripped_from_pasted_markup(self):
        self.condition.body = '<p onclick="alert(1)">Clique</p>'
        self.condition.save()

        self.assertNotIn("onclick", self.condition.body)
        self.assertIn("Clique", self.condition.body)

    def test_a_javascript_link_loses_its_address(self):
        self.condition.body = '<a href="javascript:alert(1)">mau</a>'
        self.condition.save()

        self.assertNotIn("javascript:", self.condition.body)

    def test_an_outside_link_is_given_noopener(self):
        # Sem `noopener`, a página aberta ganha uma referência para esta e
        # pode trocá-la por outra debaixo dos pés de quem clicou.
        self.condition.body = '<a href="https://exemplo.pt">fora</a>'
        self.condition.save()

        self.assertIn('rel="noopener noreferrer"', self.condition.body)

    def test_an_empty_editor_does_not_count_as_text(self):
        # Um editor por preencher devolve `<p><br></p>`, que passa por
        # preenchido em qualquer verificação ingénua.
        self.condition.body = "<p><br></p>"
        self.condition.save()

        self.assertFalse(self.condition.has_body())

    def test_the_page_proposes_its_service_when_it_has_one(self):
        from appointments.tests.factories import create_test_service

        servico = create_test_service(duration_minutes=45)
        self.condition.service = servico
        self.condition.save()

        resposta = self.client.get(self.condition.get_absolute_url())

        self.assertContains(resposta, f"?service={servico.pk}")

    def test_without_a_service_it_still_leads_to_the_agenda(self):
        # Uma página sem serviço continua a valer: leva à agenda geral.
        resposta = self.client.get(self.condition.get_absolute_url())

        self.assertContains(resposta, reverse("appointments:public_visual_schedule"))

    def test_the_footer_link_only_appears_once_something_is_published(self):
        # Uma ligação que leva a uma página vazia ensina as pessoas a não
        # clicar nela. Está no rodapé e não na barra de cima: a barra já tem
        # seis entradas e não aguenta a sétima em ecrã pequeno — mas o rodapé
        # também está em todas as páginas, que é o que interessa para o
        # índice ser encontrado a partir de qualquer sítio.
        endereco = reverse("appointments:treated_condition_list")

        TreatedCondition.objects.all().update(is_published=False)
        self.assertNotContains(self.client.get(reverse("home")), f'href="{endereco}"')

        TreatedCondition.objects.all().update(is_published=True)
        self.assertContains(self.client.get(reverse("home")), f'href="{endereco}"')

    def test_a_home_card_only_links_once_its_page_is_published(self):
        # Os cards existiam antes destas páginas. Ligá-los sem condição punha
        # sete ligações para 404 na página mais visitada do site.
        self.condition.slug = "unha-encravada"
        self.condition.is_published = False
        self.condition.save()

        home = self.client.get(reverse("home"))
        self.assertNotContains(home, self.condition.get_absolute_url())

        self.condition.is_published = True
        self.condition.save()

        home = self.client.get(reverse("home"))
        self.assertContains(home, self.condition.get_absolute_url())

    def test_a_home_card_is_clickable_from_end_to_end(self):
        # `stretched-link` faz o cartão inteiro clicável sem o transformar num
        # link gigante: o texto do link continua a ser o nome do problema.
        TreatedCondition.objects.all().update(is_published=True)

        resposta = self.client.get(reverse("home"))

        self.assertContains(resposta, "stretched-link")

    def test_an_unpublished_card_has_no_empty_link(self):
        # Um href vazio recarrega a home em vez de não fazer nada.
        TreatedCondition.objects.all().update(is_published=False)

        resposta = self.client.get(reverse("home"))

        self.assertNotContains(resposta, 'href=""')

    def test_the_index_card_has_one_link_and_not_two(self):
        # Dois links para o mesmo sítio no mesmo cartão é uma paragem a mais
        # para quem navega por teclado. O "Saber mais" é sinal visual.
        TreatedCondition.objects.all().update(is_published=False)
        self.condition.is_published = True
        self.condition.save()

        corpo = self.client.get(
            reverse("appointments:treated_condition_list")
        ).content.decode()

        self.assertEqual(corpo.count(f'href="{self.condition.get_absolute_url()}"'), 1)

    def test_a_card_without_a_page_stays_a_card(self):
        # "Feridas e pensos" não tem página, e continua a ser um card sem
        # ligação nenhuma — e não um card partido.
        TreatedCondition.objects.all().update(is_published=True)

        home = self.client.get(reverse("home"))

        self.assertContains(home, "Feridas e pensos")
        self.assertNotContains(home, "/o-que-tratamos/feridas")

    def test_the_pages_link_to_each_other(self):
        outra = self.condicao(slug="calos", name="Calos e calosidades")

        resposta = self.client.get(self.condition.get_absolute_url())

        self.assertContains(resposta, outra.get_absolute_url())

    def test_the_last_pages_in_order_are_linked_too(self):
        """Ninguém fica sem ligações por estar no fim da lista.

        A primeira versão mostrava as quatro primeiras por ordem, e assim as
        últimas não eram apontadas por página nenhuma: a órtese ungueal estava
        publicada e não tinha uma única ligação a entrar. A lista roda, e cada
        página é apontada por tantas quantas aponta.
        """

        TreatedCondition.objects.all().delete()

        criadas = [
            self.condicao(slug=f"problema-{i}", name=f"Problema {i}", display_order=i)
            for i in range(1, 9)
        ]

        recebidas = {condicao.slug: 0 for condicao in criadas}

        for condicao in criadas:
            corpo = self.client.get(condicao.get_absolute_url()).content.decode()

            for outra in criadas:
                if outra.pk != condicao.pk and outra.get_absolute_url() in corpo:
                    recebidas[outra.slug] += 1

        self.assertEqual(set(recebidas.values()), {4})

    def test_a_page_never_links_to_itself(self):
        for i in range(1, 4):
            self.condicao(slug=f"outra-{i}", name=f"Outra {i}", display_order=i)

        resposta = self.client.get(self.condition.get_absolute_url())

        self.assertNotContains(
            resposta,
            f'href="{self.condition.get_absolute_url()}"',
        )


class ConditionInternalAreaTests(TreatedConditionBase):
    """Editar as páginas sem sair da área interna.

    Estavam só no admin do Django, que é outro ecrã, outra sessão e outro
    vocabulário. Quem escreve estas páginas é quem trata as pessoas, e o sítio
    onde ela já trabalha é este.
    """

    def setUp(self):
        TreatedCondition.objects.all().delete()

        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.client.force_login(self.user)

        self.condition = self.condicao(publicada=False)

    def dados(self, **extra):
        campos = {
            "name": self.condition.name,
            "slug": self.condition.slug,
            "summary": self.condition.summary,
            "body": self.condition.body,
            "meta_title": "",
            "meta_description": "",
            "keywords": "",
            "display_order": 10,
            "questions-TOTAL_FORMS": "0",
            "questions-INITIAL_FORMS": "0",
            "questions-MIN_NUM_FORMS": "0",
            "questions-MAX_NUM_FORMS": "1000",
        }
        campos.update(extra)

        return campos

    def test_the_list_shows_which_pages_are_live(self):
        # O que interessa de relance não é o nome — é quais estão no ar.
        resposta = self.client.get(reverse("appointments:condition_admin_list"))

        self.assertContains(resposta, self.condition.name)
        self.assertContains(resposta, "Rascunho")

    def test_a_page_can_be_written_here(self):
        self.client.post(
            reverse("appointments:condition_admin_create"),
            data=self.dados(slug="nova", name="Nova", summary="Um resumo."),
        )

        self.assertTrue(TreatedCondition.objects.filter(slug="nova").exists())

    def test_a_page_can_be_rewritten_here(self):
        self.client.post(
            reverse("appointments:condition_admin_update", args=[self.condition.pk]),
            data=self.dados(body="<p>Texto novo.</p>"),
        )

        self.condition.refresh_from_db()

        self.assertEqual(self.condition.body, "<p>Texto novo.</p>")

    def test_the_questions_are_saved_with_the_page(self):
        # Guardar duas vezes é ter de se lembrar de duas.
        self.client.post(
            reverse("appointments:condition_admin_update", args=[self.condition.pk]),
            data=self.dados(
                **{
                    "questions-TOTAL_FORMS": "1",
                    "questions-0-question": "Isto dói?",
                    "questions-0-answer": "O que dói é o problema.",
                    "questions-0-display_order": "10",
                }
            ),
        )

        self.assertEqual(
            self.condition.questions.first().question,
            "Isto dói?",
        )

    def test_a_broken_question_does_not_save_half_the_page(self):
        # Uma página guardada com as perguntas por guardar seria pior do que um
        # erro, porque parecia ter corrido bem.
        resposta = self.client.post(
            reverse("appointments:condition_admin_update", args=[self.condition.pk]),
            data=self.dados(
                body="<p>Texto que não devia ficar.</p>",
                **{
                    "questions-TOTAL_FORMS": "1",
                    "questions-0-question": "Uma pergunta sem resposta?",
                    "questions-0-answer": "",
                    "questions-0-display_order": "10",
                },
            ),
        )

        self.condition.refresh_from_db()

        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("não devia ficar", self.condition.body)
        self.assertFalse(self.condition.questions.exists())

    def test_an_empty_page_cannot_be_published(self):
        # Publicar uma página vazia é publicar um resultado que não responde a
        # nada.
        resposta = self.client.post(
            reverse("appointments:condition_admin_update", args=[self.condition.pk]),
            data=self.dados(body="<p><br></p>", is_published="on"),
        )

        self.condition.refresh_from_db()

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(self.condition.is_published)

    def test_publishing_from_the_list_takes_one_click(self):
        # Rever oito páginas é abrir, ler, voltar, ligar — e o voltar-e-ligar é
        # o passo que se perde.
        self.client.post(
            reverse("appointments:condition_admin_publish", args=[self.condition.pk])
        )

        self.condition.refresh_from_db()

        self.assertTrue(self.condition.is_published)

    def test_the_same_button_unpublishes(self):
        self.condition.is_published = True
        self.condition.save()

        self.client.post(
            reverse("appointments:condition_admin_publish", args=[self.condition.pk])
        )

        self.condition.refresh_from_db()

        self.assertFalse(self.condition.is_published)

    def test_the_publish_button_refuses_an_empty_page(self):
        vazia = TreatedCondition.objects.create(
            slug="vazia", name="Vazia", summary="Sem texto."
        )

        self.client.post(
            reverse("appointments:condition_admin_publish", args=[vazia.pk])
        )

        vazia.refresh_from_db()

        self.assertFalse(vazia.is_published)

    def test_a_get_is_refused_and_changes_nothing(self):
        # Um endereço que muda o estado do site num GET é um endereço que
        # qualquer rastreador dispara sozinho. 405 é a recusa certa — a
        # primeira versão devolvia um erro de servidor, que é outra coisa.
        resposta = self.client.get(
            reverse("appointments:condition_admin_publish", args=[self.condition.pk])
        )

        self.condition.refresh_from_db()

        self.assertEqual(resposta.status_code, 405)
        self.assertFalse(self.condition.is_published)

    def test_a_page_can_be_deleted(self):
        self.client.post(
            reverse("appointments:condition_admin_delete", args=[self.condition.pk])
        )

        self.assertFalse(TreatedCondition.objects.filter(pk=self.condition.pk).exists())

    def test_deleting_a_live_page_is_announced_as_such(self):
        self.condition.is_published = True
        self.condition.save()

        resposta = self.client.get(
            reverse("appointments:condition_admin_delete", args=[self.condition.pk])
        )

        self.assertContains(resposta, "está publicada")

    def test_the_menu_leads_here(self):
        resposta = self.client.get(reverse("appointments:condition_admin_list"))

        self.assertContains(resposta, reverse("appointments:condition_admin_list"))


class ConditionInternalAccessTests(TreatedConditionBase):
    """Escrever as páginas do site é da área interna."""

    def setUp(self):
        TreatedCondition.objects.all().delete()

        self.condition = self.condicao(publicada=False)

        self.customer_user = get_user_model().objects.create_user(
            email="cliente@example.com",
            password="StrongPassword123",
            full_name="Cliente",
        )

    def paginas(self):
        return [
            reverse("appointments:condition_admin_list"),
            reverse("appointments:condition_admin_create"),
            reverse("appointments:condition_admin_update", args=[self.condition.pk]),
            reverse("appointments:condition_admin_delete", args=[self.condition.pk]),
        ]

    def test_anonymous_visitors_are_turned_away(self):
        for url in self.paginas():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)

    def test_customers_are_turned_away(self):
        self.client.force_login(self.customer_user)

        for url in self.paginas():
            with self.subTest(url=url):
                self.assertNotEqual(self.client.get(url).status_code, 200)

    def test_a_customer_cannot_publish_a_page(self):
        self.client.force_login(self.customer_user)

        self.client.post(
            reverse("appointments:condition_admin_publish", args=[self.condition.pk])
        )

        self.condition.refresh_from_db()

        self.assertFalse(self.condition.is_published)


@override_settings(MEDIA_ROOT=MEDIA_DE_TESTE)
class ConditionHeroImageTests(TreatedConditionBase):
    """A imagem de abertura da página.

    Opcional em toda a parte: uma página sem fotografia continua a responder à
    pergunta de quem chegou.
    """

    def setUp(self):
        TreatedCondition.objects.all().delete()

        self.condition = self.condicao()

    def imagem(self, nome="banner.png"):
        """Um PNG mínimo, gerado aqui.

        Um ficheiro de exemplo no repositório seria mais uma coisa a manter, e
        o que se está a testar não é a fotografia — é o campo.
        """

        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (40, 20), "#d8a7b1").save(buffer, format="PNG")

        return SimpleUploadedFile(nome, buffer.getvalue(), content_type="image/png")

    def test_a_page_without_an_image_still_works(self):
        resposta = self.client.get(self.condition.get_absolute_url())

        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, "condition-hero")

    def test_the_image_opens_the_page_when_there_is_one(self):
        self.condition.hero_image = self.imagem()
        self.condition.save()

        resposta = self.client.get(self.condition.get_absolute_url())

        self.assertContains(resposta, self.condition.hero_image.url)

    def test_with_a_banner_the_title_is_hidden_but_still_there(self):
        """O título deixa de se ver, não deixa de existir.

        O banner traz o nome escrito, e mostrá-lo outra vez em texto era
        dizê-lo duas vezes. Mas texto dentro de uma imagem é invisível para o
        Google e para quem usa leitor de ecrã: o <h1> fica, escondido.
        """

        self.condition.hero_image = self.imagem()
        self.condition.save()

        resposta = self.client.get(self.condition.get_absolute_url())

        self.assertContains(resposta, "visually-hidden")
        self.assertContains(resposta, self.condition.name)

    def test_without_a_banner_the_title_is_visible(self):
        # Sem imagem não há nada que diga o nome, portanto o título tem de se
        # ver.
        resposta = self.client.get(self.condition.get_absolute_url())

        self.assertContains(resposta, 'class="section-title mb-3"')
        self.assertNotContains(resposta, '<h1 class="visually-hidden"')

    def test_the_description_falls_back_to_the_name(self):
        # Um alt vazio numa imagem que carrega conteúdo diz a quem usa leitor
        # de ecrã que ali não há nada — e ali há.
        self.condition.hero_image = self.imagem()
        self.condition.hero_alt = ""
        self.condition.save()

        self.assertEqual(self.condition.hero_description, self.condition.name)

    def test_a_written_description_wins(self):
        self.condition.hero_alt = "Um pé visto de cima, com a unha do dedo grande."
        self.condition.save()

        self.assertEqual(
            self.condition.hero_description,
            "Um pé visto de cima, com a unha do dedo grande.",
        )

    def test_the_image_goes_into_the_structured_data(self):
        self.condition.hero_image = self.imagem()
        self.condition.save()

        resposta = self.client.get(self.condition.get_absolute_url())
        dados = json.loads(
            re.search(
                r'<script type="application/ld\+json">(.*?)</script>',
                resposta.content.decode(),
                re.DOTALL,
            ).group(1)
        )

        pagina = next(no for no in dados["@graph"] if no["@type"] == "WebPage")

        # Absoluto: um `/media/...` dentro de um JSON-LD é lido por um robô que
        # não sabe de que site veio.
        self.assertTrue(
            pagina["primaryImageOfPage"]["url"].startswith("http"),
            pagina["primaryImageOfPage"]["url"],
        )

    def test_without_an_image_nothing_is_declared(self):
        resposta = self.client.get(self.condition.get_absolute_url())

        self.assertNotContains(resposta, "primaryImageOfPage")

    def test_a_page_without_an_image_keeps_the_default_social_card(self):
        """O `{% block %}` está dentro do `{% if %}` e não ao contrário.

        Envolvido por fora, o bloco substituía sempre o do base.html — o Django
        regista os blocos ao analisar o ficheiro, sem olhar às condições que os
        rodeiam — e as páginas sem imagem ficavam com um og:image vazio.
        """

        resposta = self.client.get(self.condition.get_absolute_url())

        self.assertNotContains(resposta, 'property="og:image" content=""')

    def test_the_form_can_receive_a_file(self):
        # Sem enctype no formulário o ficheiro nunca chega, e a página grava-se
        # em silêncio sem a imagem.
        user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.client.force_login(user)

        resposta = self.client.get(
            reverse("appointments:condition_admin_update", args=[self.condition.pk])
        )

        self.assertContains(resposta, 'enctype="multipart/form-data"')

        self.client.post(
            reverse("appointments:condition_admin_update", args=[self.condition.pk]),
            data={
                "name": self.condition.name,
                "slug": self.condition.slug,
                "summary": self.condition.summary,
                "hero_image": self.imagem(),
                "hero_alt": "Um pé visto de cima.",
                "body": self.condition.body,
                "meta_title": "",
                "meta_description": "",
                "keywords": "",
                "display_order": 10,
                "questions-TOTAL_FORMS": "0",
                "questions-INITIAL_FORMS": "0",
                "questions-MIN_NUM_FORMS": "0",
                "questions-MAX_NUM_FORMS": "1000",
            },
        )

        self.condition.refresh_from_db()

        self.assertTrue(self.condition.hero_image)
        self.assertEqual(self.condition.hero_alt, "Um pé visto de cima.")


@override_settings(MEDIA_ROOT=MEDIA_DE_TESTE)
class ConditionImageUploadTests(TreatedConditionBase):
    """O ponto que recebe as imagens largadas dentro do editor.

    É o único sítio desta funcionalidade que aceita ficheiros de fora, e por
    isso é o que merece ser lido com mais atenção.
    """

    def setUp(self):
        TreatedCondition.objects.all().delete()

        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.url = reverse("appointments:condition_image_upload")

    def png(self, nome="foto.png"):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (30, 20), "#d8a7b1").save(buffer, format="PNG")

        return SimpleUploadedFile(nome, buffer.getvalue(), content_type="image/png")

    def test_an_image_comes_back_with_its_address(self):
        self.client.force_login(self.user)

        resposta = self.client.post(self.url, {"file": self.png()})

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("location", resposta.json())

    def test_a_file_that_is_not_an_image_is_refused(self):
        # A extensão e o Content-Type são o que o browser diz, e o browser
        # repete o que o ficheiro diz de si. Quem valida é o Pillow.
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.user)

        disfarcado = SimpleUploadedFile(
            "foto.png", b"<?php echo 1; ?>", content_type="image/png"
        )

        resposta = self.client.post(self.url, {"file": disfarcado})

        self.assertEqual(resposta.status_code, 400)

    def test_the_name_that_comes_from_outside_is_not_used(self):
        # Pode trazer `../` ou um `.php`. O que vale é a extensão que o Pillow
        # confirmou.
        self.client.force_login(self.user)

        resposta = self.client.post(self.url, {"file": self.png("../../evil.php.png")})

        endereco = resposta.json()["location"]

        self.assertNotIn("evil", endereco)
        self.assertNotIn("..", endereco)
        self.assertTrue(endereco.endswith(".png"), endereco)

    def test_an_oversized_file_is_refused(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.user)

        enorme = SimpleUploadedFile(
            "grande.png", b"x" * (3 * 1024 * 1024), content_type="image/png"
        )

        resposta = self.client.post(self.url, {"file": enorme})

        self.assertEqual(resposta.status_code, 400)

    def test_a_get_is_refused(self):
        self.client.force_login(self.user)

        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_a_customer_cannot_upload(self):
        cliente = get_user_model().objects.create_user(
            email="cliente@example.com",
            password="StrongPassword123",
            full_name="Cliente",
        )

        self.client.force_login(cliente)

        resposta = self.client.post(self.url, {"file": self.png()})

        self.assertNotEqual(resposta.status_code, 200)

    def test_an_anonymous_visitor_cannot_upload(self):
        resposta = self.client.post(self.url, {"file": self.png()})

        self.assertNotEqual(resposta.status_code, 200)


class ConditionEnglishTests(TreatedConditionBase):
    """A versão inglesa das páginas.

    Coimbra tem quem procure em inglês, e "ingrown toenail Coimbra" é uma
    pesquisa que tem de levar a algum lado.
    """

    def setUp(self):
        self.condition = TreatedCondition.objects.get(slug="unha-encravada")
        self.condition.is_published = True
        self.condition.save()

    def test_everything_seeded_has_an_english_version(self):
        from appointments.default_conditions_en import CONDICOES_EN

        for slug in CONDICOES_EN:
            with self.subTest(slug=slug):
                condicao = TreatedCondition.objects.get(slug=slug)

                self.assertTrue(condicao.name_en.strip())
                self.assertTrue(condicao.body_en.strip())
                self.assertTrue(condicao.meta_title_en.strip())
                self.assertTrue(condicao.meta_description_en.strip())
                self.assertLessEqual(len(condicao.meta_title_en), 70)

    def test_the_questions_are_translated_too(self):
        # Sem elas, a página inglesa perde a parte que o Google mostra aberta
        # nos resultados.
        for pergunta in self.condition.questions.all():
            with self.subTest(pergunta=pergunta.question):
                self.assertTrue(pergunta.question_en.strip())
                self.assertTrue(pergunta.answer_en.strip())

    def test_the_english_page_is_in_english_end_to_end(self):
        with translation.override("en"):
            self.assertEqual(self.condition.display_name, "Ingrown toenail")
            self.assertIn("Ingrown toenail", self.condition.seo_title())
            self.assertIn("What it is", self.condition.display_body)
            self.assertIn("ingrown toenail", self.condition.display_keywords)

    def test_the_portuguese_page_is_untouched(self):
        with translation.override("pt-pt"):
            self.assertEqual(self.condition.display_name, "Unha encravada")
            self.assertIn("O que é", self.condition.display_body)

    def test_a_missing_translation_falls_back_field_by_field(self):
        # Uma tradução feita a meio deixa a página meio traduzida, não meio em
        # branco.
        self.condition.meta_title_en = ""
        self.condition.save()

        with translation.override("en"):
            self.assertEqual(self.condition.seo_title(), "Ingrown toenail")
            self.assertIn("What it is", self.condition.display_body)

    def test_the_english_page_keeps_the_portuguese_slug(self):
        """O endereço é o mesmo, com o prefixo do idioma à frente.

        `/en/o-que-tratamos/unha-encravada/` e não um endereço traduzido: um
        segundo `slug` para o mesmo conteúdo dividia em dois o que o Google já
        sabe sobre a página, e é o par que o `hreflang` já anuncia.
        """

        with translation.override("en"):
            ingles = self.condition.get_absolute_url()

        with translation.override("pt-pt"):
            portugues = self.condition.get_absolute_url()

        self.assertEqual(ingles, "/en" + portugues)
        self.assertIn("unha-encravada", ingles)

    def test_the_seeded_english_is_still_unpublished_by_default(self):
        # Traduzir não é publicar.
        por_publicar = TreatedCondition.objects.exclude(pk=self.condition.pk)

        self.assertEqual(por_publicar.filter(is_published=True).count(), 0)


class ConditionEnglishEditingTests(TreatedConditionBase):
    """O inglês tem de se poder editar sem sair da área interna.

    O registo no admin do Django saiu quando este ecrã nasceu. Sem estes
    campos no formulário, a versão inglesa não teria onde ser tocada.
    """

    def setUp(self):
        self.condition = TreatedCondition.objects.get(slug="unha-encravada")

        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.client.force_login(self.user)

    def test_the_english_fields_are_on_the_form(self):
        resposta = self.client.get(
            reverse("appointments:condition_admin_update", args=[self.condition.pk])
        )

        for campo in [
            "name_en",
            "summary_en",
            "body_en",
            "meta_title_en",
            "meta_description_en",
            "keywords_en",
            "hero_alt_en",
        ]:
            with self.subTest(campo=campo):
                self.assertContains(resposta, f'name="{campo}"')

    def test_the_english_text_gets_an_editor_too(self):
        # A primeira versão do JavaScript punha o editor só na primeira caixa
        # que encontrasse, e a inglesa ficava uma caixa de texto crua.
        resposta = self.client.get(
            reverse("appointments:condition_admin_update", args=[self.condition.pk])
        )

        self.assertEqual(resposta.content.decode().count("editor-rico"), 3)

    def test_the_english_text_is_cleaned_like_the_portuguese(self):
        self.condition.body_en = "<p>Text</p><script>alert(1)</script>"
        self.condition.save()

        self.assertNotIn("<script>", self.condition.body_en)
        self.assertIn("<p>Text</p>", self.condition.body_en)


@override_settings(MEDIA_ROOT=MEDIA_DE_TESTE)
class ConditionEnglishHeroTests(TreatedConditionBase):
    """Um banner próprio para a versão inglesa.

    Só faz falta porque o banner tem texto escrito nele — e como tem, faz.
    """

    def setUp(self):
        TreatedCondition.objects.all().delete()

        self.condition = self.condicao()

    def imagem(self, nome="banner.png"):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (40, 20), "#d8a7b1").save(buffer, format="PNG")

        return SimpleUploadedFile(nome, buffer.getvalue(), content_type="image/png")

    def test_the_english_page_uses_its_own_banner(self):
        self.condition.hero_image = self.imagem("pt.png")
        self.condition.hero_image_en = self.imagem("en.png")
        self.condition.save()

        with translation.override("en"):
            self.assertEqual(self.condition.display_hero, self.condition.hero_image_en)

        with translation.override("pt-pt"):
            self.assertEqual(self.condition.display_hero, self.condition.hero_image)

    def test_without_one_it_borrows_the_portuguese_banner(self):
        # Uma página sem imagem é pior do que uma com a imagem da outra língua.
        self.condition.hero_image = self.imagem("pt.png")
        self.condition.save()

        with translation.override("en"):
            self.assertEqual(self.condition.display_hero, self.condition.hero_image)

    def test_a_borrowed_banner_leaves_the_english_title_visible(self):
        """É o ponto todo desta separação.

        O `<h1>` esconde-se quando há banner porque o nome já vai lá escrito.
        Se a página inglesa estiver a usar o banner português, o nome escrito
        está em português — e esconder o `<h1>` inglês deixava o leitor sem um
        título que soubesse ler.
        """

        self.condition.hero_image = self.imagem("pt.png")
        self.condition.save()

        with translation.override("en"):
            self.assertFalse(self.condition.hero_carries_title)

        with translation.override("pt-pt"):
            self.assertTrue(self.condition.hero_carries_title)

    def test_with_its_own_banner_the_english_title_hides_too(self):
        self.condition.hero_image = self.imagem("pt.png")
        self.condition.hero_image_en = self.imagem("en.png")
        self.condition.save()

        with translation.override("en"):
            self.assertTrue(self.condition.hero_carries_title)

    def test_the_form_offers_the_english_banner(self):
        user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.client.force_login(user)

        resposta = self.client.get(
            reverse("appointments:condition_admin_update", args=[self.condition.pk])
        )

        self.assertContains(resposta, 'name="hero_image_en"')
