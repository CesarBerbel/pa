import json
import logging
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

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

    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Modelo de email"
        verbose_name_plural = "Modelos de email"

    def __str__(self):
        return self.name


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

    EVENT_CHOICES = (
        (EVENT_APPOINTMENT_CREATED, "Pedido de marcação criado"),
        (EVENT_APPOINTMENT_CONFIRMED, "Marcação confirmada (pedida no site)"),
        (
            EVENT_APPOINTMENT_CONFIRMED_INTERNAL,
            "Marcação confirmada (criada na área interna)",
        ),
        (EVENT_APPOINTMENT_CANCELLED, "Marcação cancelada"),
        (EVENT_APPOINTMENT_COMPLETED, "Atendimento concluído"),
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

    EVENT_CHOICES = (
        (EVENT_APPOINTMENT_REQUESTED, "Pedido de marcação recebido"),
        (EVENT_APPOINTMENT_CONFIRMED, "Marcação confirmada (pedida no site)"),
        (
            EVENT_APPOINTMENT_CONFIRMED_INTERNAL,
            "Marcação confirmada (criada na área interna)",
        ),
        (EVENT_APPOINTMENT_CANCELLED, "Marcação cancelada"),
        (EVENT_APPOINTMENT_COMPLETED, "Atendimento concluído"),
    )

    AUDIENCE_CUSTOMER = "customer"
    AUDIENCE_PROFESSIONAL = "professional"
    AUDIENCE_CUSTOM = "custom"

    AUDIENCE_CHOICES = (
        (AUDIENCE_CUSTOMER, "Cliente"),
        (AUDIENCE_PROFESSIONAL, "Profissional"),
        (AUDIENCE_CUSTOM, "Outros números"),
    )

    PROVIDER_TWILIO = "twilio"
    PROVIDER_BAILEYS = "baileys"

    PROVIDER_CHOICES = (
        (PROVIDER_TWILIO, "Twilio"),
        (PROVIDER_BAILEYS, "Baileys (número da clínica)"),
    )

    event_type = models.CharField(
        max_length=50,
        choices=EVENT_CHOICES,
        verbose_name="Acontecimento",
    )

    # A escolha é por regra, e não global, porque os dois caminhos têm feitios
    # diferentes: a Twilio custa dinheiro e exige modelos aprovados, mas é um
    # serviço contratado; o Baileys é o número da clínica ligado como um
    # dispositivo, sem custo nem aprovações e sem garantia nenhuma. Um aviso
    # interno à profissional e uma confirmação a um cliente não têm por que
    # sair pelo mesmo sítio.
    provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default=PROVIDER_TWILIO,
        verbose_name="Enviar por",
        help_text=(
            "Twilio: precisa de modelo aprovado, mas é um serviço contratado. "
            "Baileys: texto livre pelo número da clínica, sem custo, mas "
            "depende da ligação por QR code estar de pé."
        ),
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
        help_text=(
            "Texto livre, com as mesmas variáveis dos emails. A Twilio só o "
            "aceita nas 24 horas seguintes a uma mensagem do destinatário — "
            "fora disso é preciso um modelo aprovado."
        ),
    )

    content_sid = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="Modelo aprovado (Content SID)",
        help_text=(
            "Começa por HX. Necessário para mensagens iniciadas pela clínica, "
            "que é o caso de tudo o que sai daqui."
        ),
    )

    meta_template_body = models.TextField(
        blank=True,
        verbose_name="Texto para aprovação (Meta)",
        help_text=(
            "O mesmo texto com as posições numeradas — {{1}}, {{2}} — para "
            "colar no Content Template Builder da Twilio. É este que a Meta "
            "revê; o campo acima é o que o sistema envia."
        ),
    )

    content_variables = models.TextField(
        blank=True,
        verbose_name="Variáveis do modelo",
        help_text=(
            "JSON com as posições do modelo aprovado. Exemplo: "
            '{"1": "{{ customer_name }}", "2": "{{ appointment_date }}"}'
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

    def clean(self):
        if self.audience == self.AUDIENCE_CUSTOM and not self.custom_recipients.strip():
            raise ValidationError(
                {"custom_recipients": "Indique pelo menos um número."}
            )

        if self.provider == self.PROVIDER_BAILEYS:
            # O Baileys não conhece modelos aprovados. Um Content SID preenchido
            # aqui não seria usado, e a regra parecia configurada sem ter texto
            # nenhum para enviar.
            if not self.body_template.strip():
                raise ValidationError(
                    {
                        "body_template": (
                            "O Baileys envia texto livre. Preencha a mensagem — "
                            "o modelo aprovado da Twilio não se aplica aqui."
                        )
                    }
                )

        elif not self.body_template.strip() and not self.content_sid.strip():
            raise ValidationError(
                "Preencha a mensagem ou indique um modelo aprovado; sem um dos "
                "dois não há nada para enviar."
            )

        if self.content_variables.strip():
            try:
                dados = json.loads(self.content_variables)
            except ValueError as erro:
                raise ValidationError(
                    {"content_variables": f"JSON inválido: {erro}"}
                ) from erro

            if not isinstance(dados, dict):
                raise ValidationError(
                    {"content_variables": "Deve ser um objeto JSON com as posições."}
                )

    def get_template_label(self):
        # Identifica no histórico se a mensagem saiu por modelo aprovado ou
        # como texto livre. Pelo Baileys é sempre texto livre, mesmo que a
        # regra tenha um Content SID guardado de quando saía pela Twilio.
        if self.provider == self.PROVIDER_BAILEYS:
            return "texto-livre"

        return self.content_sid.strip() or "texto-livre"

    def is_ready_to_send(self):
        """Se esta regra tem o que precisa para a mensagem chegar mesmo.

        Uma regra ligada mas incompleta é o pior dos casos: parece que está a
        funcionar e não está. Pela Twilio falta o modelo aprovado; pelo
        Baileys falta o texto.
        """

        if self.provider == self.PROVIDER_BAILEYS:
            return bool(self.body_template.strip())

        return bool(self.content_sid.strip())


class WhatsAppMessageLog(models.Model):
    # Stores WhatsApp sending attempts for audit and duplicate prevention.

    EVENT_APPOINTMENT_REQUESTED = "appointment_requested"
    EVENT_APPOINTMENT_CONFIRMED = "appointment_confirmed"
    EVENT_APPOINTMENT_CONFIRMED_INTERNAL = "appointment_confirmed_internal"
    EVENT_APPOINTMENT_CANCELLED = "appointment_cancelled"
    EVENT_APPOINTMENT_COMPLETED = "appointment_completed"

    EVENT_CHOICES = (
        (EVENT_APPOINTMENT_REQUESTED, "Pedido de marcação recebido"),
        (EVENT_APPOINTMENT_CONFIRMED, "Marcação confirmada (pedida no site)"),
        (
            EVENT_APPOINTMENT_CONFIRMED_INTERNAL,
            "Marcação confirmada (criada na área interna)",
        ),
        (EVENT_APPOINTMENT_CANCELLED, "Marcação cancelada"),
        (EVENT_APPOINTMENT_COMPLETED, "Atendimento concluído"),
    )

    PROVIDER_CLOUD_API = "cloud_api"
    PROVIDER_TWILIO = "twilio"
    PROVIDER_BAILEYS = "baileys"

    PROVIDER_CHOICES = (
        (PROVIDER_CLOUD_API, "WhatsApp Cloud API"),
        (PROVIDER_TWILIO, "Twilio"),
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

    # `status` diz se a Twilio **aceitou** a mensagem. Não diz se ela chegou:
    # a entrega acontece depois, e falha em silêncio se ninguém a for buscar.
    # Estes três campos são preenchidos pelo webhook de estado da Twilio.
    delivery_status = models.CharField(
        max_length=20,
        blank=True,
        help_text="Estado final devolvido pela Twilio: delivered, undelivered, failed.",
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
            # O Baileys entrega a mensagem ao WhatsApp na própria chamada; não
            # há webhook de estado a chegar depois, como na Twilio, por isso
            # não faz sentido prometer uma confirmação que nunca vem.
            if self.provider == self.PROVIDER_BAILEYS:
                return "Entregue ao WhatsApp"

            return "Aceite pela Twilio"

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
    """Interruptor geral de mensagens para clientes.

    Há alturas em que a clínica não quer que saia nada: férias, uma migração de
    número, um problema com o fornecedor, ou simplesmente o receio de que uma
    regra mal configurada comece a escrever a toda a gente. Sem um sítio único
    para desligar, a única saída era ir a cada regra de WhatsApp e a cada
    acontecimento de email e desligá-los um a um — demorado, fácil de esquecer
    metade, e pior ainda de repor depois.

    Está acima de tudo o resto: com isto desligado não sai email nem WhatsApp,
    nem automático, nem manual, nem de teste. Um interruptor que às vezes deixa
    passar mensagens não serve para o que é preciso, que é ter a certeza.

    Existe uma linha só, com pk fixo. É uma definição da clínica, não uma lista.
    """

    SINGLETON_PK = 1

    is_enabled = models.BooleanField(
        default=True,
        verbose_name="Enviar mensagens",
        help_text=(
            "Quando desligado, o site não envia emails nem mensagens de "
            "WhatsApp. As marcações continuam a funcionar normalmente."
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
        return "Mensagens ligadas" if self.is_enabled else "Mensagens desligadas"

    def save(self, *args, **kwargs):
        # Uma segunda linha faria com que o interruptor visível na página não
        # fosse necessariamente o que os envios consultam.
        self.pk = self.SINGLETON_PK

        return super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        definicao, _criada = cls.objects.get_or_create(pk=cls.SINGLETON_PK)

        return definicao

    @classmethod
    def messaging_enabled(cls):
        """Se as mensagens para clientes podem sair agora.

        Em caso de erro a ler a definição responde que sim. A alternativa era
        uma falha de base de dados calar as confirmações e os lembretes sem
        ninguém dar por isso, o que é pior do que uma mensagem a mais.
        """

        try:
            return cls.load().is_enabled
        except Exception:
            logger.exception("Não foi possível ler o interruptor de mensagens.")

            return True
