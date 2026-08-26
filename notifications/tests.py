from datetime import time, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment, AppointmentReminderLog, Customer
from appointments.tests.factories import create_test_service, ensure_test_business_hour
from notifications.followup_services import eligible_appointments
from notifications.models import EmailTemplate, ServiceFollowUp


class FollowUpBase(TestCase):
    """Emails de cuidados posteriores, enviados uns dias depois do atendimento.

    O caso que motivou isto: o manual para os calos não voltarem, 15 dias
    depois da remoção.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.client.force_login(self.user)

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@example.com",
            phone="+351910000000",
        )

        self.service = create_test_service(duration_minutes=60)

        self.template = EmailTemplate.objects.create(
            key="cuidados_pos_calos",
            name="Cuidados depois da remoção de calos",
            subject="{{ customer_name }}, cuidados depois do seu {{ service_name }}",
            body_text="Olá {{ customer_name }}. Hidrate os pés todos os dias.",
        )

        self.followup = ServiceFollowUp.objects.create(
            service=self.service,
            email_template=self.template,
            days_after=15,
        )

        ensure_test_business_hour(
            weekday=0, start_time=time(9, 0), end_time=time(18, 0)
        )

    def marcacao(self, dias_atras, status=Appointment.STATUS_COMPLETED, customer=None):
        data = timezone.localdate() - timedelta(days=dias_atras)

        return Appointment.objects.create(
            customer=customer or self.customer,
            service=self.service,
            date=data,
            start_time=time(10, 0),
            status=status,
            created_by=self.user,
            # As datas passadas não passariam pela validação do horário; foram
            # marcações reais no seu tempo.
            outside_schedule=True,
        )

    def envelhecer_regra(self, dias):
        """Recua a criação da regra, que é auto_now_add."""

        ServiceFollowUp.objects.filter(pk=self.followup.pk).update(
            created_at=timezone.now() - timedelta(days=dias)
        )
        self.followup.refresh_from_db()


class EligibilityTests(FollowUpBase):
    def setUp(self):
        super().setUp()
        self.envelhecer_regra(365)

    def elegiveis(self, **kwargs):
        return list(eligible_appointments(self.followup, **kwargs))

    def test_an_appointment_at_the_configured_delay_is_picked_up(self):
        marcacao = self.marcacao(15)

        self.assertIn(marcacao, self.elegiveis())

    def test_an_appointment_that_has_not_reached_the_delay_is_not(self):
        self.marcacao(10)

        self.assertEqual(self.elegiveis(), [])

    def test_a_cancelled_appointment_is_left_out(self):
        # O atendimento não aconteceu; não há cuidados a dar a seguir.
        self.marcacao(15, status=Appointment.STATUS_CANCELLED)

        self.assertEqual(self.elegiveis(), [])

    def test_a_customer_without_email_is_left_out(self):
        sem_email = Customer.objects.create(
            full_name="Sem Email",
            phone="+351910000001",
        )

        self.marcacao(15, customer=sem_email)

        self.assertEqual(self.elegiveis(), [])

    def test_appointments_older_than_the_rule_are_left_out(self):
        # Ativar um seguimento hoje não pode despejar o email em cima de toda
        # a gente que fez o serviço no ano passado.
        self.envelhecer_regra(0)
        self.marcacao(15)

        self.assertEqual(self.elegiveis(), [])

    def test_a_long_overdue_appointment_is_left_out(self):
        # Instruções "15 dias depois" que chegam dois meses depois confundem
        # mais do que ajudam.
        self.marcacao(90)

        self.assertEqual(self.elegiveis(), [])

    def test_a_recently_overdue_appointment_is_still_sent(self):
        # Um dia sem o comando correr não pode perder o envio.
        marcacao = self.marcacao(17)

        self.assertIn(marcacao, self.elegiveis())

    def test_an_appointment_already_sent_is_left_out(self):
        marcacao = self.marcacao(15)

        AppointmentReminderLog.objects.create(
            appointment=marcacao,
            reminder_type=self.followup.get_log_key(),
            status=AppointmentReminderLog.STATUS_SUCCESS,
        )

        self.assertEqual(self.elegiveis(), [])

    def test_a_failed_attempt_is_tried_again(self):
        marcacao = self.marcacao(15)

        AppointmentReminderLog.objects.create(
            appointment=marcacao,
            reminder_type=self.followup.get_log_key(),
            status=AppointmentReminderLog.STATUS_ERROR,
            error_message="SMTP em baixo",
        )

        self.assertIn(marcacao, self.elegiveis())

    def test_another_service_is_not_affected(self):
        outro = create_test_service(name="Manicure", duration_minutes=60)

        Appointment.objects.create(
            customer=self.customer,
            service=outro,
            date=timezone.localdate() - timedelta(days=15),
            start_time=time(11, 0),
            status=Appointment.STATUS_COMPLETED,
            created_by=self.user,
            outside_schedule=True,
        )

        self.assertEqual(self.elegiveis(), [])

    def test_two_delays_on_the_same_service_do_not_collide(self):
        segundo = ServiceFollowUp.objects.create(
            service=self.service,
            email_template=self.template,
            days_after=30,
        )

        self.assertNotEqual(self.followup.get_log_key(), segundo.get_log_key())


class AutomaticSendingTests(FollowUpBase):
    def setUp(self):
        super().setUp()
        self.envelhecer_regra(365)

    def correr(self, **options):
        saida = StringIO()
        call_command("send_service_followups", stdout=saida, **options)
        return saida.getvalue()

    def test_the_email_goes_out(self):
        self.marcacao(15)

        self.correr()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["maria@example.com"])

    def test_the_email_uses_the_configured_template(self):
        self.marcacao(15)

        self.correr()

        self.assertEqual(
            mail.outbox[0].subject,
            "Maria Silva, cuidados depois do seu Podologia",
        )
        self.assertIn("Hidrate os pés", mail.outbox[0].body)

    def test_running_twice_does_not_send_twice(self):
        # O comando corre uma vez por dia, mas correr duas não pode duplicar.
        self.marcacao(15)

        self.correr()
        self.correr()

        self.assertEqual(len(mail.outbox), 1)

    def test_an_inactive_rule_sends_nothing(self):
        self.followup.is_active = False
        self.followup.save()

        self.marcacao(15)

        self.correr()

        self.assertEqual(len(mail.outbox), 0)

    def test_a_dry_run_sends_nothing(self):
        self.marcacao(15)

        saida = self.correr(dry_run=True)

        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("simulação", saida)

    def test_the_send_is_recorded(self):
        marcacao = self.marcacao(15)

        self.correr()

        self.assertTrue(
            AppointmentReminderLog.objects.filter(
                appointment=marcacao,
                reminder_type=self.followup.get_log_key(),
                status=AppointmentReminderLog.STATUS_SUCCESS,
            ).exists()
        )


class ManualSendingTests(FollowUpBase):
    def setUp(self):
        super().setUp()
        self.envelhecer_regra(365)
        self.appointment = self.marcacao(2)

    def url(self):
        return reverse(
            "notifications:appointment_followup_send",
            args=[self.appointment.pk, self.followup.pk],
        )

    def test_the_page_lists_the_service_follow_ups(self):
        resposta = self.client.get(
            reverse("notifications:appointment_followups", args=[self.appointment.pk])
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, self.template.name)

    def test_it_sends_before_the_configured_day(self):
        # O prazo serve o caso normal; isto serve a cliente que ligou a pedir
        # as instruções.
        self.client.post(self.url())

        self.assertEqual(len(mail.outbox), 1)

    def test_a_manual_send_stops_the_automatic_one(self):
        self.client.post(self.url())

        call_command("send_service_followups", stdout=StringIO())

        self.assertEqual(len(mail.outbox), 1)

    def test_it_can_be_sent_again(self):
        # Para o email que se perdeu.
        self.client.post(self.url())
        self.client.post(self.url())

        self.assertEqual(len(mail.outbox), 2)

    def test_an_inactive_rule_can_still_be_sent_by_hand(self):
        self.followup.is_active = False
        self.followup.save()

        self.client.post(self.url())

        self.assertEqual(len(mail.outbox), 1)

    def test_a_follow_up_from_another_service_is_refused(self):
        outro = create_test_service(name="Manicure", duration_minutes=60)
        alheio = ServiceFollowUp.objects.create(
            service=outro,
            email_template=self.template,
            days_after=5,
        )

        self.client.post(
            reverse(
                "notifications:appointment_followup_send",
                args=[self.appointment.pk, alheio.pk],
            )
        )

        self.assertEqual(len(mail.outbox), 0)

    def test_a_customer_without_email_is_refused(self):
        self.customer.email = ""
        self.customer.save()

        self.client.post(self.url())

        self.assertEqual(len(mail.outbox), 0)

    def test_a_failure_is_recorded_and_reported(self):
        self.template.is_active = False
        self.template.save()

        self.client.post(self.url())

        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(
            AppointmentReminderLog.objects.filter(
                appointment=self.appointment,
                status=AppointmentReminderLog.STATUS_ERROR,
            ).exists()
        )


class EmailTemplateAdminAreaTests(FollowUpBase):
    def test_the_list_shows_where_each_template_is_used(self):
        resposta = self.client.get(reverse("notifications:email_template_list"))

        self.assertContains(resposta, self.template.name)
        self.assertContains(resposta, self.service.name)

    def test_a_template_can_be_created(self):
        self.client.post(
            reverse("notifications:email_template_create"),
            data={
                "name": "Boas-vindas",
                "key": "Boas Vindas",
                "subject": "Olá {{ customer_name }}",
                "body_text": "Bem-vinda.",
                "body_html": "",
                "is_active": "on",
            },
        )

        criado = EmailTemplate.objects.get(name="Boas-vindas")

        # O identificador é normalizado: com espaços ou maiúsculas seria fácil
        # criar dois modelos que parecem o mesmo.
        self.assertEqual(criado.key, "boas_vindas")

    def test_broken_template_syntax_is_caught_before_saving(self):
        # Uma chaveta mal fechada só rebentaria na hora de enviar, com o email
        # já a caminho de ninguém.
        resposta = self.client.post(
            reverse("notifications:email_template_create"),
            data={
                "name": "Partido",
                "key": "partido",
                "subject": "Olá",
                "body_text": "{% if %}",
                "body_html": "",
                "is_active": "on",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(EmailTemplate.objects.filter(key="partido").exists())

    def test_the_preview_fills_in_the_variables(self):
        resposta = self.client.get(
            reverse("notifications:email_template_preview", args=[self.template.pk])
        )

        self.assertContains(resposta, "Maria Silva")
        self.assertNotContains(resposta, "customer_name")

    def test_a_template_in_use_cannot_be_deleted(self):
        # A base de dados recusaria com um ProtectedError cru.
        self.client.post(
            reverse("notifications:email_template_delete", args=[self.template.pk])
        )

        self.assertTrue(EmailTemplate.objects.filter(pk=self.template.pk).exists())

    def test_an_unused_template_can_be_deleted(self):
        solto = EmailTemplate.objects.create(
            key="solto", name="Solto", subject="a", body_text="b"
        )

        self.client.post(
            reverse("notifications:email_template_delete", args=[solto.pk])
        )

        self.assertFalse(EmailTemplate.objects.filter(pk=solto.pk).exists())

    def test_the_follow_up_form_only_offers_active_templates(self):
        inativo = EmailTemplate.objects.create(
            key="inativo", name="Inativo", subject="a", body_text="b", is_active=False
        )

        resposta = self.client.get(reverse("notifications:service_followup_create"))
        opcoes = resposta.context["form"].fields["email_template"].queryset

        self.assertIn(self.template, opcoes)
        self.assertNotIn(inativo, opcoes)

    def test_the_html_preview_is_drawn_and_not_shown_as_source(self):
        # O motor de templates devolve o HTML marcado como seguro, e assim ele
        # entrava cru no atributo `srcdoc` — que terminava nas primeiras aspas
        # do modelo. O resultado era um email meio desenhado e meio em pedaços.
        self.template.body_html = '<p style="color:red">Olá {{ customer_name }}</p>'
        self.template.save()

        resposta = self.client.get(
            reverse("notifications:email_template_preview", args=[self.template.pk])
        )
        pagina = resposta.content.decode()

        self.assertIn("&lt;p style=&quot;color:red&quot;&gt;", pagina)
        self.assertNotIn('srcdoc="<p', pagina)

        # E as variáveis continuam preenchidas lá dentro.
        self.assertIn("Maria Silva", pagina)

    def test_the_text_preview_shows_a_tag_instead_of_obeying_it(self):
        self.template.body_text = "Olá <b>Maria</b>"
        self.template.save()

        resposta = self.client.get(
            reverse("notifications:email_template_preview", args=[self.template.pk])
        )

        self.assertContains(resposta, "&lt;b&gt;Maria&lt;/b&gt;")

    def test_automatic_and_follow_up_templates_are_listed_apart(self):
        # Os nomes são parecidos e o que os separa não está no nome: um sai de
        # um acontecimento, o outro sai de um serviço. Juntos, editava-se o
        # que não era.
        automatico, _ = EmailTemplate.objects.get_or_create(
            key="appointment_created",
            defaults={
                "name": "Pedido recebido",
                "subject": "Olá",
                "body_text": "Recebemos o seu pedido.",
            },
        )

        resposta = self.client.get(reverse("notifications:email_template_list"))

        self.assertIn(automatico, resposta.context["automatic_templates"])
        self.assertNotIn(automatico, resposta.context["followup_templates"])

        self.assertIn(self.template, resposta.context["followup_templates"])
        self.assertNotIn(self.template, resposta.context["automatic_templates"])

    def test_the_per_service_messages_live_on_the_same_page(self):
        # Tinham ecrã próprio no menu. Um seguimento é um modelo mais um
        # serviço mais uma altura, e configurá-lo obrigava a saltar entre dois
        # menus para ver as duas metades da mesma coisa.
        resposta = self.client.get(reverse("notifications:email_template_list"))

        self.assertIn(self.followup, resposta.context["followups"])
        self.assertContains(resposta, "Mensagens por serviço")
        self.assertContains(resposta, reverse("notifications:service_followup_create"))

    def test_saving_a_follow_up_comes_back_to_the_templates(self):
        # O ecrã de onde se saiu deixou de existir.
        resposta = self.client.post(
            reverse("notifications:service_followup_create"),
            data={
                "service": self.service.pk,
                "email_template": self.template.pk,
                "trigger": ServiceFollowUp.TRIGGER_DELAYED,
                "days_after": 7,
                "is_active": "on",
            },
        )

        self.assertRedirects(resposta, reverse("notifications:email_template_list"))

    def test_an_empty_section_is_not_drawn(self):
        # Sem nenhum modelo ligado a um serviço, a secção de acompanhamento
        # não tem nada para mostrar — e uma secção sempre lá, vazia, só ensina
        # a passar os olhos por cima dela.
        self.followup.delete()

        resposta = self.client.get(reverse("notifications:email_template_list"))

        self.assertEqual(resposta.context["followup_templates"], [])
        self.assertNotContains(resposta, "Acompanhamento</h2>")

    def test_a_template_nothing_sends_yet_is_kept_to_one_side(self):
        # Escrito mas por ligar. Não é um envio automático nem um
        # acompanhamento: dizê-lo é mais útil do que escondê-lo numa das duas.
        rascunho = EmailTemplate.objects.create(
            key="rascunho", name="Rascunho", subject="a", body_text="b"
        )

        resposta = self.client.get(reverse("notifications:email_template_list"))

        self.assertIn(rascunho, resposta.context["unused_templates"])


class FollowUpAccessTests(TestCase):
    """Configuração de emails e envios são da área interna."""

    def setUp(self):
        self.customer_user = get_user_model().objects.create_user(
            email="cliente@example.com",
            password="StrongPassword123",
            full_name="Cliente",
        )

    def paginas(self):
        return [
            reverse("notifications:email_template_list"),
            reverse("notifications:email_template_create"),
            reverse("notifications:service_followup_create"),
        ]

    def test_anonymous_visitors_are_turned_away(self):
        for url in self.paginas():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)

    def test_customers_are_turned_away(self):
        self.client.force_login(self.customer_user)

        for url in self.paginas():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)


class DefaultEmailTemplatesTests(TestCase):
    """Modelos criados pela migração e ligados às regras de envio."""

    def catalogo(self):
        from notifications.default_email_templates import DEFAULT_EMAIL_TEMPLATES

        return DEFAULT_EMAIL_TEMPLATES

    def test_the_main_templates_exist(self):
        for entrada in self.catalogo():
            with self.subTest(chave=entrada["key"]):
                self.assertTrue(
                    EmailTemplate.objects.filter(key=entrada["key"]).exists()
                )

    def test_every_rule_points_at_a_template(self):
        from notifications.models import EmailEventSetting

        for regra in EmailEventSetting.objects.all():
            with self.subTest(regra=regra.event_type):
                self.assertIsNotNone(regra.email_template)

    def test_they_are_active(self):
        # O email já estava a sair com o texto de reserva; deixá-los
        # desligados trocaria um email simples por email nenhum.
        for entrada in self.catalogo():
            with self.subTest(chave=entrada["key"]):
                self.assertTrue(EmailTemplate.objects.get(key=entrada["key"]).is_active)

    def test_the_variables_are_ones_the_system_provides(self):
        import re

        from notifications.services import EmailTemplateService

        conhecidas = set(EmailTemplateService.get_sample_context())

        for modelo in EmailTemplate.objects.all():
            texto = f"{modelo.subject} {modelo.body_text} {modelo.body_html}"

            for nome in re.findall(r"\{\{\s*(\w+)\s*\}\}", texto):
                with self.subTest(modelo=modelo.key, variavel=nome):
                    self.assertIn(nome, conhecidas)

    def test_they_render_without_leaving_placeholders(self):
        from notifications.services import EmailTemplateService

        for modelo in EmailTemplate.objects.all():
            resultado = EmailTemplateService.render_template_object(
                email_template=modelo,
                context_data=EmailTemplateService.get_sample_context(),
            )

            with self.subTest(modelo=modelo.key):
                self.assertNotIn("{{", resultado["subject"])
                self.assertNotIn("{{", resultado["body_text"])
                self.assertNotIn("{{", resultado["body_html"])
                self.assertIn("Maria Silva", resultado["body_text"])

    def test_every_template_has_a_text_version(self):
        # Nem todos os clientes de email mostram HTML.
        for modelo in EmailTemplate.objects.all():
            with self.subTest(modelo=modelo.key):
                self.assertTrue(modelo.body_text.strip())


class ConfirmationEmailUsesTheTemplateTests(TestCase):
    """O email de confirmação passa a sair pelo modelo, não pelo texto fixo."""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@example.com",
            phone="+351910000000",
        )

        self.service = create_test_service(duration_minutes=60)

        self.date = timezone.localdate() + timedelta(days=7)
        while self.date.weekday() != 0:
            self.date += timedelta(days=1)

        ensure_test_business_hour(
            weekday=self.date.weekday(),
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

    def marcacao(self, status=Appointment.STATUS_SCHEDULED, origem=None):
        # A origem é explícita porque a confirmação depende dela: um pedido
        # feito no site e uma marcação combinada ao balcão têm textos
        # diferentes. Sem a dizer, o valor por omissão do modelo decidia por si.
        return Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=self.date,
            start_time=time(10, 0),
            status=status,
            created_by=self.user,
            origin=origem or Appointment.ORIGIN_PUBLIC,
        )

    def test_the_request_email_goes_out(self):
        from appointments.emails import send_appointment_confirmation_email

        send_appointment_confirmation_email(self.marcacao())

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Recebemos o seu pedido de marcação")

    def test_the_confirmation_email_goes_out(self):
        from appointments.emails import send_appointment_confirmation_email

        send_appointment_confirmation_email(
            self.marcacao(status=Appointment.STATUS_CONFIRMED)
        )

        self.assertIn("A sua marcação está confirmada", mail.outbox[0].subject)

    def test_an_appointment_arranged_at_the_clinic_is_told_apart(self):
        # A cliente não pediu nada: este email é a primeira vez que vê a data
        # escrita. Chamar-lhe "confirmação do seu pedido" seria responder a um
        # pedido que não existiu.
        from appointments.emails import send_appointment_confirmation_email

        send_appointment_confirmation_email(
            self.marcacao(
                status=Appointment.STATUS_CONFIRMED,
                origem=Appointment.ORIGIN_INTERNAL,
            )
        )

        self.assertIn("ficou registada", mail.outbox[0].subject)
        self.assertIn("combinámos", mail.outbox[0].body)

    def test_it_carries_an_html_alternative(self):
        from appointments.emails import send_appointment_confirmation_email

        send_appointment_confirmation_email(self.marcacao())

        alternativas = mail.outbox[0].alternatives

        self.assertEqual(len(alternativas), 1)
        self.assertEqual(alternativas[0][1], "text/html")
        self.assertIn("Maria Silva", alternativas[0][0])

    def test_the_customer_details_are_filled_in(self):
        from appointments.emails import send_appointment_confirmation_email

        send_appointment_confirmation_email(self.marcacao())

        corpo = mail.outbox[0].body

        self.assertIn("Maria Silva", corpo)
        self.assertIn(self.service.name, corpo)
        self.assertIn(self.date.strftime("%d/%m/%Y"), corpo)
        self.assertNotIn("{{", corpo)

    def test_deactivating_the_template_falls_back_instead_of_going_silent(self):
        # Um modelo desligado não pode calar o email de confirmação: o cliente
        # ficaria sem saber que a marcação existe.
        from appointments.emails import send_appointment_confirmation_email

        EmailTemplate.objects.filter(key="appointment_created").update(is_active=False)

        send_appointment_confirmation_email(self.marcacao())

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Maria Silva", mail.outbox[0].body)
