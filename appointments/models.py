import random
import string
from datetime import datetime, timedelta
from decimal import Decimal
from django.core.validators import MinValueValidator

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import get_language


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
    )

    name = models.CharField(max_length=120)
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

    duration_minutes = models.PositiveIntegerField(
        default=60,
        validators=[
            MinValueValidator(1),
        ],
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
    )

    is_active = models.BooleanField(default=True)

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

    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30)

    is_guest = models.BooleanField(
        default=False,
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_profile",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


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

    weekday = models.IntegerField(choices=WEEKDAY_CHOICES, unique=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["weekday"]

    def __str__(self):
        return f"{self.get_weekday_display()} - {self.start_time} às {self.end_time}"

    @property
    def duration_minutes(self):
        # Return gross working duration in minutes for display purposes.
        if not self.start_time or not self.end_time:
            return 0

        start_datetime = datetime.combine(datetime.today(), self.start_time)
        end_datetime = datetime.combine(datetime.today(), self.end_time)

        return int((end_datetime - start_datetime).total_seconds() / 60)

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
        # Validate that end time is after start time
        if self.end_time <= self.start_time:
            raise ValidationError(
                "O horário final deve ser maior que o horário inicial."
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

    title = models.CharField(max_length=120)
    block_type = models.CharField(
        max_length=20,
        choices=BLOCK_TYPE_CHOICES,
        default=BLOCK_TYPE_OTHER,
    )
    date = models.DateField(
        help_text="Use this date for a single block or as the recurrence start date."
    )
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    is_full_day = models.BooleanField(default=False)

    is_recurring = models.BooleanField(default=False)
    recurring_weekdays = models.CharField(
        max_length=20,
        blank=True,
        help_text="Comma-separated weekdays. Example: 0,1,2,3,4",
    )
    recurrence_end_date = models.DateField(blank=True, null=True)

    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "start_time"]

    def __str__(self):
        return f"{self.title} - {self.date}"

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

    def clean(self):
        # Validate schedule block consistency
        if self.is_recurring and not self.recurring_weekdays:
            raise ValidationError(
                "Indique pelo menos um dia da semana para o bloqueio recorrente."
            )

        if self.is_full_day:
            return

        if not self.start_time or not self.end_time:
            raise ValidationError(
                "Indique o horário inicial e final ou marque como dia inteiro."
            )

        if self.end_time <= self.start_time:
            raise ValidationError(
                "O horário final do bloqueio deve ser maior que o horário inicial."
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
    )

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="appointments",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="appointments",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_appointments",
    )

    date = models.DateField()
    start_time = models.TimeField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_SCHEDULED,
    )

    notes = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)

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
        # Generate unique professional reference code
        while True:
            random_code = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=6)
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

    def clean(self):
        # Keep model validation as a thin delegate to the domain availability policy.
        from appointments.availability import AvailabilityService

        AvailabilityService.validate_appointment(self)

    def save(self, *args, **kwargs):
        # Auto-generate reference code before validation and saving
        if not self.reference_code:
            self.reference_code = self.generate_reference_code()

        self.full_clean()
        return super().save(*args, **kwargs)


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

    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.appointment.reference_code} - {self.action}"


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
