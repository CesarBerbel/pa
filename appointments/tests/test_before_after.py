"""Os casos antes e depois: o que se carrega na área interna e o que se vê no site."""

import os
import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from notifications.models import BeforeAfterCase

MEDIA_DE_TESTE = tempfile.mkdtemp(prefix="pa-antes-depois-")


def imagem(nome, cor):
    """Um JPEG a sério, pequeno. O `ImageField` valida o conteúdo, portanto um
    ficheiro com bytes inventados seria recusado e o teste não provaria nada."""

    ficheiro = BytesIO()
    Image.new("RGB", (12, 9), cor).save(ficheiro, format="JPEG")

    return SimpleUploadedFile(nome, ficheiro.getvalue(), content_type="image/jpeg")


@override_settings(MEDIA_ROOT=MEDIA_DE_TESTE)
class BeforeAfterInternalTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        # As imagens escritas ficam num sítio temporário e saem com ele: sem
        # isto, cada execução deixava ficheiros na pasta `media/` do projeto.
        shutil.rmtree(MEDIA_DE_TESTE, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        User = get_user_model()
        self.profissional = User.objects.create_superuser(
            email="admin@test.com",
            password="testpass123",
            full_name="Admin",
        )
        self.cliente = User.objects.create_user(
            email="cliente@test.com",
            password="testpass123",
            full_name="Cliente",
        )

    def entrar(self):
        self.client.login(email="admin@test.com", password="testpass123")

    def dados(self):
        return {
            "title": "Unha encravada",
            "caption": "Duas semanas entre uma fotografia e a outra.",
            "before_image": imagem("antes.jpg", "red"),
            "after_image": imagem("depois.jpg", "green"),
            "display_order": 0,
            "is_active": "on",
        }

    def test_the_professional_can_create_a_case_with_both_photos(self):
        self.entrar()

        resposta = self.client.post(
            reverse("appointments:before_after_create"), data=self.dados()
        )

        self.assertRedirects(resposta, reverse("appointments:before_after_list"))

        caso = BeforeAfterCase.objects.get()
        self.assertEqual(caso.title, "Unha encravada")
        self.assertTrue(caso.before_image.name)
        self.assertTrue(caso.after_image.name)
        self.assertEqual(caso.caption, "Duas semanas entre uma fotografia e a outra.")

    def test_a_case_needs_both_photos(self):
        # Uma comparação com uma fotografia só não é uma comparação.
        self.entrar()
        dados = self.dados()
        del dados["after_image"]

        resposta = self.client.post(
            reverse("appointments:before_after_create"), data=dados
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(BeforeAfterCase.objects.exists())

    def test_editing_the_caption_does_not_ask_for_the_photos_again(self):
        # Ao editar, as fotografias já estão guardadas: obrigar a carregá-las
        # outra vez para mudar uma palavra seria trabalho por nada.
        self.entrar()
        self.client.post(reverse("appointments:before_after_create"), data=self.dados())
        caso = BeforeAfterCase.objects.get()
        antes = caso.before_image.name

        resposta = self.client.post(
            reverse("appointments:before_after_update", args=[caso.pk]),
            data={
                "title": "Unha encravada — resolvido",
                "caption": "Duas semanas entre uma fotografia e a outra.",
                "display_order": 0,
                "is_active": "on",
            },
        )

        self.assertRedirects(resposta, reverse("appointments:before_after_list"))

        caso.refresh_from_db()
        self.assertEqual(caso.title, "Unha encravada — resolvido")
        self.assertEqual(caso.before_image.name, antes)

    def test_deleting_a_case_removes_the_photos_from_disk(self):
        # Sem isto os ficheiros ficavam no servidor para sempre, sem nada que
        # lhes chegasse — e são imagens de pessoas.
        self.entrar()
        self.client.post(reverse("appointments:before_after_create"), data=self.dados())
        caso = BeforeAfterCase.objects.get()
        guardadas = [caso.before_image.path, caso.after_image.path]

        self.client.post(reverse("appointments:before_after_delete", args=[caso.pk]))

        self.assertFalse(BeforeAfterCase.objects.exists())

        for caminho in guardadas:
            with self.subTest(caminho):
                self.assertFalse(os.path.exists(caminho))

    def test_a_client_cannot_reach_the_management_pages(self):
        self.client.login(email="cliente@test.com", password="testpass123")

        for nome in ("before_after_list", "before_after_create"):
            with self.subTest(nome):
                resposta = self.client.get(reverse(f"appointments:{nome}"))
                self.assertNotEqual(resposta.status_code, 200)


@override_settings(MEDIA_ROOT=MEDIA_DE_TESTE)
class BeforeAfterPublicPageTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_DE_TESTE, ignore_errors=True)
        super().tearDownClass()

    def criar(self, **campos):
        valores = {
            "title": "Unha encravada",
            "caption": "Duas semanas entre uma fotografia e a outra.",
            "before_image": imagem("antes.jpg", "red"),
            "after_image": imagem("depois.jpg", "green"),
        }
        valores.update(campos)

        return BeforeAfterCase.objects.create(**valores)

    def test_the_page_shows_a_case_with_its_title_and_caption(self):
        self.criar()

        html = self.client.get(
            reverse("appointments:public_before_after")
        ).content.decode()

        self.assertIn("Unha encravada", html)
        self.assertIn("Duas semanas entre uma fotografia e a outra.", html)

    def test_both_photos_share_one_box_with_a_control_to_drag(self):
        # É isto que faz a comparação: as duas no mesmo sítio e uma linha que
        # se arrasta. Sem o controlo, a de cima taparia a outra para sempre.
        self.criar()

        html = self.client.get(
            reverse("appointments:public_before_after")
        ).content.decode()

        self.assertIn('class="ba-compare"', html)
        self.assertIn('class="ba-frame ba-frame-before"', html)
        self.assertIn('class="ba-frame ba-frame-after"', html)
        self.assertIn('type="range"', html)

    def test_a_hidden_case_does_not_reach_the_site(self):
        self.criar(is_active=False)

        html = self.client.get(
            reverse("appointments:public_before_after")
        ).content.decode()

        self.assertNotIn("Unha encravada", html)

    def test_the_page_works_with_nothing_published(self):
        resposta = self.client.get(reverse("appointments:public_before_after"))

        self.assertEqual(resposta.status_code, 200)

    def test_the_photos_are_served(self):
        # O `static()` de antes não fazia nada com DEBUG=False e as imagens
        # dariam 404 em produção.
        caso = self.criar()

        with override_settings(DEBUG=False):
            resposta = self.client.get(caso.before_image.url)

        self.assertEqual(resposta.status_code, 200)


@override_settings(MEDIA_ROOT=MEDIA_DE_TESTE)
class BeforeAfterPaginationTests(TestCase):
    """Quatro de cada vez. Cada caso são duas imagens: a página inteira de uma
    só vez seria lenta a abrir e cara em dados móveis."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_DE_TESTE, ignore_errors=True)
        super().tearDownClass()

    def criar(self, quantos):
        for numero in range(quantos):
            BeforeAfterCase.objects.create(
                title=f"Caso {numero}",
                before_image=imagem(f"antes-{numero}.jpg", "red"),
                after_image=imagem(f"depois-{numero}.jpg", "green"),
                display_order=numero,
            )

    def pedir(self, **parametros):
        return self.client.get(reverse("appointments:public_before_after"), parametros)

    def test_only_four_come_in_the_first_page(self):
        self.criar(9)

        resposta = self.pedir()

        self.assertEqual(len(resposta.context["cases"]), 4)
        self.assertNotContains(resposta, "Caso 4")

    def test_the_link_appears_only_when_there_is_more(self):
        self.criar(4)

        self.assertFalse(self.pedir().context["has_more"])

        self.criar(1)

        self.assertTrue(self.pedir().context["has_more"])

    def test_the_link_asks_for_four_more(self):
        self.criar(9)

        resposta = self.pedir()

        self.assertEqual(resposta.context["next_amount"], 8)
        self.assertContains(resposta, "?mostrar=8")

    def test_following_the_link_keeps_the_ones_already_shown(self):
        # Acumulativo e não "os quatro seguintes": sem JavaScript, seguir a
        # ligação não pode fazer desaparecer o que a pessoa estava a ver.
        self.criar(9)

        resposta = self.pedir(mostrar=12)

        self.assertEqual(len(resposta.context["cases"]), 9)
        self.assertContains(resposta, "Caso 0")
        self.assertContains(resposta, "Caso 8")
        self.assertFalse(resposta.context["has_more"])

    def test_a_made_up_amount_does_not_break_the_page(self):
        # O número vem do URL, portanto vem de qualquer pessoa.
        self.criar(9)

        for valor in ("-1", "0", "abc", "999999", ""):
            with self.subTest(valor):
                resposta = self.pedir(mostrar=valor)

                self.assertEqual(resposta.status_code, 200)
                self.assertLessEqual(len(resposta.context["cases"]), 9)
                self.assertGreaterEqual(len(resposta.context["cases"]), 4)


@override_settings(MEDIA_ROOT=MEDIA_DE_TESTE)
class BeforeAfterImageResizingTests(TestCase):
    """O que acontece à fotografia entre o carregamento e o disco."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_DE_TESTE, ignore_errors=True)
        super().tearDownClass()

    def grande(self, nome="foto.jpg", tamanho=(3200, 2400), formato="JPEG", **extra):
        ficheiro = BytesIO()
        Image.new("RGB", tamanho, "red").save(ficheiro, format=formato, **extra)

        return SimpleUploadedFile(nome, ficheiro.getvalue())

    def caso(self, **campos):
        valores = {
            "title": "Caso",
            "before_image": self.grande("antes.jpg"),
            "after_image": self.grande("depois.jpg"),
        }
        valores.update(campos)

        return BeforeAfterCase.objects.create(**valores)

    def test_a_phone_sized_photo_is_shrunk(self):
        caso = self.caso()

        with Image.open(caso.before_image.path) as guardada:
            self.assertEqual(max(guardada.size), 1200)

    def test_it_weighs_a_fraction_of_what_came_in(self):
        # É este o motivo de tudo isto: o que sai para quem visita o site.
        original = self.grande("antes.jpg")
        tamanho_original = original.size

        caso = BeforeAfterCase.objects.create(
            title="Caso",
            before_image=original,
            after_image=self.grande("depois.jpg"),
        )

        self.assertLess(caso.before_image.size, tamanho_original / 2)

    def test_a_small_photo_is_not_blown_up(self):
        # Encolher é para encolher. Esticar uma imagem pequena só a desfoca.
        caso = self.caso(before_image=self.grande("antes.jpg", tamanho=(300, 200)))

        with Image.open(caso.before_image.path) as guardada:
            self.assertEqual(guardada.size, (300, 200))

    def test_a_png_becomes_a_jpeg_without_turning_black(self):
        # Um PNG com transparência ficava com fundo preto ao virar JPEG.
        caso = self.caso(before_image=self.grande("antes.png", formato="PNG"))

        self.assertTrue(caso.before_image.name.endswith(".jpg"))

        with Image.open(caso.before_image.path) as guardada:
            self.assertEqual(guardada.format, "JPEG")

    def test_the_location_and_the_rest_of_the_metadata_do_not_survive(self):
        # São fotografias de pacientes: as coordenadas de onde foram tiradas
        # não podem ir para o site agarradas à imagem.
        with_exif = Image.new("RGB", (2000, 1500), "red")
        exif = with_exif.getexif()
        exif[271] = "ACME"  # fabricante do equipamento
        ficheiro = BytesIO()
        with_exif.save(ficheiro, format="JPEG", exif=exif)

        caso = self.caso(
            before_image=SimpleUploadedFile("antes.jpg", ficheiro.getvalue())
        )

        with Image.open(caso.before_image.path) as guardada:
            self.assertNotIn(271, guardada.getexif())

    def test_saving_the_record_again_does_not_touch_the_photo(self):
        # Recomprimir a cada gravação — mudar uma legenda, por exemplo — ia
        # degradando a imagem sem nada a ganhar.
        caso = self.caso()
        antes = (caso.before_image.name, caso.before_image.size)

        caso.title = "Outro título"
        caso.save()
        caso.refresh_from_db()

        self.assertEqual((caso.before_image.name, caso.before_image.size), antes)


@override_settings(MEDIA_ROOT=MEDIA_DE_TESTE)
class BeforeAfterMenuEntryTests(TestCase):
    """A entrada de menu existe quando há o que mostrar, e não antes."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_DE_TESTE, ignore_errors=True)
        super().tearDownClass()

    def criar(self, **campos):
        valores = {
            "title": "Unha encravada",
            "before_image": imagem("antes.jpg", "red"),
            "after_image": imagem("depois.jpg", "green"),
        }
        valores.update(campos)

        return BeforeAfterCase.objects.create(**valores)

    def ligacoes(self):
        html = self.client.get(reverse("home")).content.decode()

        return html.count(reverse("appointments:public_before_after"))

    def test_without_any_case_the_menu_does_not_offer_the_page(self):
        # Um menu que leva a uma página vazia ensina as pessoas a não clicar
        # no menu.
        self.assertEqual(self.ligacoes(), 0)

    def test_one_case_is_enough_to_show_it(self):
        self.criar()

        # Três sítios: o menu, o rodapé e a chamada na própria página inicial.
        self.assertEqual(self.ligacoes(), 3)

    def test_a_hidden_case_does_not_count(self):
        # Esconder o único caso deixa a página vazia: a entrada sai com ele.
        self.criar(is_active=False)

        self.assertEqual(self.ligacoes(), 0)

    def test_the_page_itself_stays_reachable(self):
        # A ligação some do menu; o endereço continua a responder, para não
        # partir o que já esteja guardado nos favoritos ou indexado.
        self.assertEqual(
            self.client.get(reverse("appointments:public_before_after")).status_code,
            200,
        )


@override_settings(MEDIA_ROOT=MEDIA_DE_TESTE)
class BeforeAfterFramingTests(TestCase):
    """Aproximar e reposicionar cada fotografia dentro da caixa."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_DE_TESTE, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        User = get_user_model()
        User.objects.create_superuser(
            email="admin@test.com", password="testpass123", full_name="Admin"
        )
        self.client.login(email="admin@test.com", password="testpass123")

    def criar(self, **campos):
        valores = {
            "title": "Caso",
            "before_image": imagem("antes.jpg", "red"),
            "after_image": imagem("depois.jpg", "green"),
        }
        valores.update(campos)

        return BeforeAfterCase.objects.create(**valores)

    def test_a_new_case_shows_the_whole_photo_centred(self):
        # O enquadramento por omissão não pode cortar nada: quem não mexer no
        # editor tem de ficar com a fotografia como a carregou.
        caso = self.criar()

        self.assertEqual(caso.before_zoom, 100)
        self.assertEqual(caso.before_focus_x, 50)
        self.assertEqual(caso.before_focus_y, 50)

    def test_the_framing_reaches_the_public_page_as_css(self):
        caso = self.criar(before_zoom=180, before_focus_x=30, before_focus_y=20)

        html = self.client.get(
            reverse("appointments:public_before_after")
        ).content.decode()

        self.assertIn("--ba-zoom: 1.8;", html)
        self.assertIn("--ba-x: 30%;", html)
        self.assertIn("--ba-y: 20%;", html)

    def test_each_side_is_framed_on_its_own(self):
        # Duas fotografias tiradas a distâncias diferentes só se alinham se
        # cada uma puder ser ajustada à parte.
        caso = self.criar(before_zoom=150, after_zoom=220)

        self.assertEqual(caso.framing("before")["zoom"], 1.5)
        self.assertEqual(caso.framing("after")["zoom"], 2.2)

    def test_the_line_is_clipped_on_the_frame_and_not_on_the_photo(self):
        # A aproximação é uma transformação da imagem. Se o recorte da linha
        # vivesse na própria imagem, seria transformado com ela e a linha
        # deixava de coincidir com o que se vê.
        self.criar(before_zoom=200)

        html = self.client.get(
            reverse("appointments:public_before_after")
        ).content.decode()

        moldura = html[html.index('class="ba-frame ba-frame-before"') :][:400]

        self.assertIn("--ba-zoom: 2.0;", moldura)
        self.assertNotIn("clip-path", moldura)

    def test_the_form_offers_an_editor_for_each_side(self):
        caso = self.criar()

        html = self.client.get(
            reverse("appointments:before_after_update", args=[caso.pk])
        ).content.decode()

        # `data-ba-editor` aparece também no JavaScript que os procura; o
        # que conta são os dois blocos de marcação.
        self.assertEqual(html.count('data-ba-editor data-side='), 2)
        self.assertIn('data-side="before"', html)
        self.assertIn('data-side="after"', html)
        self.assertIn('id="id_before_zoom"', html)

    def test_saving_without_the_hidden_fields_keeps_the_defaults(self):
        # Um formulário submetido sem eles é um enquadramento por decidir, e
        # não um erro que impeça de guardar o caso.
        resposta = self.client.post(
            reverse("appointments:before_after_create"),
            data={
                "title": "Sem enquadramento",
                "before_image": imagem("antes.jpg", "red"),
                "after_image": imagem("depois.jpg", "green"),
                "display_order": 0,
                "is_active": "on",
            },
        )

        self.assertRedirects(resposta, reverse("appointments:before_after_list"))

        caso = BeforeAfterCase.objects.get(title="Sem enquadramento")

        self.assertEqual(caso.before_zoom, 100)
        self.assertEqual(caso.after_focus_y, 50)

    def test_an_impossible_zoom_is_refused(self):
        # O valor vem de um campo escondido, portanto vem de qualquer pessoa.
        caso = self.criar()

        resposta = self.client.post(
            reverse("appointments:before_after_update", args=[caso.pk]),
            data={
                "title": "Caso",
                "display_order": 0,
                "is_active": "on",
                "before_zoom": 9000,
                "before_focus_x": 50,
                "before_focus_y": 50,
                "after_zoom": 100,
                "after_focus_x": 50,
                "after_focus_y": 50,
            },
        )

        self.assertEqual(resposta.status_code, 200)

        caso.refresh_from_db()
        self.assertEqual(caso.before_zoom, 100)
