"""Diagnóstico do envio de email.

"O site parou de enviar emails" tem duas causas possíveis e muito diferentes:
ou o sistema não chega a produzir o email, ou produz e o servidor de correio
recusa. Sem separar as duas, procura-se no sítio errado.

Este comando mostra a configuração em uso e tenta um envio real, deixando o
erro do servidor de correio aparecer em vez de o engolir — que é o que o envio
normal faz de propósito, para uma falha de email não desfazer uma marcação.
"""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError

from notifications.models import EmailEventSetting, EmailTemplate, MessagingSetting


class Command(BaseCommand):
    help = "Mostra a configuração de email e envia uma mensagem de teste"

    def add_arguments(self, parser):
        parser.add_argument(
            "destinatario",
            nargs="?",
            help="Para onde enviar o teste. Sem isto, só mostra a configuração.",
        )

    def handle(self, *args, **options):
        self.mostrar_configuracao()
        self.mostrar_modelos()

        destinatario = options["destinatario"]

        if not destinatario:
            self.stdout.write(
                "\nIndique um endereço para tentar um envio a sério:\n"
                "  python manage.py send_test_email pessoa@exemplo.pt"
            )
            return

        self.enviar(destinatario)

    def mostrar_configuracao(self):
        backend = settings.EMAIL_BACKEND

        self.stdout.write(self.style.MIGRATE_HEADING("Configuração em uso"))
        self.stdout.write(f"  EMAIL_BACKEND      {backend}")
        self.stdout.write(f"  EMAIL_HOST         {settings.EMAIL_HOST or '(vazio)'}")
        self.stdout.write(f"  EMAIL_PORT         {settings.EMAIL_PORT}")
        self.stdout.write(f"  EMAIL_USE_TLS      {settings.EMAIL_USE_TLS}")
        self.stdout.write(f"  EMAIL_USE_SSL      {settings.EMAIL_USE_SSL}")
        self.stdout.write(
            f"  EMAIL_HOST_USER    {settings.EMAIL_HOST_USER or '(vazio)'}"
        )
        self.stdout.write(
            "  EMAIL_HOST_PASSWORD "
            + ("definida" if settings.EMAIL_HOST_PASSWORD else "(vazia)")
        )
        self.stdout.write(f"  DEFAULT_FROM_EMAIL {settings.DEFAULT_FROM_EMAIL}")

        if "console" in backend:
            self.stdout.write(
                self.style.WARNING(
                    "\n  Este backend escreve na consola e não envia nada. "
                    "Se isto for produção, está encontrado o problema."
                )
            )
        elif "locmem" in backend or "dummy" in backend:
            self.stdout.write(
                self.style.WARNING("\n  Este backend não envia nada para fora.")
            )
        elif not settings.EMAIL_HOST:
            self.stdout.write(
                self.style.ERROR(
                    "\n  EMAIL_HOST está vazio com um backend SMTP: o envio vai falhar."
                )
            )

    def mostrar_modelos(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\nRegras de envio"))

        regras = EmailEventSetting.objects.select_related("email_template")

        if not regras:
            self.stdout.write(
                self.style.WARNING("  Nenhuma regra configurada: não sai nada.")
            )
            return

        for regra in regras:
            estado = "ativa" if regra.is_active else "DESLIGADA"
            modelo = (
                regra.email_template.name
                if regra.email_template
                else "sem modelo (usa o texto de reserva)"
            )

            self.stdout.write(f"  {regra.event_type:<24} {estado:<10} {modelo}")

        self.stdout.write(f"\n  Modelos guardados: {EmailTemplate.objects.count()}")

    def enviar(self, destinatario):
        # Este comando monta o email à mão, sem passar pelo send_rendered_email,
        # por isso o interruptor tem de ser lido aqui também. Falhar em vez de
        # avisar seria pior: quem corre isto para diagnosticar o SMTP ficaria a
        # pensar que o problema era o servidor de correio.
        if not MessagingSetting.messaging_enabled():
            raise CommandError(
                "O envio de mensagens está desligado nas configurações do "
                "site. Ligue-o em Configurações → Envio de mensagens antes de "
                "testar o email."
            )

        self.stdout.write(
            self.style.MIGRATE_HEADING(f"\nA enviar para {destinatario}...")
        )

        mensagem = EmailMultiAlternatives(
            subject="Teste de envio — Priscila Arantes Pedicure Terapêutica",
            body=(
                "Se está a ler isto, o envio de email do site funciona.\n\n"
                "Mensagem gerada por: python manage.py send_test_email"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[destinatario],
        )

        try:
            # fail_silently=False de propósito: o objetivo aqui é ver o erro.
            enviados = mensagem.send(fail_silently=False)
        except Exception as erro:
            raise CommandError(
                f"O servidor de correio recusou: {type(erro).__name__}: {erro}"
            ) from erro

        if not enviados:
            raise CommandError(
                "O envio devolveu zero mensagens enviadas, sem levantar erro."
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Aceite pelo servidor de correio. Se não chegar à caixa de "
                "entrada, o problema passa a ser de entrega: confirme o spam, "
                "o SPF e o DKIM do domínio."
            )
        )
