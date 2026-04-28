import random
import string
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

class Service(models.Model):
    # Represents a service offered by the business

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Customer(models.Model):
    # Represents a customer who can book appointments

    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30)
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

    def clean(self):
        # Validate that end time is after start time
        if self.end_time <= self.start_time:
            raise ValidationError("O horário final deve ser maior que o horário inicial.")


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
            item.strip()
            for item in self.recurring_weekdays.split(",")
            if item.strip()
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
                "Informe pelo menos um dia da semana para o bloqueio recorrente."
            )

        if self.is_full_day:
            return

        if not self.start_time or not self.end_time:
            raise ValidationError(
                "Informe o horário inicial e final ou marque como dia inteiro."
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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "start_time"]

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
        # Cancelled appointments do not need schedule validation
        if self.status == self.STATUS_CANCELLED:
            return

        if self.service and not self.service.is_active:
            raise ValidationError("Não é possível marcar horário para um serviço inativo.")

        if not self.date or not self.start_time or not self.service:
            return

        weekday = self.date.weekday()

        try:
            business_hour = BusinessHour.objects.get(
                weekday=weekday,
                is_active=True,
            )
        except BusinessHour.DoesNotExist:
            raise ValidationError(
                "Não há horário de funcionamento ativo para este dia."
            )

        appointment_start = self.get_start_datetime()
        appointment_end = self.get_end_datetime()

        business_start = datetime.combine(self.date, business_hour.start_time)
        business_end = datetime.combine(self.date, business_hour.end_time)

        if appointment_start < business_start or appointment_end > business_end:
            raise ValidationError(
                "A marcação está fora do horário de funcionamento."
            )

        active_blocks = [
            block
            for block in ScheduleBlock.objects.filter(is_active=True)
            if block.applies_to_date(self.date)
        ]

        for block in active_blocks:
            block_start = block.get_start_datetime_for_date(self.date)
            block_end = block.get_end_datetime_for_date(self.date)

            has_block_conflict = (
                appointment_start < block_end
                and appointment_end > block_start
            )

            if has_block_conflict:
                raise ValidationError(
                    f"Este horário está bloqueado: {block.title}."
                )

        appointments = Appointment.objects.filter(
            date=self.date,
        ).exclude(
            status=self.STATUS_CANCELLED,
        ).select_related(
            "service",
        )

        if self.pk:
            appointments = appointments.exclude(pk=self.pk)

        for appointment in appointments:
            existing_start = appointment.get_start_datetime()
            existing_end = appointment.get_end_datetime()

            has_conflict = (
                appointment_start < existing_end
                and appointment_end > existing_start
            )

            if has_conflict:
                raise ValidationError(
                    "Este horário entra em conflito com outra marcação existente."
                )

    def save(self, *args, **kwargs):
        # Auto-generate reference code before validation and saving
        if not self.reference_code:
            self.reference_code = self.generate_reference_code()

        self.full_clean()
        return super().save(*args, **kwargs)