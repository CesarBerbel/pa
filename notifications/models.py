import logging
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from notifications.images import resize_uploaded_image

logger = logging.getLogger(__name__)


class EmailTemplate(models.Model):
    # Stores customizable email templates editable via admin.

    key = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Identificador",
        help_text="Identificador interno, sem espaços. Exemplo: appointment_cancelled",
    )

    name = models.CharField(
        max_length=150,
        verbose_name="Nome",
        help_text="Nome legível, para identificar o modelo nas listas.",
    )

    subject = models.CharField(
        max_length=255,
        verbose_name="Assunto",
    )

    body_text = models.TextField(verbose_name="Texto")

    body_html = models.TextField(
        blank=True,
        verbose_name="HTML (opcional)",
        help_text="Versão em HTML do email. Vazio envia só o texto acima.",
    )

    # A versão inglesa, para quem marcou na versão inglesa do site. Vazia
    # significa "não traduzido": envia-se o português, que é melhor do que
    # não enviar nada. Os avisos à profissional não têm versão inglesa
    # nenhuma — quem os lê fala português.
    subject_en = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Assunto (inglês)",
    )

    body_text_en = models.TextField(
        blank=True,
        verbose_name="Texto (inglês)",
    )

    body_html_en = models.TextField(
        blank=True,
        verbose_name="HTML (inglês)",
    )

    # Quantas horas antes da marcação sai esta mensagem.
    #
    # Só o lembrete é enviado a contar do relógio, e por isso só nele é que
    # este número tem efeito — o formulário nem sequer o mostra nos outros.
    # Fica no modelo, ao pé do texto, porque é a mesma decisão: o que se diz e
    # quando se diz. Vinte e quatro horas dão tempo de desmarcar e libertar a
    # vaga; duas horas servem para quem já se esqueceu de que ia sair de casa.
    reminder_hours_before = models.PositiveIntegerField(
        default=24,
        verbose_name="Antecedência (horas)",
        help_text=(
            "Quantas horas antes da marcação sai o lembrete. Zero desliga-o. "
            "Só tem efeito no modelo do lembrete."
        ),
    )

    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # A chave do modelo que o comando dos lembretes usa.
    REMINDER_KEY = "appointment_reminder"

    # Para que serve um modelo. Não é um campo: é uma leitura do que está
    # ligado a ele, e por isso não pode ficar a dizer o contrário da verdade.
    USE_AUTOMATIC = "automatic"
    USE_FOLLOWUP = "followup"
    USE_UNUSED = "unused"

    # As chaves que os envios automáticos pedem pelo nome, quando a regra do
    # acontecimento não aponta para modelo nenhum. Não se derivam das escolhas
    # de EmailEventSetting: três delas não são acontecimentos à parte — são o
    # mesmo acontecimento visto do lado da profissional, ou a confirmação de
    # uma marcação combinada ao balcão.
    AUTOMATIC_KEYS = frozenset(
        {
            "appointment_created",
            "appointment_created_professional",
            "appointment_confirmed",
            "appointment_confirmed_internal",
            "appointment_cancelled",
            "appointment_cancelled_professional",
            "appointment_completed",
            "appointment_reminder",
            "return_due",
        }
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Modelo de email"
        verbose_name_plural = "Modelos de email"

    def for_language(self, language):
        """O assunto e o corpo na língua pedida, com o português como recurso.

        Um campo inglês vazio não é um email vazio: é um email por traduzir, e
        aí vale mais o português. Isto vale campo a campo, para uma tradução
        feita a meio não deixar o assunto numa língua e o corpo noutra.
        """

        ingles = (language or "").lower().startswith("en")

        if not ingles:
            return {
                "subject": self.subject,
                "body_text": self.body_text,
                "body_html": self.body_html,
            }

        return {
            "subject": self.subject_en or self.subject,
            "body_text": self.body_text_en or self.body_text,
            "body_html": self.body_html_en or self.body_html,
        }

    def usage(self):
        """Para que serve este modelo: envio automático ou acompanhamento.

        São duas famílias que só se parecem por serem ambas emails. Um envio
        automático sai de um acontecimento — a marcação foi criada, a hora
        está a chegar — e o texto dele é do sistema. Um acompanhamento sai de
        um serviço, dias depois, e o texto é da profissional.

        Misturados na mesma lista, editava-se o errado: os nomes são
        parecidos, e a diferença entre eles não está no nome, está em quem os
        manda.

        Lê-se pelas relações e não por um campo escolhido à mão, para não
        haver um modelo marcado como acompanhamento a sair, todos os dias, de
        um acontecimento. O `.all()` é de propósito: com o prefetch da lista
        não custa consulta nenhuma, ao contrário de um `.exists()`.
        """

        if self.key in self.AUTOMATIC_KEYS or self.event_settings.all():
            return self.USE_AUTOMATIC

        if self.follow_ups.all():
            return self.USE_FOLLOWUP

        return self.USE_UNUSED

    def __str__(self):
        return self.name

    @classmethod
    def reminder_hours(cls):
        """Horas de antecedência do lembrete. Zero é não enviar.

        Lê sem escrever: isto é consultado por um comando que corre de meia em
        meia hora, e um comando que grava a cada passagem sujava o histórico
        sem razão nenhuma.

        Sem o modelo — apagado, ou uma base ainda por semear — devolve zero, e
        o comando não envia nada: sem texto não há mensagem para mandar.
        """

        try:
            modelo = cls.objects.filter(key=cls.REMINDER_KEY).first()

            return modelo.reminder_hours_before if modelo else 0
        except Exception:
            logger.exception("Não foi possível ler a antecedência do lembrete.")

            return 0


class EmailEventSetting(models.Model):
    # Controls which appointment events send emails and which template each event uses.

    EVENT_APPOINTMENT_CREATED = "appointment_created"
    EVENT_APPOINTMENT_CONFIRMED = "appointment_confirmed"
    # A confirmação de uma marcação combinada ao telefone não pode ser dita
    # como a de um pedido feito no site: uma responde a um pedido que a cliente
    # fez, a outra anuncia uma marcação que ela ainda não viu escrita.
    EVENT_APPOINTMENT_CONFIRMED_INTERNAL = "appointment_confirmed_internal"
    EVENT_APPOINTMENT_CANCELLED = "appointment_cancelled"
    EVENT_APPOINTMENT_COMPLETED = "appointment_completed"
    # O aviso de que está na altura de voltar. Sai do comando diário dos
    # retornos, e não de uma marcação: é a única mensagem desta casa que fala
    # de uma marcação que ainda não existe.
    EVENT_RETURN_DUE = "return_due"
    # O lembrete da véspera. Sai do comando que corre de meia em meia hora, e
    # não de nada que alguém faça: é a única mensagem que ninguém manda.
    EVENT_APPOINTMENT_REMINDER = "appointment_reminder"

    EVENT_CHOICES = (
        (EVENT_APPOINTMENT_CREATED, "Pedido de marcação criado"),
        (EVENT_APPOINTMENT_CONFIRMED, "Marcação confirmada (pedida no site)"),
        (
            EVENT_APPOINTMENT_CONFIRMED_INTERNAL,
            "Marcação confirmada (criada na área interna)",
        ),
        (EVENT_APPOINTMENT_CANCELLED, "Marcação cancelada"),
        (EVENT_APPOINTMENT_COMPLETED, "Atendimento concluído"),
        (EVENT_APPOINTMENT_REMINDER, "Lembrete da marcação"),
        (EVENT_RETURN_DUE, "Está na altura de voltar"),
    )

    AUDIENCE_CUSTOMER = "customer"
    AUDIENCE_PROFESSIONAL = "professional"

    AUDIENCE_CHOICES = (
        (AUDIENCE_CUSTOMER, "Cliente"),
        (AUDIENCE_PROFESSIONAL, "Profissional"),
    )

    LEAD_TIME_UNIT_HOURS = "hours"
    LEAD_TIME_UNIT_DAYS = "days"

    LEAD_TIME_UNIT_CHOICES = (
        (LEAD_TIME_UNIT_HOURS, "Horas antes"),
        (LEAD_TIME_UNIT_DAYS, "Dias antes"),
    )

    name = models.CharField(
        max_length=150,
        verbose_name="Nome",
        help_text="Nome interno para identificar esta regra no admin.",
    )

    event_type = models.CharField(
        max_length=50,
        choices=EVENT_CHOICES,
        verbose_name="Acontecimento",
        help_text="Ação do sistema que poderá enviar email.",
    )

    # O mesmo acontecimento diz coisas diferentes de cada lado: à cliente
    # confirma-se a marcação, à profissional avisa-se que há um pedido à espera
    # de resposta. Uma linha por par, para cada uma se ligar e desligar à parte.
    audience = models.CharField(
        max_length=20,
        choices=AUDIENCE_CHOICES,
        default=AUDIENCE_CUSTOMER,
        verbose_name="Destinatário",
    )

    email_template = models.ForeignKey(
        EmailTemplate,
        on_delete=models.PROTECT,
        related_name="event_settings",
        blank=True,
        null=True,
        help_text="Template usado nesta ação. Se ficar vazio, o sistema usa o template pela chave padrão ou o texto de fallback.",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Desmarque para não enviar email nesta ação.",
    )

    lead_time_value = models.PositiveIntegerField(
        default=1,
        help_text="Apenas para lembretes. Exemplo: 1 dia antes, 2 horas antes.",
    )

    lead_time_unit = models.CharField(
        max_length=10,
        choices=LEAD_TIME_UNIT_CHOICES,
        default=LEAD_TIME_UNIT_DAYS,
        help_text="Apenas para lembretes.",
    )

    window_before_minutes = models.PositiveIntegerField(
        default=15,
        help_text="Apenas para lembretes. Margem antes do horário-alvo, em minutos.",
    )

    window_after_minutes = models.PositiveIntegerField(
        default=15,
        help_text="Apenas para lembretes. Margem depois do horário-alvo, em minutos.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["event_type", "name"]
        verbose_name = "Regra de email"
        verbose_name_plural = "Regras de email"
        constraints = [
            models.UniqueConstraint(
                fields=["event_type", "audience"],
                name="unique_email_setting_per_event_and_audience",
            ),
        ]

    def __str__(self):
        return self.name


class ServiceFollowUp(models.Model):
    """Mensagem ligada a um serviço, e o momento em que sai.

    Três momentos, porque um serviço tem coisas para dizer em alturas
    diferentes: o que se diz ao terminar o atendimento, o manual de cuidados
    que só faz sentido uns dias depois, e o texto que se guarda para mandar à
    mão quando for preciso. Cada serviço pode ter vários de cada.
    """

    TRIGGER_COMPLETION = "completion"
    TRIGGER_DELAYED = "delayed"
    TRIGGER_MANUAL = "manual"

    TRIGGER_CHOICES = (
        (TRIGGER_COMPLETION, "No fim do atendimento"),
        (TRIGGER_DELAYED, "Alguns dias depois"),
        (TRIGGER_MANUAL, "Só quando for enviada à mão"),
    )

    trigger = models.CharField(
        max_length=20,
        choices=TRIGGER_CHOICES,
        # Os seguimentos que já existiam são todos deste tipo, e é por isso que
        # é este o valor por omissão: a migração não muda o que já estava feito.
        default=TRIGGER_DELAYED,
        verbose_name="Quando enviar",
    )

    service = models.ForeignKey(
        "appointments.Service",
        on_delete=models.CASCADE,
        related_name="follow_ups",
        verbose_name="Serviço",
        help_text="O seguimento é enviado a quem fez este serviço.",
    )

    email_template = models.ForeignKey(
        EmailTemplate,
        on_delete=models.PROTECT,
        related_name="follow_ups",
        verbose_name="Modelo de email",
    )

    days_after = models.PositiveIntegerField(
        default=15,
        verbose_name="Dias depois do atendimento",
        help_text=(
            "Só conta para 'Alguns dias depois'. Zero envia no próprio dia "
            "do atendimento."
        ),
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Ativo",
        help_text="Desmarque para suspender o envio automático. O envio manual continua disponível.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["service__name", "trigger", "days_after"]
        verbose_name = "Mensagem por serviço"
        verbose_name_plural = "Mensagens por serviço"
        constraints = [
            models.UniqueConstraint(
                fields=["service", "email_template", "trigger", "days_after"],
                name="unique_service_message_per_template_and_moment",
            ),
        ]

    def __str__(self):
        return f"{self.service} · {self.get_delay_label()}"

    @property
    def is_automatic(self):
        """Se o sistema o envia sozinho, ou se espera por alguém.

        As mensagens manuais existem para estar à mão no ecrã da marcação; não
        entram no comando diário nem saem ao concluir um atendimento.
        """

        return self.trigger != self.TRIGGER_MANUAL

    def get_delay_label(self):
        if self.trigger == self.TRIGGER_MANUAL:
            return "envio manual"

        if self.trigger == self.TRIGGER_COMPLETION:
            return "no fim do atendimento"

        if self.days_after == 0:
            return "no próprio dia"

        if self.days_after == 1:
            return "1 dia depois"

        return f"{self.days_after} dias depois"

    def get_log_key(self):
        # A chave inclui a pk para dois seguimentos do mesmo serviço em prazos
        # diferentes não se confundirem um com o outro no registo de envios.
        return f"followup_{self.pk}"

    def due_date_for(self, appointment):
        from datetime import timedelta

        return appointment.date + timedelta(days=self.days_after)


class WhatsAppEventSetting(models.Model):
    """Quando enviar uma mensagem de WhatsApp e a quem.

    Uma linha por par acontecimento/destinatário: o pedido de marcação avisa a
    profissional e o cliente com textos diferentes, e cada um dos dois liga-se
    e desliga-se à parte.
    """

    EVENT_APPOINTMENT_REQUESTED = "appointment_requested"
    EVENT_APPOINTMENT_CONFIRMED = "appointment_confirmed"
    EVENT_APPOINTMENT_CONFIRMED_INTERNAL = "appointment_confirmed_internal"
    EVENT_APPOINTMENT_CANCELLED = "appointment_cancelled"
    EVENT_APPOINTMENT_COMPLETED = "appointment_completed"
    EVENT_RETURN_DUE = "return_due"
    EVENT_APPOINTMENT_REMINDER = "appointment_reminder"

    EVENT_CHOICES = (
        (EVENT_APPOINTMENT_REQUESTED, "Pedido de marcação recebido"),
        (EVENT_APPOINTMENT_CONFIRMED, "Marcação confirmada (pedida no site)"),
        (
            EVENT_APPOINTMENT_CONFIRMED_INTERNAL,
            "Marcação confirmada (criada na área interna)",
        ),
        (EVENT_APPOINTMENT_CANCELLED, "Marcação cancelada"),
        (EVENT_APPOINTMENT_COMPLETED, "Atendimento concluído"),
        (EVENT_APPOINTMENT_REMINDER, "Lembrete da marcação"),
        (EVENT_RETURN_DUE, "Está na altura de voltar"),
    )

    AUDIENCE_CUSTOMER = "customer"
    AUDIENCE_PROFESSIONAL = "professional"
    AUDIENCE_CUSTOM = "custom"

    AUDIENCE_CHOICES = (
        (AUDIENCE_CUSTOMER, "Cliente"),
        (AUDIENCE_PROFESSIONAL, "Profissional"),
        (AUDIENCE_CUSTOM, "Outros números"),
    )

    event_type = models.CharField(
        max_length=50,
        choices=EVENT_CHOICES,
        verbose_name="Acontecimento",
    )

    audience = models.CharField(
        max_length=20,
        choices=AUDIENCE_CHOICES,
        default=AUDIENCE_CUSTOMER,
        verbose_name="Destinatário",
    )

    custom_recipients = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Números",
        help_text=(
            "Só para 'Outros números'. Separe por vírgulas, com indicativo: "
            "+351912345678, +351913333333."
        ),
    )

    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    body_template = models.TextField(
        blank=True,
        verbose_name="Mensagem",
        help_text="Texto livre, com as mesmas variáveis dos emails.",
    )

    # A versão inglesa do texto livre, para quem marcou na versão inglesa do
    # site. Vazia envia-se o português: melhor a mensagem na língua errada do
    # que mensagem nenhuma.
    body_template_en = models.TextField(
        blank=True,
        verbose_name="Mensagem (inglês)",
        help_text=(
            "Deixe vazio para enviar a mensagem em português também a quem "
            "marcou na versão inglesa do site."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["event_type", "audience"]
        verbose_name = "Mensagem de WhatsApp"
        verbose_name_plural = "Mensagens de WhatsApp"
        constraints = [
            models.UniqueConstraint(
                fields=["event_type", "audience"],
                name="unique_whatsapp_setting_per_event_audience",
            ),
        ]

    def __str__(self):
        return f"{self.get_event_type_display()} → {self.get_audience_display()}"

    def for_language(self, language):
        """O texto na língua pedida, com o português como recurso.

        Um campo inglês vazio não é uma mensagem vazia: é uma mensagem por
        traduzir, e aí vale mais o português. Uma mensagem na língua errada
        continua a avisar a pessoa; uma mensagem por enviar não avisa ninguém.
        """

        ingles = (language or "").lower().startswith("en")

        if not ingles:
            return {"body": self.body_template}

        return {"body": self.body_template_en or self.body_template}

    def clean(self):
        if self.audience == self.AUDIENCE_CUSTOM and not self.custom_recipients.strip():
            raise ValidationError(
                {"custom_recipients": "Indique pelo menos um número."}
            )

        # Sem texto não há nada para enviar. Era uma de duas condições —
        # texto ou modelo aprovado — enquanto houve um segundo caminho.
        if not self.body_template.strip():
            raise ValidationError(
                {"body_template": "Preencha a mensagem: é o que vai ser enviado."}
            )

    def get_template_label(self):
        # Fica no histórico de envios. Houve um tempo em que podia ser o
        # identificador de um modelo aprovado; hoje é sempre texto livre.
        return "texto-livre"

    def is_ready_to_send(self):
        """Se esta regra tem o que precisa para a mensagem chegar mesmo.

        Uma regra ligada mas incompleta é o pior dos casos: parece que está a
        funcionar e não está. O que falta é sempre o texto.
        """

        return bool(self.body_template.strip())


class WhatsAppMessageLog(models.Model):
    # Stores WhatsApp sending attempts for audit and duplicate prevention.

    EVENT_APPOINTMENT_REQUESTED = "appointment_requested"
    EVENT_APPOINTMENT_CONFIRMED = "appointment_confirmed"
    EVENT_APPOINTMENT_CONFIRMED_INTERNAL = "appointment_confirmed_internal"
    EVENT_APPOINTMENT_CANCELLED = "appointment_cancelled"
    EVENT_APPOINTMENT_COMPLETED = "appointment_completed"
    EVENT_RETURN_DUE = "return_due"
    EVENT_APPOINTMENT_REMINDER = "appointment_reminder"

    EVENT_CHOICES = (
        (EVENT_APPOINTMENT_REQUESTED, "Pedido de marcação recebido"),
        (EVENT_APPOINTMENT_CONFIRMED, "Marcação confirmada (pedida no site)"),
        (
            EVENT_APPOINTMENT_CONFIRMED_INTERNAL,
            "Marcação confirmada (criada na área interna)",
        ),
        (EVENT_APPOINTMENT_CANCELLED, "Marcação cancelada"),
        (EVENT_APPOINTMENT_COMPLETED, "Atendimento concluído"),
        (EVENT_APPOINTMENT_REMINDER, "Lembrete da marcação"),
        (EVENT_RETURN_DUE, "Está na altura de voltar"),
    )

    # O registo guarda por onde a mensagem saiu. A Twilio saiu do projeto, mas
    # o valor fica na lista: há linhas antigas com ele, e um histórico que
    # deixa de saber ler o que lá está não é um histórico.
    PROVIDER_CLOUD_API = "cloud_api"
    PROVIDER_TWILIO = "twilio"
    PROVIDER_BAILEYS = "baileys"

    PROVIDER_CHOICES = (
        (PROVIDER_CLOUD_API, "WhatsApp Cloud API"),
        (PROVIDER_TWILIO, "Twilio (retirado)"),
        (PROVIDER_BAILEYS, "Baileys"),
    )

    provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default=PROVIDER_CLOUD_API,
    )

    # Sem isto, avisar a profissional e o cliente do mesmo acontecimento com o
    # mesmo texto colidiria na restrição de unicidade e o segundo envio seria
    # dado como repetido.
    audience = models.CharField(
        max_length=20,
        default=WhatsAppEventSetting.AUDIENCE_CUSTOMER,
    )

    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"
    STATUS_SKIPPED = "skipped"

    STATUS_CHOICES = (
        (STATUS_SUCCESS, "Sucesso"),
        (STATUS_ERROR, "Erro"),
        (STATUS_SKIPPED, "Ignorado"),
    )

    appointment = models.ForeignKey(
        "appointments.Appointment",
        on_delete=models.CASCADE,
        related_name="whatsapp_logs",
    )

    event_type = models.CharField(
        max_length=50,
        choices=EVENT_CHOICES,
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
    )

    template_name = models.CharField(
        max_length=100,
    )

    recipient_phone = models.CharField(
        max_length=30,
    )

    whatsapp_message_id = models.CharField(
        max_length=255,
        blank=True,
    )

    request_payload = models.TextField(
        blank=True,
    )

    response_payload = models.TextField(
        blank=True,
    )

    error_message = models.TextField(
        blank=True,
    )

    # `status` diz se o fornecedor **aceitou** a mensagem. Não diz se ela
    # chegou: a entrega acontece depois. Estes três campos vinham do webhook
    # de estado da Twilio e ficam por preencher desde que ela saiu do projeto —
    # continuam aqui pelas linhas antigas que os têm.
    delivery_status = models.CharField(
        max_length=20,
        blank=True,
        help_text="Estado final da entrega, quando o fornecedor o devolve.",
    )

    delivery_error_code = models.CharField(max_length=20, blank=True)

    delivery_updated_at = models.DateTimeField(blank=True, null=True)

    sent_at = models.DateTimeField(auto_now_add=True)

    DELIVERY_LABELS = {
        "queued": "Em fila",
        "sending": "A enviar",
        "sent": "Enviada",
        "delivered": "Entregue",
        "read": "Lida",
        "undelivered": "Não entregue",
        "failed": "Falhou",
    }

    def get_delivery_label(self):
        if not self.delivery_status:
            # O Baileys entrega a mensagem ao WhatsApp na própria chamada: não
            # há webhook de estado a chegar depois, e por isso não faz sentido
            # prometer uma confirmação que nunca vem.
            if self.provider == self.PROVIDER_BAILEYS:
                return "Entregue ao WhatsApp"

            return "Aceite pelo fornecedor"

        return self.DELIVERY_LABELS.get(self.delivery_status, self.delivery_status)

    def delivery_failed(self):
        return self.delivery_status in {"undelivered", "failed"}

    class Meta:
        ordering = ["-sent_at"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "appointment",
                    "event_type",
                    "template_name",
                    "audience",
                    "provider",
                ],
                condition=Q(status="success"),
                name="unique_success_whatsapp_per_appointment_event_template",
            ),
        ]

    def __str__(self):
        return (
            f"{self.appointment.reference_code} - {self.template_name} - {self.status}"
        )


class InstagramPost(models.Model):
    # Publicação real do Instagram, registada colando o código de incorporação
    # oficial (Instagram > "..." > Copiar código de incorporação) e exibida
    # como embed ao vivo (blockquote + embed.js) em carrossel no site.

    embed_code = models.TextField(
        help_text=(
            "Cole aqui o código de incorporação do Instagram (no post, clique em "
            '"..." → Copiar código de incorporação). Pode colar o bloco inteiro, '
            "inclusive a linha &lt;script&gt; — ela é removida automaticamente ao guardar."
        ),
    )

    display_order = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "-created_at"]
        verbose_name = "Publicação do Instagram"
        verbose_name_plural = "Publicações do Instagram"

    def save(self, *args, **kwargs):
        # Remove a(s) tag(s) <script> do trecho colado: o script do embed.js
        # já é carregado uma única vez pelo template, para todos os posts.
        self.embed_code = re.sub(
            r"<script\b[^>]*>.*?</script>",
            "",
            self.embed_code,
            flags=re.IGNORECASE | re.DOTALL,
        ).strip()

        super().save(*args, **kwargs)

    @property
    def permalink(self):
        match = re.search(r'data-instgrm-permalink="([^"]+)"', self.embed_code)

        return match.group(1) if match else ""

    def __str__(self):
        return self.permalink or f"Publicação #{self.pk}"


class MessagingSetting(models.Model):
    """Que canais podem escrever aos clientes.

    Há alturas em que a clínica não quer que saia alguma coisa: férias, uma
    migração de número, um problema com um fornecedor, ou o receio de que uma
    regra mal configurada comece a escrever a toda a gente. Sem um sítio único
    para desligar, a única saída era ir a cada regra de WhatsApp e a cada
    acontecimento de email e desligá-los um a um — demorado, fácil de esquecer
    metade, e pior ainda de repor depois.

    É por canal e não um interruptor único porque os dois avariam por razões
    diferentes: o WhatsApp perde a ligação, o fornecedor bloqueia, o número
    muda — e nada disso é razão para a cliente deixar de receber a confirmação
    por email. Desligar tudo por causa de um lado calava o outro sem motivo.

    Cada canal está acima das regras dele: desligado, não sai nada por ali —
    nem automático, nem manual, nem de teste. Um interruptor que às vezes deixa
    passar mensagens não serve para o que é preciso, que é ter a certeza.

    Existe uma linha só, com pk fixo. É uma definição da clínica, não uma lista.
    """

    SINGLETON_PK = 1

    send_emails = models.BooleanField(
        default=True,
        verbose_name="Enviar emails",
        help_text=(
            "Confirmações, cancelamentos, seguimentos e envios manuais por "
            "email. Desligado, as marcações continuam a funcionar."
        ),
    )

    send_whatsapp = models.BooleanField(
        default=True,
        verbose_name="Enviar mensagens de WhatsApp",
        help_text=(
            "Todas as regras de WhatsApp, incluindo os envios manuais e os de "
            "teste. Desligado, as marcações continuam a funcionar."
        ),
    )

    # Quem desligou e quando. Uma mensagem que não chegou costuma ser
    # descoberta dias depois, por alguém que não esteve presente na decisão.
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messaging_setting_changes",
        verbose_name="Alterado por",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Envio de mensagens"
        verbose_name_plural = "Envio de mensagens"

    def __str__(self):
        ligados = [
            nome
            for nome, ligado in (
                ("email", self.send_emails),
                ("WhatsApp", self.send_whatsapp),
            )
            if ligado
        ]

        if not ligados:
            return "Nada a sair"

        return "A enviar por " + " e ".join(ligados)

    def save(self, *args, **kwargs):
        # Uma segunda linha faria com que os interruptores visíveis na página
        # não fossem necessariamente os que os envios consultam.
        self.pk = self.SINGLETON_PK

        return super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        definicao, _criada = cls.objects.get_or_create(pk=cls.SINGLETON_PK)

        return definicao

    @classmethod
    def _canal_ligado(cls, campo):
        """Em caso de erro a ler a definição, responde que sim.

        A alternativa era uma falha de base de dados calar as confirmações e os
        lembretes sem ninguém dar por isso, o que é pior do que uma mensagem a
        mais.
        """

        try:
            return getattr(cls.load(), campo)
        except Exception:
            logger.exception("Não foi possível ler o interruptor de mensagens.")

            return True

    @classmethod
    def emails_enabled(cls):
        """Se os emails para clientes podem sair agora."""

        return cls._canal_ligado("send_emails")

    @classmethod
    def whatsapp_enabled(cls):
        """Se as mensagens de WhatsApp podem sair agora."""

        return cls._canal_ligado("send_whatsapp")


class BeforeAfterCase(models.Model):
    """Um caso mostrado no site como um par de fotografias, antes e depois.

    As duas fotografias ocupam o mesmo espaço na página, uma por cima da
    outra, e quem visita arrasta uma linha para revelar mais de uma ou da
    outra. Por isso **as duas são recortadas para o mesmo enquadramento**: o
    que muda entre elas tem de ser o tratamento, não a moldura. Fotografias
    com proporções muito diferentes continuam a funcionar, mas perde-se mais
    de uma delas no recorte.

    São imagens de pessoas reais em contexto clínico: nada aqui aparece no
    site sem `is_active`, e é por aí que se retira um caso depressa se a
    pessoa mudar de ideias.
    """

    REVEAL_VERTICAL = "vertical"
    REVEAL_HORIZONTAL = "horizontal"

    REVEAL_CHOICES = [
        (REVEAL_VERTICAL, "Vertical — antes à esquerda, arrasta-se para os lados"),
        (REVEAL_HORIZONTAL, "Horizontal — antes em cima, arrasta-se para baixo"),
    ]

    title = models.CharField(
        "Título da foto",
        max_length=140,
        help_text="O que este par mostra. Aparece por cima das fotografias.",
    )

    caption = models.TextField(
        "Legenda da foto",
        blank=True,
        help_text="Texto que acompanha o par. Aparece por baixo das fotografias.",
    )

    before_image = models.ImageField(
        "Fotografia do antes",
        upload_to="antes-e-depois/",
    )

    after_image = models.ImageField(
        "Fotografia do depois",
        upload_to="antes-e-depois/",
    )

    # Enquadramento de cada fotografia dentro da caixa quadrada do site.
    #
    # A caixa tem proporção fixa e recorta o que sobra, e o que interessa numa
    # fotografia de pé raramente está no meio exato do ficheiro. Estes valores
    # dizem quanto aproximar e que ponto manter à vista, e são o que faz as
    # duas fotografias ficarem alinhadas uma com a outra — sem isso, uma
    # tirada um passo mais atrás desalinha a comparação inteira.
    #
    # Percentagens e não decimais: `object-position` e `scale()` recebem-nas
    # tal como estão, sem conversões pelo caminho.
    before_zoom = models.PositiveSmallIntegerField(
        "Aproximação do antes",
        default=100,
        validators=[MinValueValidator(100), MaxValueValidator(300)],
        help_text="100 é a fotografia inteira; 200 é o dobro do tamanho.",
    )

    before_focus_x = models.PositiveSmallIntegerField(
        "Ponto do antes (horizontal)",
        default=50,
        validators=[MaxValueValidator(100)],
    )

    before_focus_y = models.PositiveSmallIntegerField(
        "Ponto do antes (vertical)",
        default=50,
        validators=[MaxValueValidator(100)],
    )

    after_zoom = models.PositiveSmallIntegerField(
        "Aproximação do depois",
        default=100,
        validators=[MinValueValidator(100), MaxValueValidator(300)],
    )

    after_focus_x = models.PositiveSmallIntegerField(
        "Ponto do depois (horizontal)",
        default=50,
        validators=[MaxValueValidator(100)],
    )

    after_focus_y = models.PositiveSmallIntegerField(
        "Ponto do depois (vertical)",
        default=50,
        validators=[MaxValueValidator(100)],
    )

    # Por que lado se separam as duas fotografias.
    #
    # A linha estava fixa na vertical, e nem todas as fotografias se leem bem
    # assim: um pé fotografado ao comprido divide-se melhor de cima para
    # baixo, e a comparação lado a lado corta-o ao meio. Fica por caso, como
    # já ficava o enquadramento, porque é do par de fotografias que depende.
    reveal_orientation = models.CharField(
        "Barra de comparação",
        max_length=10,
        choices=REVEAL_CHOICES,
        default=REVEAL_VERTICAL,
        help_text=(
            "Por onde a linha separa as duas fotografias. Escolha a direção "
            "que atravessa o que mudou."
        ),
    )

    display_order = models.PositiveIntegerField(
        "Ordem",
        default=0,
        help_text="Menor primeiro. Em caso de empate, o mais recente à frente.",
    )

    is_active = models.BooleanField(
        "Visível no site",
        default=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "-created_at"]
        verbose_name = "Caso antes e depois"
        verbose_name_plural = "Casos antes e depois"

    def framing(self, lado):
        """O enquadramento de um dos lados, pronto para o CSS.

        Um sítio só a montar isto: o mesmo enquadramento é usado na página
        pública, na pré-visualização do formulário e nas miniaturas da
        gestão, e três construções à mão divergiriam à primeira alteração.
        """

        return {
            "zoom": getattr(self, f"{lado}_zoom") / 100,
            "x": f"{getattr(self, f'{lado}_focus_x')}%",
            "y": f"{getattr(self, f'{lado}_focus_y')}%",
        }

    @property
    def is_horizontal(self):
        """A comparação faz-se de cima para baixo, e não lado a lado."""

        return self.reveal_orientation == self.REVEAL_HORIZONTAL

    @property
    def before_style(self):
        return self._estilo("before")

    @property
    def after_style(self):
        return self._estilo("after")

    def _estilo(self, lado):
        enquadramento = self.framing(lado)

        return (
            f"--ba-zoom: {enquadramento['zoom']};"
            f"--ba-x: {enquadramento['x']};"
            f"--ba-y: {enquadramento['y']};"
        )

    def save(self, *args, **kwargs):
        # As fotografias são encolhidas antes de ir para o disco. Aqui e não
        # no formulário, para que o admin do Django — que grava o modelo
        # diretamente — não fique de fora.
        for campo in ("before_image", "after_image"):
            resize_uploaded_image(getattr(self, campo))

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
