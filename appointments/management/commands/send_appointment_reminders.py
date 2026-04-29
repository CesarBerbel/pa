from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from appointments.models import Appointment
from appointments.emails import send_appointment_reminder_email


class Command(BaseCommand):
    # Sends reminder emails for upcoming appointments.

    help = "Send appointment reminder emails"

    def handle(self, *args, **kwargs):
        now = timezone.now()

        target_start = now + timedelta(hours=23)
        target_end = now + timedelta(hours=25)

        appointments = Appointment.objects.filter(
            status=Appointment.STATUS_CONFIRMED,
            date=target_start.date(),
            reminder_sent_at__isnull=True,  # 🚀 evita duplicidade
        )

        sent_count = 0

        for appointment in appointments:
            appointment_datetime = timezone.make_aware(
                timezone.datetime.combine(
                    appointment.date,
                    appointment.start_time,
                )
            )

            if target_start <= appointment_datetime <= target_end:
                send_appointment_reminder_email(appointment)

                # ✅ marca como enviado
                appointment.reminder_sent_at = timezone.now()
                appointment.save(update_fields=["reminder_sent_at"])

                sent_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{sent_count} reminder(s) sent successfully."
            )
        )