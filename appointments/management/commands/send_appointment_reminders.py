from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from appointments.emails import send_appointment_reminder_email
from appointments.models import Appointment


class Command(BaseCommand):
    # Sends appointment reminder emails with independent 24h and 2h controls.

    help = "Send appointment reminder emails"

    def handle(self, *args, **kwargs):
        now = timezone.localtime()

        reminder_rules = [
            {
                "label": "24 horas antes",
                "target_start": now + timedelta(hours=23),
                "target_end": now + timedelta(hours=25),
                "sent_field": "reminder_24h_sent_at",
            },
            {
                "label": "2 horas antes",
                "target_start": now + timedelta(hours=1, minutes=45),
                "target_end": now + timedelta(hours=2, minutes=15),
                "sent_field": "reminder_2h_sent_at",
            },
        ]

        total_sent_count = 0

        for rule in reminder_rules:
            sent_count = self.send_reminders_for_rule(rule)
            total_sent_count += sent_count

        self.stdout.write(
            self.style.SUCCESS(
                f"{total_sent_count} reminder(s) sent successfully."
            )
        )

    def send_reminders_for_rule(self, rule):
        # Sends reminders for one configured reminder window.
        target_start = rule["target_start"]
        target_end = rule["target_end"]
        sent_field = rule["sent_field"]
        label = rule["label"]

        filter_kwargs = {
            "status": Appointment.STATUS_CONFIRMED,
            "date": target_start.date(),
            f"{sent_field}__isnull": True,
        }

        appointments = Appointment.objects.filter(
            **filter_kwargs
        ).select_related(
            "customer",
            "service",
        )

        sent_count = 0

        for appointment in appointments:
            appointment_datetime = timezone.make_aware(
                timezone.datetime.combine(
                    appointment.date,
                    appointment.start_time,
                ),
                timezone.get_current_timezone(),
            )

            if target_start <= appointment_datetime <= target_end:
                send_appointment_reminder_email(
                    appointment=appointment,
                    reminder_label=label,
                )

                setattr(appointment, sent_field, timezone.now())
                appointment.save(update_fields=[sent_field])

                sent_count += 1

        return sent_count