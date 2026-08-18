"""A lista de marcações como cartões, e o ecrã de detalhe que a completa.

A lista deixou de ser uma tabela com botões por linha: passou a mostrar
cartões agrupados por dia, e cada cartão é apenas uma ligação. O que estes
testes guardam é o par — a lista sem ações, e o detalhe onde elas passaram a
viver. Separar as duas coisas sem garantir a segunda deixaria a marcação
visível e intocável.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment, Customer
from appointments.tests.factories import create_test_service, ensure_test_business_hour


class CardsBase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.maria = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@example.com",
            phone="+351910000000",
        )

        self.ana = Customer.objects.create(
            full_name="Ana Costa",
            email="ana@example.com",
            phone="+351910000001",
        )

        self.service = create_test_service(duration_minutes=60)

        for dia in range(0, 7):
            ensure_test_business_hour(
                weekday=dia, start_time=time(8, 0), end_time=time(20, 0)
            )

        self.hoje = timezone.localdate()
        self.amanha = self.hoje + timedelta(days=1)

        self.manha = self.marcar(self.maria, self.hoje, time(9, 0))
        self.tarde = self.marcar(self.ana, self.hoje, time(15, 0))
        self.seguinte = self.marcar(self.maria, self.amanha, time(10, 0))

        self.client.force_login(self.user)
        self.url = reverse("appointments:appointment_list")

    def marcar(self, cliente, data, hora, status=Appointment.STATUS_SCHEDULED):
        marcacao = Appointment(
            customer=cliente,
            service=self.service,
            date=data,
            start_time=hora,
            status=status,
            created_by=self.user,
        )

        marcacao.reference_code = marcacao.generate_reference_code()
        super(Appointment, marcacao).save()

        return marcacao


class DayGroupingTests(CardsBase):
    def test_each_day_becomes_one_group(self):
        dias = self.client.get(self.url).context["appointment_days"]

        self.assertEqual([grupo["date"] for grupo in dias], [self.hoje, self.amanha])

    def test_a_day_keeps_all_of_its_appointments(self):
        dias = self.client.get(self.url).context["appointment_days"]

        self.assertEqual(dias[0]["appointments"], [self.manha, self.tarde])

    def test_ordering_by_customer_does_not_split_a_day_in_two(self):
        # `regroup` só junta linhas seguidas. Ordenada por cliente, a manhã da
        # Maria e a tarde da Ana ficam separadas na consulta, e o mesmo dia
        # aparecia duas vezes no ecrã.
        dias = self.client.get(self.url, {"ordering": "customer_asc"})

        datas = [grupo["date"] for grupo in dias.context["appointment_days"]]

        self.assertEqual(len(datas), len(set(datas)))


class ListWithoutActionsTests(CardsBase):
    def test_the_list_carries_no_action_buttons(self):
        pagina = self.client.get(self.url).content.decode()

        for acao in (
            "appointment_confirm",
            "appointment_complete",
            "appointment_cancel",
        ):
            self.assertNotIn(
                reverse(f"appointments:{acao}", kwargs={"pk": self.manha.pk}),
                pagina,
            )

    def test_each_card_links_to_its_own_detail(self):
        pagina = self.client.get(self.url).content.decode()

        for marcacao in (self.manha, self.tarde, self.seguinte):
            self.assertIn(
                reverse("appointments:appointment_detail", kwargs={"pk": marcacao.pk}),
                pagina,
            )

    def test_a_card_shows_what_it_promises(self):
        pagina = self.client.get(self.url).content.decode()

        self.assertIn("Maria Silva", pagina)
        self.assertIn(self.service.name, pagina)
        self.assertIn("Agendado", pagina)
        self.assertIn(self.manha.date.strftime("%d/%m/%Y"), pagina)
        self.assertIn("09:00", pagina)

    def test_the_card_keeps_the_filters_for_the_way_back(self):
        # Sem isto, abrir uma marcação encontrada numa pesquisa e voltar
        # atrás devolvia a lista ao estado inicial.
        resposta = self.client.get(self.url, {"q": self.manha.reference_code})

        detalhe = reverse(
            "appointments:appointment_detail", kwargs={"pk": self.manha.pk}
        )

        self.assertIn(f"{detalhe}?q=", resposta.content.decode())


class DetailPageTests(CardsBase):
    def detalhe(self, marcacao):
        return self.client.get(
            reverse("appointments:appointment_detail", kwargs={"pk": marcacao.pk})
        )

    def test_it_shows_the_appointment_in_full(self):
        pagina = self.detalhe(self.manha).content.decode()

        self.assertIn(self.manha.reference_code, pagina)
        self.assertIn("Maria Silva", pagina)
        self.assertIn("maria@example.com", pagina)
        self.assertIn("+351910000000", pagina)
        self.assertIn(self.service.name, pagina)
        self.assertIn("09:00", pagina)
        self.assertIn("Agendado", pagina)

    def test_a_scheduled_appointment_offers_confirm_edit_and_cancel(self):
        pagina = self.detalhe(self.manha).content.decode()

        for acao in ("appointment_confirm", "appointment_update", "appointment_cancel"):
            self.assertIn(
                reverse(f"appointments:{acao}", kwargs={"pk": self.manha.pk}),
                pagina,
            )

    def test_a_confirmed_appointment_offers_completing_it(self):
        self.manha.status = Appointment.STATUS_CONFIRMED
        self.manha.save(update_fields=["status"])

        pagina = self.detalhe(self.manha).content.decode()

        self.assertIn(
            reverse("appointments:appointment_complete", kwargs={"pk": self.manha.pk}),
            pagina,
        )

    def test_a_completed_appointment_offers_neither_editing_nor_cancelling(self):
        self.manha.status = Appointment.STATUS_COMPLETED
        self.manha.save(update_fields=["status"])

        pagina = self.detalhe(self.manha).content.decode()

        for acao in ("appointment_update", "appointment_cancel"):
            self.assertNotIn(
                reverse(f"appointments:{acao}", kwargs={"pk": self.manha.pk}),
                pagina,
            )

    def test_a_cancelled_appointment_says_why(self):
        self.manha.status = Appointment.STATUS_CANCELLED
        self.manha.cancellation_reason = "A cliente adoeceu."
        self.manha.cancelled_at = timezone.now()
        self.manha.save(update_fields=["status", "cancellation_reason", "cancelled_at"])

        pagina = self.detalhe(self.manha).content.decode()

        self.assertIn("A cliente adoeceu.", pagina)

    def test_it_is_closed_to_who_is_not_from_the_internal_area(self):
        # A marcação diz o nome, o telefone e o email da cliente. O detalhe
        # tem de estar atrás da mesma porta que a lista de onde saiu.
        self.client.logout()

        resposta = self.detalhe(self.manha)

        self.assertEqual(resposta.status_code, 302)


class WhatsAppLinkTests(CardsBase):
    """O telefone da cliente abre a conversa, não o marcador de chamadas.

    O contacto com as clientes faz-se por WhatsApp. Um `tel:` obrigava a
    copiar o número e a procurá-lo à mão do outro lado.
    """

    def test_the_phone_opens_the_conversation(self):
        pagina = self.client.get(
            reverse("appointments:appointment_detail", kwargs={"pk": self.manha.pk})
        ).content.decode()

        self.assertIn("https://wa.me/351910000000", pagina)

    def test_it_does_not_dial_anymore(self):
        pagina = self.client.get(
            reverse("appointments:appointment_detail", kwargs={"pk": self.manha.pk})
        ).content.decode()

        self.assertNotIn(f"tel:{self.maria.phone}", pagina)

    def test_the_number_is_still_readable(self):
        # A ligação é para carregar; o número é para ler em voz alta a quem
        # pergunta. Um sem o outro obrigava a abrir o WhatsApp para o saber.
        pagina = self.client.get(
            reverse("appointments:appointment_detail", kwargs={"pk": self.manha.pk})
        ).content.decode()

        self.assertIn(self.maria.phone, pagina)


class CustomerWhatsAppUrlTests(TestCase):
    def cliente(self, phone):
        return Customer(full_name="Maria Silva", phone=phone)

    def test_it_drops_the_plus_sign(self):
        # O wa.me responde com uma página de erro a um número com `+`, e o
        # número continua a parecer certo a quem carregou.
        self.assertEqual(
            self.cliente("+351910000000").whatsapp_url,
            "https://wa.me/351910000000",
        )

    def test_it_drops_spaces_and_punctuation(self):
        self.assertEqual(
            self.cliente("+55 (11) 91234-5678").whatsapp_url,
            "https://wa.me/5511912345678",
        )

    def test_a_number_without_digits_gives_no_link(self):
        # Melhor não oferecer ligação nenhuma do que uma que abre o wa.me
        # vazio, como se o contacto estivesse a funcionar.
        self.assertEqual(self.cliente("sem número").whatsapp_url, "")

    def test_an_empty_phone_gives_no_link(self):
        self.assertEqual(self.cliente("").whatsapp_url, "")
