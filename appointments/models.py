import logging
import re
import secrets
import string
from datetime import datetime, timedelta
from decimal import Decimal
from django.core.validators import MinValueValidator

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import get_language

from appointments.rich_text import esta_vazio, limpar

logger = logging.getLogger(__name__)


def campo_da_lingua(default_value, english_value):
    """O campo desta língua, e só desta — sem cair para a outra.

    O `get_localized_value` cai para o português quando o inglês está vazio, e
    para um corpo de texto isso é o que se quer: uma página meio traduzida vale
    mais do que meia página em branco.

    Para o título e a descrição que vão para o Google, não. Numa página com o
    nome já traduzido, um `meta_title` vazio em inglês fazia sair o título
    português — "Unha encravada: tratamento em Coimbra" por cima de uma página
    escrita em inglês de alto a baixo. Vale mais o nome inglês, que existe.

    Quem chama isto trata do recurso a seguir, e escolhe-o na mesma língua.
    """

    language = get_language() or ""

    if language.lower().startswith("en"):
        return english_value

    return default_value


def get_localized_value(default_value, english_value):
    # Public pages are also served in English under /en/. Catalog content lives
    # in the database, so it cannot go through gettext. Fall back to the
    # Portuguese value whenever the English one was left empty in the admin.
    language = get_language() or ""

    if language.lower().startswith("en") and english_value:
        return english_value

    return default_value


class ServiceCategory(models.Model):
    # Represents a public service category, such as Podologia or Enfermagem.

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)

    name_en = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Nome (inglês)",
        help_text="Usado nas páginas em /en/. Se ficar vazio, mostra o nome em português.",
    )

    description_en = models.TextField(
        blank=True,
        verbose_name="Descrição (inglês)",
        help_text="Usada nas páginas em /en/. Se ficar vazia, mostra a descrição em português.",
    )
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    # Shown publicly with an "Em breve" badge, but not yet bookable.
    is_coming_soon = models.BooleanField(default=False)

    # Preços só aparecem no site nas categorias onde forem explicitamente
    # ligados, para não publicar valores que ainda não foram revistos.
    show_prices = models.BooleanField(
        default=False,
        verbose_name="Mostrar preços no site",
        help_text=(
            "Quando ligado, o preço de cada serviço desta categoria aparece "
            "na página inicial e na lista de serviços."
        ),
    )

    # A página inicial posiciona a casa como podologia. Nem tudo o que se
    # marca precisa de estar lá: a lista completa vive na página de serviços,
    # e é essa que continua a mostrar tudo. Interruptor e não regra escrita no
    # código, para a decisão poder mudar sem um deploy.
    show_on_homepage = models.BooleanField(
        default=True,
        verbose_name="Mostrar na página inicial",
        help_text=(
            "Desligado, a categoria continua marcável e visível na página de "
            "serviços, mas deixa de aparecer na página inicial."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Categoria de serviço"
        verbose_name_plural = "Categorias de serviço"

    def __str__(self):
        return self.name

    @property
    def display_name(self):
        return get_localized_value(self.name, self.name_en)

    @property
    def display_description(self):
        return get_localized_value(self.description, self.description_en)


def get_default_service_category():
    # Return an active default category for legacy flows that do not submit one.
    category = (
        ServiceCategory.objects.filter(is_active=True)
        .order_by("display_order", "name")
        .first()
    )

    if category:
        return category

    category, _created = ServiceCategory.objects.get_or_create(
        slug="geral",
        defaults={
            "name": "Geral",
            "description": "Categoria padrão para serviços sem categoria definida.",
            "display_order": 999,
            "is_active": True,
        },
    )

    if not category.is_active:
        category.is_active = True
        category.save(update_fields=["is_active", "updated_at"])

    return category


class Service(models.Model):
    # Represents a bookable service offered inside a public category.

    category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.PROTECT,
        related_name="services",
        verbose_name="Categoria",
    )

    name = models.CharField(max_length=120, verbose_name="Nome")
    description = models.TextField(blank=True, verbose_name="Descrição")

    name_en = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Nome (inglês)",
        help_text="Usado nas páginas em /en/. Se ficar vazio, mostra o nome em português.",
    )

    description_en = models.TextField(
        blank=True,
        verbose_name="Descrição (inglês)",
        help_text="Usada nas páginas em /en/. Se ficar vazia, mostra a descrição em português.",
    )

    duration_minutes = models.PositiveIntegerField(
        default=60,
        validators=[
            MinValueValidator(1),
        ],
        verbose_name="Duração (minutos)",
    )

    return_days = models.PositiveIntegerField(
        default=0,
        verbose_name="Retorno sugerido (dias)",
        help_text=(
            "Ao concluir um atendimento deste serviço, é este o prazo "
            "proposto para a pessoa voltar. Zero não propõe nada."
        ),
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
        verbose_name="Preço",
    )

    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category__display_order", "category__name", "name"]
        verbose_name = "Serviço"
        verbose_name_plural = "Serviços"

    def __str__(self):
        if self.category_id and self.category:
            return f"{self.category.name} - {self.name}"

        return self.name

    @property
    def display_name(self):
        return get_localized_value(self.name, self.name_en)

    @property
    def display_description(self):
        return get_localized_value(self.description, self.description_en)

    def name_for_language(self, language):
        """O nome do serviço na língua pedida, e não na da página.

        `display_name` olha para a página onde alguém está, o que serve o site
        e não serve as mensagens: uma confirmação em inglês é escrita a partir
        da área interna, que está em português, e saía "Your appointment for
        Pedicure terapêutica". A língua da mensagem é a da marcação, e é ela
        que tem de ser pedida aqui.
        """

        if (language or "").lower().startswith("en") and self.name_en:
            return self.name_en

        return self.name

    def save(self, *args, **kwargs):
        # Service categories were added after the initial service model.
        # Assign a safe fallback category when legacy code/tests create a service
        # without explicitly selecting one, while keeping the database relation
        # non-null for current production data.
        if not self.category_id:
            self.category = get_default_service_category()

        super().save(*args, **kwargs)


class Customer(models.Model):
    # Represents a customer who can book appointments

    full_name = models.CharField(max_length=255, verbose_name="Nome completo")
    email = models.EmailField(blank=True, verbose_name="Email")
    phone = models.CharField(max_length=30, verbose_name="Telefone")

    is_guest = models.BooleanField(
        default=False,
        verbose_name="Sem conta no site",
    )

    # Guardado a partir da versão do site em que a marcação foi feita. É por
    # aqui que as mensagens sabem em que língua falar com esta pessoa: quem
    # marcou em /en/ não percebe uma confirmação em português, e quem marcou
    # em português não quer receber inglês.
    language = models.CharField(
        max_length=10,
        choices=settings.LANGUAGES,
        default="pt-pt",
        verbose_name="Idioma",
        help_text="Língua em que esta cliente recebe emails e mensagens.",
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_profile",
        verbose_name="Conta de utilizador",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"

    def __str__(self):
        return self.full_name

    @property
    def prefers_english(self):
        return (self.language or "").lower().startswith("en")

    @property
    def whatsapp_url(self):
        """Ligação direta para a conversa de WhatsApp desta cliente.

        O wa.me só aceita o número em dígitos. O `+` com que o telefone é
        guardado leva a uma página de erro em vez da conversa, e o número
        continua a parecer certo a quem carregou.
        """

        digitos = re.sub(r"\D", "", self.phone or "")

        if not digitos:
            return ""

        return f"https://wa.me/{digitos}"


class PatientRecord(models.Model):
    """Ficha de anamnese de uma cliente.

    Contém dados de saúde, que o RGPD trata como categoria especial (artigo
    9.º). É por isso acessível apenas na área interna, atrás de autenticação de
    administrador, e nunca exposta em páginas públicas nem em emails.

    Há uma ficha por cliente, revista ao longo do tempo: o histórico de saúde
    pertence à pessoa e não a uma marcação isolada.
    """

    customer = models.OneToOneField(
        Customer,
        on_delete=models.CASCADE,
        related_name="patient_record",
        verbose_name="Cliente",
    )

    main_complaint = models.TextField(
        blank=True,
        verbose_name="Motivo da consulta",
        help_text="Queixa principal e há quanto tempo dura.",
    )

    # Sinalizadores clínicos. São campos próprios, e não texto livre, para
    # poderem aparecer como aviso na lista de clientes: em podologia, diabetes
    # e problemas de circulação mudam a forma de tratar.
    has_diabetes = models.BooleanField(
        default=False,
        verbose_name="Diabetes",
    )

    has_circulatory_issues = models.BooleanField(
        default=False,
        verbose_name="Problemas de circulação",
    )

    has_cardiovascular_issues = models.BooleanField(
        default=False,
        verbose_name="Problemas cardiovasculares",
    )

    has_hypertension = models.BooleanField(
        default=False,
        verbose_name="Hipertensão arterial",
    )

    has_neuropathy = models.BooleanField(
        default=False,
        verbose_name="Neuropatia periférica",
    )

    has_coagulation_issues = models.BooleanField(
        default=False,
        verbose_name="Alterações da coagulação ou anticoagulantes",
    )

    has_rheumatic_disease = models.BooleanField(
        default=False,
        verbose_name="Doença reumática (artrite, artrose)",
    )

    has_thyroid_disease = models.BooleanField(
        default=False,
        verbose_name="Alterações da tiroide",
    )

    has_kidney_disease = models.BooleanField(
        default=False,
        verbose_name="Doença renal",
    )

    has_skin_condition = models.BooleanField(
        default=False,
        verbose_name="Doença dermatológica (psoríase, eczema)",
    )

    is_pregnant = models.BooleanField(
        default=False,
        verbose_name="Grávida",
    )

    has_allergies = models.BooleanField(
        default=False,
        verbose_name="Alergias",
    )

    is_smoker = models.BooleanField(
        default=False,
        verbose_name="Fumadora",
    )

    allergies = models.TextField(
        blank=True,
        verbose_name="Quais alergias",
        help_text="Obrigatório quando existem alergias.",
    )

    medical_history = models.TextField(
        blank=True,
        verbose_name="Outros antecedentes",
        help_text="Doenças relevantes não cobertas pelas opções acima.",
    )

    current_medication = models.TextField(
        blank=True,
        verbose_name="Medicação habitual",
    )

    previous_surgeries = models.TextField(
        blank=True,
        verbose_name="Cirurgias e tratamentos anteriores",
    )

    footwear_notes = models.TextField(
        blank=True,
        verbose_name="Calçado e hábitos",
        help_text="Tipo de calçado usado, atividade física, tempo em pé.",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="Observações",
    )

    birth_date = models.DateField(
        blank=True,
        null=True,
        verbose_name="Data de nascimento",
        help_text="A idade condiciona a avaliação vascular e neurológica.",
    )

    profession = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Profissão",
        help_text="Tempo em pé e tipo de calçado de trabalho são relevantes.",
    )

    # --- Exame podológico ---

    skin_assessment = models.TextField(
        blank=True,
        verbose_name="Pele",
        help_text="Hidratação, hiperqueratose, fissuras, maceração interdigital.",
    )

    nail_assessment = models.TextField(
        blank=True,
        verbose_name="Unhas",
        help_text="Onicomicose, onicocriptose, onicogrifose, hematoma subungueal.",
    )

    foot_deformities = models.TextField(
        blank=True,
        verbose_name="Deformidades e apoio",
        help_text="Hallux valgus, dedos em garra, pé plano ou cavo, zonas de pressão.",
    )

    vascular_assessment = models.TextField(
        blank=True,
        verbose_name="Avaliação vascular",
        help_text="Pulsos pedioso e tibial posterior, temperatura, cor, edema.",
    )

    neurological_assessment = models.TextField(
        blank=True,
        verbose_name="Avaliação neurológica",
        help_text="Sensibilidade ao monofilamento, diapasão, reflexos.",
    )

    gait_assessment = models.TextField(
        blank=True,
        verbose_name="Marcha",
    )

    DIABETIC_RISK_NOT_APPLICABLE = "na"
    DIABETIC_RISK_LOW = "low"
    DIABETIC_RISK_MODERATE = "moderate"
    DIABETIC_RISK_HIGH = "high"

    DIABETIC_RISK_CHOICES = [
        (DIABETIC_RISK_NOT_APPLICABLE, "Não aplicável"),
        (DIABETIC_RISK_LOW, "Baixo"),
        (DIABETIC_RISK_MODERATE, "Moderado"),
        (DIABETIC_RISK_HIGH, "Alto"),
    ]

    diabetic_foot_risk = models.CharField(
        max_length=10,
        choices=DIABETIC_RISK_CHOICES,
        default=DIABETIC_RISK_NOT_APPLICABLE,
        verbose_name="Risco de pé diabético",
    )

    treatment_plan = models.TextField(
        blank=True,
        verbose_name="Plano de tratamento",
        help_text="Cuidados previstos, periodicidade e indicações dadas.",
    )

    consent_confirmed = models.BooleanField(
        default=False,
        verbose_name="Cliente informada sobre o registo clínico",
        help_text=(
            "Confirma que a cliente foi informada de que estes dados de saúde "
            "são registados e para que servem."
        ),
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_patient_records",
        verbose_name="Última alteração por",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["customer__full_name"]
        verbose_name = "Ficha de anamnese"
        verbose_name_plural = "Fichas de anamnese"

    def __str__(self):
        return f"Anamnese de {self.customer.full_name}"

    @property
    def age(self):
        if not self.birth_date:
            return None

        hoje = datetime.today().date()
        anos = hoje.year - self.birth_date.year

        if (hoje.month, hoje.day) < (self.birth_date.month, self.birth_date.day):
            anos -= 1

        return anos

    def clean(self):
        # Saber que há alergia sem saber qual não serve para nada no momento
        # do atendimento.
        if self.has_allergies and not self.allergies.strip():
            raise ValidationError({"allergies": "Indique quais são as alergias."})

    @property
    def risk_alerts(self):
        # Avisos a mostrar junto do nome da cliente. Só entram aqui as condições
        # que mudam a conduta no momento do atendimento.
        alertas = []

        if self.has_diabetes:
            alertas.append("Diabetes")

        if self.has_neuropathy:
            # Perda de sensibilidade protetora: a cliente pode não sentir dor
            # durante o tratamento.
            alertas.append("Neuropatia")

        if self.has_circulatory_issues:
            alertas.append("Circulação")

        if self.has_cardiovascular_issues:
            alertas.append("Cardiovascular")

        if self.has_coagulation_issues:
            alertas.append("Coagulação")

        if self.has_allergies:
            alertas.append("Alergias")

        if self.diabetic_foot_risk == self.DIABETIC_RISK_HIGH:
            alertas.append("Pé diabético: risco alto")

        return alertas

    @property
    def is_filled(self):
        # Uma ficha criada e deixada em branco não conta como preenchida.
        campos_de_texto = [
            self.main_complaint,
            self.medical_history,
            self.current_medication,
            self.previous_surgeries,
            self.footwear_notes,
            self.notes,
            self.skin_assessment,
            self.nail_assessment,
            self.foot_deformities,
            self.vascular_assessment,
            self.neurological_assessment,
            self.gait_assessment,
            self.treatment_plan,
            self.profession,
        ]

        return any(
            [
                any(campo.strip() for campo in campos_de_texto),
                bool(self.birth_date),
                bool(self.risk_alerts),
            ]
        )


class PatientRecordLog(models.Model):
    """Histórico de alterações de uma ficha de anamnese.

    A conservação digital de registos clínicos exige garantir a integridade da
    informação. Saber apenas quem fez a última alteração não chega: é preciso
    poder reconstituir o que mudou, quando e por quem — por exemplo quando uma
    alergia é apagada por engano.
    """

    record = models.ForeignKey(
        PatientRecord,
        on_delete=models.CASCADE,
        related_name="logs",
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="patient_record_logs",
    )

    description = models.TextField(
        verbose_name="Alterações",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # O `pk` desempata: a data tem resolução limitada e dois registos
        # gravados no mesmo instante ficavam sem ordem definida entre si,
        # com o mais antigo a aparecer como se fosse o último.
        ordering = ["-created_at", "-pk"]
        verbose_name = "Alteração de ficha"
        verbose_name_plural = "Alterações de fichas"

    def __str__(self):
        return f"{self.record.customer.full_name} - {self.created_at:%Y-%m-%d %H:%M}"


class SchedulingSetting(models.Model):
    """As regras de agenda que a profissional decide, e que estavam no código.

    Intervalo da grelha, antecedência mínima para marcar, prazo para cancelar e
    até quando o site aceita marcações: quatro números que mudam com a forma de
    trabalhar e que, escritos no código, obrigavam a um deploy para mudar de
    ideias.

    Existe uma linha só, com pk fixo. É uma definição da clínica, não uma lista.
    """

    SINGLETON_PK = 1

    SLOT_CHOICES = [
        (15, "15 minutos"),
        (30, "30 minutos"),
        (60, "1 hora"),
    ]

    slot_minutes = models.PositiveIntegerField(
        choices=SLOT_CHOICES,
        default=30,
        verbose_name="Intervalo da grelha",
        help_text=(
            "De quanto em quanto tempo a agenda é dividida. Vale para a agenda "
            "interna e para os horários oferecidos no site."
        ),
    )

    booking_min_advance_hours = models.PositiveIntegerField(
        default=3,
        verbose_name="Antecedência mínima para marcar",
        help_text=(
            "Horas que têm de faltar para um horário poder ser marcado no "
            "site. Zero aceita marcações até à hora exata."
        ),
    )

    booking_horizon_days = models.PositiveIntegerField(
        default=21,
        verbose_name="Marcações até",
        help_text=(
            "Quantos dias à frente o site deixa marcar. Encurtar não afeta as "
            "marcações que já existem."
        ),
    )

    cancellation_min_advance_hours = models.PositiveIntegerField(
        default=0,
        verbose_name="Prazo para cancelar no site",
        help_text=(
            "Horas que têm de faltar para a cliente ainda poder cancelar "
            "sozinha. Passado o prazo, a marcação só é cancelada pela clínica. "
            "Zero deixa cancelar até à hora da marcação."
        ),
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduling_setting_changes",
        verbose_name="Alterado por",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Regras de agenda"
        verbose_name_plural = "Regras de agenda"

    def __str__(self):
        return f"Grelha de {self.get_slot_minutes_display()}"

    def save(self, *args, **kwargs):
        # Uma segunda linha faria com que a grelha visível na página não fosse
        # necessariamente a que a agenda usa.
        self.pk = self.SINGLETON_PK

        return super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        definicao, _criada = cls.objects.get_or_create(pk=cls.SINGLETON_PK)

        return definicao

    @classmethod
    def _valor(cls, campo, reserva):
        """Lê uma regra sem nunca escrever.

        Não passa pelo `load()` de propósito: esse cria a linha se ela faltar,
        e estas leituras acontecem a desenhar páginas — um GET não deve gravar
        nada. Sem linha, valem os valores de fábrica do próprio modelo.

        Em caso de erro responde com o valor de reserva: uma falha de base de
        dados não pode partir a agenda. Mais vale a grelha sair com o intervalo
        de fábrica do que não sair de todo.
        """

        try:
            definicao = cls.objects.filter(pk=cls.SINGLETON_PK).first()

            return getattr(definicao, campo) if definicao else reserva
        except Exception:
            logger.exception("Não foi possível ler as regras de agenda.")

            return reserva

    @classmethod
    def get_slot_minutes(cls):
        return cls._valor("slot_minutes", 30)

    @classmethod
    def get_booking_min_advance_hours(cls):
        return cls._valor("booking_min_advance_hours", 3)

    @classmethod
    def get_booking_horizon_days(cls):
        return cls._valor("booking_horizon_days", 21)

    @classmethod
    def get_cancellation_min_advance_hours(cls):
        return cls._valor("cancellation_min_advance_hours", 0)


class BusinessHour(models.Model):
    # Defines working hours per weekday

    WEEKDAY_CHOICES = [
        (0, "Segunda-feira"),
        (1, "Terça-feira"),
        (2, "Quarta-feira"),
        (3, "Quinta-feira"),
        (4, "Sexta-feira"),
        (5, "Sábado"),
        (6, "Domingo"),
    ]

    weekday = models.IntegerField(
        choices=WEEKDAY_CHOICES,
        unique=True,
        verbose_name="Dia da semana",
    )
    start_time = models.TimeField(verbose_name="Hora inicial")
    end_time = models.TimeField(verbose_name="Hora final")

    # Segundo período do dia. Existe para a pausa de almoço ficar implícita no
    # horário de trabalho, em vez de depender de um bloqueio recorrente que é
    # preciso lembrar de manter.
    second_start_time = models.TimeField(
        blank=True,
        null=True,
        verbose_name="Hora inicial (tarde)",
        help_text="Deixe vazio se trabalhar em período único.",
    )

    second_end_time = models.TimeField(
        blank=True,
        null=True,
        verbose_name="Hora final (tarde)",
    )

    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        ordering = ["weekday"]
        verbose_name = "Horário de funcionamento"
        verbose_name_plural = "Horários de funcionamento"

    def __str__(self):
        periodos = " e ".join(f"{inicio} às {fim}" for inicio, fim in self.periods)

        return f"{self.get_weekday_display()} - {periodos}"

    @property
    def periods(self):
        # Períodos de trabalho do dia, na ordem. Um dia de período único
        # devolve uma lista de um só elemento, para o resto do sistema poder
        # tratar sempre da mesma maneira.
        periodos = []

        if self.start_time and self.end_time:
            periodos.append((self.start_time, self.end_time))

        if self.second_start_time and self.second_end_time:
            periodos.append((self.second_start_time, self.second_end_time))

        return periodos

    @property
    def has_second_period(self):
        return bool(self.second_start_time and self.second_end_time)

    @property
    def duration_minutes(self):
        # Soma dos períodos, já sem a pausa entre eles.
        total = 0
        referencia = datetime.today()

        for inicio, fim in self.periods:
            delta = datetime.combine(referencia, fim) - datetime.combine(
                referencia, inicio
            )
            total += int(delta.total_seconds() / 60)

        return total

    @property
    def duration_display(self):
        # Return gross working duration formatted as hours and minutes.
        total_minutes = self.duration_minutes
        hours = total_minutes // 60
        minutes = total_minutes % 60

        if minutes:
            return f"{hours}h{minutes:02d}"

        return f"{hours}h"

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError(
                "O horário final deve ser maior que o horário inicial."
            )

        # Os dois campos da tarde andam sempre juntos: só um preenchido seria
        # um período sem fim ou sem início.
        if bool(self.second_start_time) != bool(self.second_end_time):
            raise ValidationError(
                "Preencha a hora inicial e a hora final da tarde, ou deixe "
                "ambas vazias."
            )

        if not self.has_second_period:
            return

        if self.second_end_time <= self.second_start_time:
            raise ValidationError(
                {
                    "second_end_time": (
                        "A hora final da tarde deve ser maior que a inicial."
                    )
                }
            )

        if self.end_time and self.second_start_time < self.end_time:
            raise ValidationError(
                {
                    "second_start_time": (
                        "O período da tarde tem de começar depois do fim da manhã."
                    )
                }
            )


class ScheduleBlock(models.Model):
    # Represents unavailable periods in the schedule, including recurring blocks

    BLOCK_TYPE_BREAK = "break"
    BLOCK_TYPE_VACATION = "vacation"
    BLOCK_TYPE_DAY_OFF = "day_off"
    BLOCK_TYPE_OTHER = "other"

    BLOCK_TYPE_CHOICES = [
        (BLOCK_TYPE_BREAK, "Pausa"),
        (BLOCK_TYPE_VACATION, "Férias"),
        (BLOCK_TYPE_DAY_OFF, "Folga"),
        (BLOCK_TYPE_OTHER, "Outro"),
    ]

    WEEKDAY_CHOICES = [
        ("0", "Segunda-feira"),
        ("1", "Terça-feira"),
        ("2", "Quarta-feira"),
        ("3", "Quinta-feira"),
        ("4", "Sexta-feira"),
        ("5", "Sábado"),
        ("6", "Domingo"),
    ]

    block_type = models.CharField(
        max_length=20,
        choices=BLOCK_TYPE_CHOICES,
        default=BLOCK_TYPE_OTHER,
        verbose_name="Tipo",
    )
    date = models.DateField(
        verbose_name="Data",
        help_text=(
            "Num bloqueio único, o dia. Num bloqueio que se repete, o dia em "
            "que a repetição começa."
        ),
    )
    start_time = models.TimeField(blank=True, null=True, verbose_name="Hora de início")
    end_time = models.TimeField(blank=True, null=True, verbose_name="Hora de fim")
    is_full_day = models.BooleanField(default=False, verbose_name="Dia inteiro")

    is_recurring = models.BooleanField(default=False, verbose_name="Repete-se")
    recurring_weekdays = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Dias da semana da repetição",
        help_text="Dias separados por vírgula. Exemplo: 0,1,2,3,4",
    )
    recurrence_end_date = models.DateField(
        blank=True,
        null=True,
        verbose_name="Repete até",
    )

    is_active = models.BooleanField(default=True, verbose_name="Ativo")
    notes = models.TextField(blank=True, verbose_name="Observações")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "start_time"]
        verbose_name = "Bloqueio de agenda"
        verbose_name_plural = "Bloqueios de agenda"

    def __str__(self):
        return f"{self.label} - {self.date}"

    @property
    def label(self):
        """Como o bloqueio se apresenta num ecrã.

        Substituiu o campo de título, que pedia à mão aquilo que o tipo já
        dizia. Quem quiser precisar mais escreve nas observações, e é a
        primeira linha delas que aparece.
        """

        primeira_linha = (self.notes or "").strip().splitlines()

        if primeira_linha:
            return primeira_linha[0][:120]

        return self.get_block_type_display()

    def get_recurring_weekday_list(self):
        # Returns selected recurring weekdays as a clean list
        if not self.recurring_weekdays:
            return []

        return [
            item.strip() for item in self.recurring_weekdays.split(",") if item.strip()
        ]

    def applies_to_date(self, selected_date):
        # Checks if this block applies to a selected date
        if not self.is_active:
            return False

        if not self.is_recurring:
            return self.date == selected_date

        if selected_date < self.date:
            return False

        if self.recurrence_end_date and selected_date > self.recurrence_end_date:
            return False

        return str(selected_date.weekday()) in self.get_recurring_weekday_list()

    def get_start_datetime_for_date(self, selected_date):
        # Returns block start for a specific date
        if self.is_full_day:
            return datetime.combine(selected_date, datetime.min.time())

        return datetime.combine(selected_date, self.start_time)

    def get_end_datetime_for_date(self, selected_date):
        # Returns block end for a specific date
        if self.is_full_day:
            return datetime.combine(selected_date, datetime.max.time())

        return datetime.combine(selected_date, self.end_time)

    def get_start_datetime(self):
        # Returns block start using its own date
        return self.get_start_datetime_for_date(self.date)

    def get_end_datetime(self):
        # Returns block end using its own date
        return self.get_end_datetime_for_date(self.date)

    def conflicting_appointments(self):
        """Marcações que este bloqueio taparia.

        Os encaixes ficam de fora de propósito. Um encaixe é uma marcação que
        alguém colocou por cima de um bloqueio, sabendo o que estava a fazer;
        se contasse aqui, o bloqueio deixaria de poder ser editado depois — nem
        para lhe corrigir o título.
        """

        from appointments.availability import AvailabilityService

        if not self.is_active or not self.date:
            return []

        if not self.is_full_day and not (self.start_time and self.end_time):
            return []

        candidatas = (
            Appointment.objects.filter(date__gte=self.date)
            .exclude(status=Appointment.STATUS_CANCELLED)
            .exclude(outside_schedule=True)
            .select_related("customer", "service")
            .order_by("date", "start_time")
        )

        if self.is_recurring:
            if self.recurrence_end_date:
                candidatas = candidatas.filter(date__lte=self.recurrence_end_date)
        else:
            candidatas = candidatas.filter(date=self.date)

        # Percorre as marcações e não as datas: um bloqueio recorrente sem fim
        # definido cobre um número indeterminado de dias, mas o número de
        # marcações é sempre finito.
        return [
            marcacao
            for marcacao in candidatas
            if self.applies_to_date(marcacao.date)
            and AvailabilityService.overlaps(
                marcacao.get_start_datetime(),
                marcacao.get_end_datetime(),
                self.get_start_datetime_for_date(marcacao.date),
                self.get_end_datetime_for_date(marcacao.date),
            )
        ]

    def clean(self):
        # Validate schedule block consistency
        if self.is_recurring and not self.recurring_weekdays:
            raise ValidationError(
                "Indique pelo menos um dia da semana para o bloqueio recorrente."
            )

        if not self.is_full_day:
            if not self.start_time or not self.end_time:
                raise ValidationError(
                    "Indique o horário inicial e final ou marque como dia inteiro."
                )

            if self.end_time <= self.start_time:
                raise ValidationError(
                    "O horário final do bloqueio deve ser maior que o horário inicial."
                )

        self.validate_no_appointments_in_the_way()

    def validate_no_appointments_in_the_way(self):
        """Recusa o bloqueio quando já há alguém marcado no período.

        Deixar criar tornaria a marcação invisível na agenda pública e deixaria
        a cliente à porta num dia que o sistema diz estar fechado. Quem bloqueia
        precisa de saber que há alguém marcado, para desmarcar primeiro.
        """

        conflitos = self.conflicting_appointments()

        if not conflitos:
            return

        detalhes = ", ".join(
            f"{marcacao.customer.full_name} "
            f"({marcacao.date.strftime('%d/%m')} às "
            f"{marcacao.start_time.strftime('%H:%M')})"
            for marcacao in conflitos[:3]
        )

        if len(conflitos) > 3:
            detalhes = f"{detalhes} e mais {len(conflitos) - 3}"

        raise ValidationError(
            f"Já existem marcações neste período: {detalhes}. "
            "Cancele ou mude essas marcações antes de bloquear."
        )


class Appointment(models.Model):
    # Represents a scheduled appointment

    STATUS_SCHEDULED = "scheduled"
    STATUS_CONFIRMED = "confirmed"
    STATUS_CANCELLED = "cancelled"
    STATUS_COMPLETED = "completed"

    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "Agendado"),
        (STATUS_CONFIRMED, "Confirmado"),
        (STATUS_CANCELLED, "Cancelado"),
        (STATUS_COMPLETED, "Concluído"),
    ]

    reference_code = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        editable=False,
        verbose_name="Código da marcação",
    )

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="appointments",
        verbose_name="Cliente",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="appointments",
        verbose_name="Serviço",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_appointments",
        verbose_name="Criada por",
    )

    date = models.DateField(verbose_name="Data")
    start_time = models.TimeField(verbose_name="Hora de início")

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_SCHEDULED,
        verbose_name="Estado",
    )

    # A língua desta marcação, e não a da pessoa.
    #
    # A língua da cliente é uma só e acompanha a última marcação: quem marcou
    # em inglês e volta a marcar em português muda-a, e as mensagens das
    # marcações antigas mudavam com ela. Aqui fica a desta, escrita quando ela
    # foi feita — em /en/ nasce marcada — e a profissional pode marcá-la à mão
    # por quem lhe telefona em inglês sem nunca ter passado pelo site.
    customer_speaks_english = models.BooleanField(
        default=False,
        verbose_name="Cliente fala inglês",
        help_text="As mensagens desta marcação saem em inglês.",
    )

    # Atendimento em casa da cliente.
    #
    # A morada vive na marcação e não no cliente de propósito: uma pessoa pode
    # ser atendida em casa numa vez e na clínica na seguinte, ou em casa de um
    # familiar de quem trata. O que interessa é onde é *este* atendimento.
    is_home_visit = models.BooleanField(
        default=False,
        verbose_name="Atendimento em domicílio",
        help_text="A profissional desloca-se a casa da cliente.",
    )

    # A morada em campos e não numa caixa de texto: escrita à mão, chegava
    # "Rua das Flores 12" sem código postal nem localidade, e quem lá vai
    # descobria-o à porta. Em campos, o que falta vê-se.
    #
    # Só a rua é obrigatória. Uma morada de aldeia pode não ter número nem
    # código postal conhecido, e exigi-los impedia de marcar um atendimento
    # que existe.
    home_street = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Rua",
        help_text="Obrigatória num atendimento em domicílio.",
    )

    home_number = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="Número",
    )

    home_floor = models.CharField(
        max_length=60,
        blank=True,
        verbose_name="Andar ou fração",
        help_text="3.º Dto, R/C esquerdo, Lote 4 — o que estiver na porta.",
    )

    home_postal_code = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Código postal",
    )

    home_locality = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Localidade",
    )

    home_municipality = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Concelho",
    )

    home_district = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Distrito",
    )

    home_country = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="País",
    )

    home_directions = models.TextField(
        blank=True,
        verbose_name="Como chegar",
        help_text=(
            "Opcional: andar, campainha, onde estacionar, um ponto de "
            "referência — o que poupe uma chamada à porta do prédio."
        ),
    )

    notes = models.TextField(blank=True, verbose_name="Observações")
    cancellation_reason = models.TextField(
        blank=True,
        verbose_name="Motivo do cancelamento",
    )
    cancelled_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Cancelada em",
    )

    # De onde veio a marcação. Não dá para deduzir do `created_by`: uma
    # marcação feita no site é gravada em nome do primeiro administrador, e
    # ficava indistinguível de uma que a profissional tenha marcado à mão.
    ORIGIN_PUBLIC = "public"
    ORIGIN_INTERNAL = "internal"
    ORIGIN_UNKNOWN = "unknown"

    ORIGIN_CHOICES = (
        (ORIGIN_PUBLIC, "Site"),
        (ORIGIN_INTERNAL, "Área interna"),
        # As marcações anteriores a este registo. Deixar "Site" ou "Área
        # interna" seria inventar: numa auditoria, não saber tem de se ver.
        (ORIGIN_UNKNOWN, "Desconhecida"),
    )

    origin = models.CharField(
        max_length=20,
        choices=ORIGIN_CHOICES,
        default=ORIGIN_INTERNAL,
        verbose_name="Origem",
    )

    # Um encaixe é uma marcação que a profissional colocou fora do horário de
    # funcionamento ou por cima de um bloqueio. Fica gravado, e não apenas
    # decidido no momento em que se cria: sem isto, confirmar ou concluir a
    # marcação mais tarde voltaria a passar pela validação do horário e falharia
    # numa marcação que existe de forma legítima.
    outside_schedule = models.BooleanField(
        default=False,
        verbose_name="Encaixe fora do horário",
        help_text=(
            "Marcação colocada fora do horário de funcionamento ou sobre um "
            "bloqueio, a partir da área interna."
        ),
    )

    reminder_sent_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    reminder_24h_sent_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    reminder_2h_sent_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "start_time"]
        verbose_name = "Marcação"
        verbose_name_plural = "Marcações"
        constraints = [
            # Database-level guard against double booking. Application validation
            # can be bypassed by a concurrent request that passes availability
            # checks before the other one commits.
            # This covers collisions on the same slot start. Partial overlaps
            # between services of different durations remain covered only by
            # AvailabilityService.validate_appointment().
            models.UniqueConstraint(
                fields=["date", "start_time"],
                condition=~models.Q(status="cancelled"),
                name="unique_active_appointment_per_slot",
            ),
        ]

    def __str__(self):
        return f"{self.reference_code} - {self.customer} - {self.service}"

    def generate_reference_code(self):
        # `secrets` e não `random`: este código é a credencial de acesso à
        # marcação. Com ele, e sem sessão iniciada, vê-se e cancela-se —
        # ver PublicAppointmentByCodeView e PublicCancelAppointmentByCodeView.
        # O `random` é um Mersenne Twister: quem visse alguns códigos emitidos
        # podia reconstruir o estado do gerador e prever os seguintes.
        #
        # Formato e alfabeto ficam como estavam: há códigos já enviados em
        # mensagens e emails de clientes, e é este o formato que os testes e o
        # exemplo do formulário de consulta mostram.
        while True:
            random_code = "".join(
                secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6)
            )
            code = f"AGD-{random_code}"

            if not Appointment.objects.filter(reference_code=code).exists():
                return code

    def get_start_datetime(self):
        # Returns appointment start as datetime
        return datetime.combine(self.date, self.start_time)

    def get_end_datetime(self):
        # Returns appointment end based on service duration
        return self.get_start_datetime() + timedelta(
            minutes=self.service.duration_minutes
        )

    @property
    def home_address(self):
        """A morada numa linha, para quem a lê de fora.

        As mensagens à cliente e os ecrãs querem a morada escrita, não oito
        campos. Montá-la num sítio só evita que cada um a escreva à sua
        maneira — e que um deles se esqueça do código postal.
        """

        rua = " ".join(parte for parte in [self.home_street, self.home_number] if parte)
        localidade = " ".join(
            parte for parte in [self.home_postal_code, self.home_locality] if parte
        )

        partes = [rua, self.home_floor, localidade, self.home_municipality]

        # O concelho não se repete quando é o mesmo nome da localidade, que em
        # Portugal é o caso mais comum: "3000-351 Coimbra, Coimbra".
        if self.home_municipality and self.home_municipality == self.home_locality:
            partes.remove(self.home_municipality)

        return ", ".join(parte.strip() for parte in partes if parte.strip())

    def clean(self):
        # Keep model validation as a thin delegate to the domain availability policy.
        from appointments.availability import AvailabilityService

        # Um domicílio sem morada é uma deslocação para lado nenhum, e a
        # mensagem que sai à cliente diz que vamos ter com ela — a um sítio
        # que ninguém escreveu. Fica aqui e não só no formulário para valer
        # também no admin e em qualquer gravação feita por código.
        if self.is_home_visit and not self.home_street.strip():
            raise ValidationError(
                {
                    "home_street": (
                        "Indique a rua: é para onde a profissional se desloca."
                    )
                }
            )

        AvailabilityService.validate_appointment(self)

    # Campos de que a validação de disponibilidade depende. Uma gravação que
    # não lhes toque não precisa de repetir a validação, e não a deve repetir:
    # confirmar ou concluir uma marcação que já existe voltaria a medi-la contra
    # o horário de funcionamento de hoje, que pode ter mudado desde que ela foi
    # criada. O resultado era um erro 500 ao concluir uma marcação legítima e já
    # realizada, por causa de uma regra que só faz sentido ao agendar.
    SCHEDULING_FIELDS = frozenset(
        {"service", "service_id", "date", "start_time", "outside_schedule"}
    )

    def save(self, *args, **kwargs):
        # Auto-generate reference code before validation and saving
        if not self.reference_code:
            self.reference_code = self.generate_reference_code()

        update_fields = kwargs.get("update_fields")

        # update_fields a None é uma gravação completa (incluindo a criação):
        # aí a validação corre sempre.
        if update_fields is None or self.SCHEDULING_FIELDS & set(update_fields):
            self.full_clean()

        return super().save(*args, **kwargs)


# Nomes dos campos como aparecem no ecrã de auditoria. Sem isto, quem consulta
# o registo via "start_time" em vez de "Hora".
FIELD_LABELS = {
    "customer": "Cliente",
    "service": "Serviço",
    "date": "Data",
    "start_time": "Hora",
    "status": "Estado",
    "notes": "Observações",
    "cancellation_reason": "Motivo do cancelamento",
    "outside_schedule": "Encaixe fora do horário",
}


class AppointmentLog(models.Model):
    # Stores audit trail for appointment changes.

    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_CANCEL = "cancel"
    ACTION_CONFIRM = "confirm"
    ACTION_COMPLETE = "complete"

    ACTION_CHOICES = [
        (ACTION_CREATE, "Create"),
        (ACTION_UPDATE, "Update"),
        (ACTION_CANCEL, "Cancel"),
        (ACTION_CONFIRM, "Confirm"),
        (ACTION_COMPLETE, "Complete"),
    ]

    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="logs",
    )

    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointment_logs",
    )

    # De onde partiu esta ação em concreto, que nem sempre é a origem da
    # marcação: uma marcação feita no site pode ser cancelada pela equipa, e
    # uma marcada pela equipa pode ser cancelada pela cliente com o código.
    SOURCE_PUBLIC = "public"
    SOURCE_INTERNAL = "internal"
    SOURCE_SYSTEM = "system"
    SOURCE_UNKNOWN = "unknown"

    SOURCE_CHOICES = (
        (SOURCE_PUBLIC, "Site"),
        (SOURCE_INTERNAL, "Área interna"),
        # Tarefas agendadas e rotinas que correm sem ninguém à frente.
        (SOURCE_SYSTEM, "Automático"),
        (SOURCE_UNKNOWN, "Desconhecida"),
    )

    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_INTERNAL,
        verbose_name="Origem",
    )

    description = models.TextField(blank=True)

    # O que mudou, campo a campo: {"start_time": {"de": "10:00", "para": "11:00"}}.
    # Guardado como dados e não embutido no texto da descrição, para a página
    # de auditoria poder mostrar cada alteração à parte e para se poder
    # procurar por campo.
    changes = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Alterações",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Ver `PatientRecordLog`: sem o `pk`, dois registos do mesmo instante
        # saíam pela ordem errada.
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.appointment.reference_code} - {self.action}"

    @property
    def changed_fields(self):
        """As alterações prontas a listar, com os nomes que se veem no ecrã."""

        if not isinstance(self.changes, dict):
            return []

        return [
            {
                "field": campo,
                "label": FIELD_LABELS.get(campo, campo),
                "from": valores.get("de", ""),
                "to": valores.get("para", ""),
            }
            for campo, valores in self.changes.items()
            if isinstance(valores, dict)
        ]


class AppointmentReminderLog(models.Model):
    # Stores reminder sending logs for audit and monitoring.

    REMINDER_TYPE_24H = "24h"
    REMINDER_TYPE_2H = "2h"

    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"

    STATUS_CHOICES = (
        (STATUS_SUCCESS, "Sucesso"),
        (STATUS_ERROR, "Erro"),
    )

    appointment = models.ForeignKey(
        "Appointment",
        on_delete=models.CASCADE,
        related_name="reminder_logs",
    )

    reminder_type = models.CharField(
        max_length=50,
        help_text="Reminder identifier, e.g. reminder_1_days or reminder_2_hours.",
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
    )

    error_message = models.TextField(
        blank=True,
    )

    sent_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return (
            f"{self.appointment.reference_code} - {self.reminder_type} - {self.status}"
        )


class ReturnVisit(models.Model):
    """Um retorno: a intenção de voltar, antes de haver marcação nenhuma.

    É a peça que faltava. Uma marcação de retorno já combinada é só uma
    marcação — o que se perdia era o outro caso, o mais comum: "volte daqui a
    três semanas, depois combinamos". Isso vivia numa frase nas observações
    que ninguém voltava a ler, ou na cabeça de quem atendeu.

    Por isso tem data-alvo e não data: a data é do dia em que a marcação for
    feita, e até lá o que existe é um prazo a cumprir.

    Guarda as duas pontas: `origin` é o atendimento de onde veio, `appointment`
    é o que o cumpriu. Com as duas, sabe-se que a consulta de hoje é o retorno
    daquela de há um mês.
    """

    STATUS_PENDING = "pending"
    STATUS_SCHEDULED = "scheduled"
    STATUS_DISMISSED = "dismissed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Por marcar"),
        (STATUS_SCHEDULED, "Marcado"),
        (STATUS_DISMISSED, "Dispensado"),
    ]

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="return_visits",
        verbose_name="Cliente",
    )

    # O atendimento que o originou. `SET_NULL` porque apagar uma marcação
    # antiga não pode apagar um retorno que ainda está por marcar.
    origin = models.ForeignKey(
        "Appointment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="returns_generated",
        verbose_name="Atendimento de origem",
    )

    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="return_visits",
        verbose_name="Serviço previsto",
    )

    target_date = models.DateField(
        verbose_name="Voltar por volta de",
        help_text="A data que se combinou com a pessoa, ainda sem hora.",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name="Estado",
    )

    # A marcação que cumpriu este retorno. Um retorno cumpre-se uma vez só.
    appointment = models.OneToOneField(
        "Appointment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="return_visit",
        verbose_name="Marcação",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="Notas",
        help_text="O que fica para lembrar quando se ligar à pessoa.",
    )

    # Quando saiu a mensagem a dizer que está na altura de voltar. Serve de
    # travão: o comando diário corre todos os dias e não pode repetir o aviso.
    notified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Avisada em",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_return_visits",
        verbose_name="Criado por",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["target_date", "customer__full_name"]
        verbose_name = "Retorno"
        verbose_name_plural = "Retornos"

    def __str__(self):
        return f"{self.customer.full_name} — {self.target_date:%d/%m/%Y}"

    @property
    def is_late(self):
        """A data-alvo passou e continua por marcar.

        Atrasado não é um estado guardado: seria um estado que envelhece
        sozinho e obrigava alguém a correr atrás dele todos os dias.
        """

        return (
            self.status == self.STATUS_PENDING
            and self.target_date < timezone.localdate()
        )


class ClinicalNote(models.Model):
    """Nota de evolução de uma consulta: o que foi efetivamente feito.

    A ficha de anamnese guarda o histórico da pessoa; esta guarda os atos
    praticados em cada sessão, que a legislação exige constarem do registo
    clínico. Uma nota por marcação.
    """

    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name="clinical_note",
        verbose_name="Marcação",
    )

    procedures = models.TextField(
        verbose_name="Atos praticados",
        help_text="O que foi feito nesta consulta.",
    )

    observations = models.TextField(
        blank=True,
        verbose_name="Observações clínicas",
        help_text="Estado encontrado, evolução desde a última consulta.",
    )

    recommendations = models.TextField(
        blank=True,
        verbose_name="Indicações dadas",
        help_text="Cuidados recomendados e próximos passos.",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clinical_notes",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-appointment__date", "-appointment__start_time"]
        verbose_name = "Nota de evolução"
        verbose_name_plural = "Notas de evolução"

    def __str__(self):
        return f"Nota de {self.appointment.reference_code}"

    def clean(self):
        if not self.procedures.strip():
            raise ValidationError(
                {"procedures": "Descreva os atos praticados nesta consulta."}
            )


class TreatedCondition(models.Model):
    """Um problema que a pedicure terapêutica trata, com página própria.

    Quem procura no Google não escreve "pedicure terapêutica": escreve "unha
    encravada dói muito" ou "micose na unha do pé tratamento". Uma página só de
    serviços responde à pergunta errada — diz o que se vende, não o que a
    pessoa tem. Cada linha desta tabela é uma página que responde à pergunta
    que a pessoa fez, e só no fim propõe marcar.

    As secções são fixas e não um campo de texto livre porque é a repetição
    que faz isto funcionar: a mesma ordem em todas as páginas dá ao leitor um
    sítio previsível para procurar, e ao Google uma estrutura para ler.

    **Nasce por publicar.** É texto sobre saúde assinado por uma enfermeira, e
    o custo de publicar uma frase errada não se compara ao de ela esperar uma
    leitura.
    """

    slug = models.SlugField(
        max_length=140,
        unique=True,
        verbose_name="Endereço",
        help_text="A parte final do endereço: /o-que-tratamos/unha-encravada/",
    )

    name = models.CharField(
        max_length=120,
        verbose_name="Nome",
        help_text="Como a pessoa lhe chama. É o título da página.",
    )

    name_en = models.CharField(max_length=120, blank=True, verbose_name="Nome (inglês)")

    summary = models.TextField(
        verbose_name="Resumo",
        help_text=(
            "Duas ou três linhas, logo abaixo do título. Serve também de "
            "descrição para o Google quando não houver uma escrita à mão."
        ),
    )

    summary_en = models.TextField(blank=True, verbose_name="Resumo (inglês)")

    # A imagem que abre a página. Opcional: uma página sem fotografia continua
    # a responder à pergunta de quem chegou, e uma fotografia escolhida à
    # pressa só para preencher o espaço vale menos do que nenhuma.
    hero_image = models.ImageField(
        blank=True,
        upload_to="o-que-tratamos/",
        verbose_name="Imagem de abertura",
        help_text=(
            "Aparece no topo da página e no card do índice. Larga e não alta "
            "— é recortada ao meio, e uma fotografia vertical perde as pontas."
        ),
    )

    # O texto alternativo não é um extra de acessibilidade que se acrescenta
    # depois: é o que descreve a imagem a quem não a vê e ao Google, que
    # também não a vê. Vazio, a página usa o nome do problema — pior do que
    # uma frase escrita, melhor do que um atributo em branco.
    hero_alt = models.CharField(
        max_length=180,
        blank=True,
        verbose_name="Descrição da imagem",
        help_text=(
            "O que se vê na fotografia, para quem não a consegue ver. Sem "
            "isto, a página usa o nome do problema."
        ),
    )

    # O texto da página, em HTML, escrito num editor.
    #
    # Eram cinco campos de texto — o que é, porque acontece, sinais de alerta,
    # como se trata, cuidados em casa — e a ordem era fixa. Isso dava páginas
    # consistentes e tirava-lhe a possibilidade de escrever uma tabela de
    # sintomas, uma fotografia a meio ou uma ligação para outra página. Quem
    # escreve estas páginas sabe o que cada uma precisa; a estrutura passou a
    # ser dela.
    #
    # **O que está aqui já vem limpo.** É `save()` que o garante, e é por isso
    # que a página o pode mostrar como HTML sem o escapar.
    body = models.TextField(
        blank=True,
        verbose_name="Texto da página",
        help_text=(
            "Escreva como escreveria num documento. Pode usar títulos, "
            "listas, tabelas, ligações e imagens."
        ),
    )

    body_en = models.TextField(blank=True, verbose_name="Texto da página (inglês)")

    # O título e a descrição que vão para o Google. Ficam à parte do nome e do
    # resumo porque respondem a outra coisa: o nome é para quem já está na
    # página, isto é para quem ainda está na lista de resultados a decidir se
    # clica. Vazios, a página usa o nome e o resumo, que é melhor do que uma
    # etiqueta em branco.
    meta_title = models.CharField(
        max_length=70,
        blank=True,
        verbose_name="Título para o Google",
        help_text="Até 60 caracteres é o que costuma aparecer inteiro.",
    )

    meta_description = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Descrição para o Google",
        help_text="Entre 120 e 155 caracteres é o que costuma aparecer inteiro.",
    )

    keywords = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Palavras-chave",
        help_text="Separadas por vírgulas.",
    )

    # As mesmas três, em inglês. Sem elas, uma página traduzida de alto a
    # baixo continuava a mostrar o separador do browser e o resultado da
    # pesquisa em português — que é onde quem procura em inglês a vê primeiro.
    # Uma imagem própria para a versão inglesa. Só faz falta quando o banner
    # tem texto escrito nele — e como tem, faz.
    hero_image_en = models.ImageField(
        blank=True,
        upload_to="o-que-tratamos/",
        verbose_name="Imagem de abertura (inglês)",
        help_text=(
            "Vazio usa a imagem portuguesa. Só vale a pena se o banner "
            "tiver texto escrito."
        ),
    )

    hero_alt_en = models.CharField(
        max_length=180, blank=True, verbose_name="Descrição da imagem (inglês)"
    )

    meta_title_en = models.CharField(
        max_length=70, blank=True, verbose_name="Título para o Google (inglês)"
    )

    meta_description_en = models.CharField(
        max_length=200, blank=True, verbose_name="Descrição para o Google (inglês)"
    )

    keywords_en = models.CharField(
        max_length=255, blank=True, verbose_name="Palavras-chave (inglês)"
    )

    # O serviço que se marca no fim da página. Opcional: há problemas que se
    # explicam antes de haver um serviço com nome próprio para eles, e uma
    # página sem serviço continua a valer — leva a pessoa à agenda geral.
    service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="treated_conditions",
        verbose_name="Serviço a propor",
    )

    display_order = models.PositiveIntegerField(default=0, verbose_name="Ordem")

    is_published = models.BooleanField(
        default=False,
        verbose_name="Publicado",
        help_text=(
            "Enquanto estiver desligado, a página não existe para ninguém — "
            "nem no site, nem no sitemap."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Problema tratado"
        verbose_name_plural = "Problemas tratados"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse(
            "appointments:treated_condition_detail",
            kwargs={"slug": self.slug},
        )

    @property
    def display_name(self):
        return get_localized_value(self.name, self.name_en)

    @property
    def display_summary(self):
        return get_localized_value(self.summary, self.summary_en)

    @property
    def display_hero(self):
        """A imagem de abertura desta língua, com a portuguesa como recurso.

        Uma página sem imagem é pior do que uma com a imagem da outra língua —
        e é por isso que cai. O que a queda custa está no `hero_carries_title`
        logo abaixo.
        """

        if get_language() and get_language().lower().startswith("en"):
            return self.hero_image_en or self.hero_image

        return self.hero_image

    @property
    def hero_carries_title(self):
        """Se o banner desta página traz o título escrito nele.

        O `<h1>` esconde-se quando há banner, porque o nome já vai lá escrito.
        Mas se a página inglesa estiver a usar o banner português, o nome que
        lá está escrito está em português — e esconder o `<h1>` inglês deixava
        o leitor inglês sem um título que conseguisse ler.

        Por isso é a imagem **desta** língua que decide, e não a que aparece.
        """

        if get_language() and get_language().lower().startswith("en"):
            return bool(self.hero_image_en)

        return bool(self.hero_image)

    @property
    def hero_description(self):
        """O texto alternativo da imagem, com o nome do problema como recurso.

        Um `alt` vazio numa imagem que carrega conteúdo diz a quem usa leitor
        de ecrã que ali não há nada — e ali há. O nome do problema não é uma
        boa descrição, mas é verdadeira.
        """

        return campo_da_lingua(self.hero_alt, self.hero_alt_en).strip() or (
            self.display_name
        )

    @property
    def display_body(self):
        """O texto da página, na língua dela, pronto a mostrar como HTML.

        Pode ir para o template com `|safe` porque o que está guardado já
        passou pelo `save()`: a limpeza é à entrada, e é a única forma de o
        que está na base de dados ser seguro em todos os sítios para onde for.
        """

        return get_localized_value(self.body, self.body_en)

    def has_body(self):
        """Se há texto a sério, e não um parágrafo vazio deixado pelo editor.

        Um editor por preencher devolve `<p><br></p>`, que passa por
        preenchido em qualquer verificação ingénua. É isto que impede publicar
        uma página em branco.
        """

        return not esta_vazio(self.display_body)

    def save(self, *args, **kwargs):
        """Limpa o HTML antes de ele chegar à base de dados.

        Aqui e não no formulário: um `loaddata`, uma migração ou uma sessão de
        `shell` também gravam, e nenhum deles passa por um formulário. O que
        fica guardado é seguro venha de onde vier.
        """

        self.body = limpar(self.body)
        self.body_en = limpar(self.body_en)

        super().save(*args, **kwargs)

    @property
    def display_keywords(self):
        return get_localized_value(self.keywords, self.keywords_en)

    def seo_title(self):
        return (
            campo_da_lingua(self.meta_title, self.meta_title_en).strip()
            or self.display_name
        )

    def seo_description(self):
        """A descrição para os resultados de pesquisa, na língua da página.

        Sem uma escrita à mão vale o resumo, cortado à palavra e não a meio
        dela: o Google corta o que passa dos ~155 caracteres, e um corte a
        meio de uma palavra é o que faz uma descrição parecer partida.
        """

        escrita = campo_da_lingua(
            self.meta_description, self.meta_description_en
        ).strip()

        if escrita:
            return escrita

        resumo = " ".join(self.display_summary.split())

        if len(resumo) <= 155:
            return resumo

        return resumo[:152].rsplit(" ", 1)[0] + "…"


class ConditionQuestion(models.Model):
    """Uma pergunta e a resposta dela, no fim da página do problema.

    Não é enfeite: é a parte da página que o Google mostra aberta nos
    resultados, e são as perguntas que as pessoas escrevem à letra na
    pesquisa. Uma pergunta sem resposta não vai para lado nenhum, por isso as
    duas são obrigatórias.
    """

    condition = models.ForeignKey(
        TreatedCondition,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="Problema",
    )

    question = models.CharField(max_length=200, verbose_name="Pergunta")
    question_en = models.CharField(
        max_length=200, blank=True, verbose_name="Pergunta (inglês)"
    )

    answer = models.TextField(verbose_name="Resposta")
    answer_en = models.TextField(blank=True, verbose_name="Resposta (inglês)")

    display_order = models.PositiveIntegerField(default=0, verbose_name="Ordem")

    class Meta:
        ordering = ["display_order", "id"]
        verbose_name = "Pergunta frequente"
        verbose_name_plural = "Perguntas frequentes"

    def __str__(self):
        return self.question

    @property
    def display_question(self):
        return get_localized_value(self.question, self.question_en)

    @property
    def display_answer(self):
        return get_localized_value(self.answer, self.answer_en)
