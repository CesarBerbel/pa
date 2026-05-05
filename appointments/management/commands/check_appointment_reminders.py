from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from appointments.models import Appointment


class Command(BaseCommand):
    # Shows diagnostic information about appointment reminders without sending emails.

    help = "Check appointment reminders status without sending emails"

    def handle(self, *args, **kwargs):
        now = timezone.localtime()

        self.stdout.write("")
        self.stdout.write(self.style.WARNING("Appointment reminders diagnostic"))
        self.stdout.write(f"Current time: {now.strftime('%d/%m/%Y %H:%M')}")
        self.stdout.write("")

        reminder_rules = [
            {
                "label": "24h",
                "target_start": now + timedelta(hours=23),
                "target_end": now + timedelta(hours=25),
                "sent_field": "reminder_24h_sent_at",
            },
            {
                "label": "2h",
                "target_start": now + timedelta(hours=1, minutes=45),
                "target_end": now + timedelta(hours=2, minutes=15),
                "sent_field": "reminder_2h_sent_at",
            },
        ]

        for rule in reminder_rules:
            self.show_rule_diagnostic(rule)

        self.show_ignored_appointments()

    def show_rule_diagnostic(self, rule):
        # Shows appointments eligible or already processed for one reminder rule.
        label = rule["label"]
        target_start = rule["target_start"]
        target_end = rule["target_end"]
        sent_field = rule["sent_field"]

        self.stdout.write(self.style.SUCCESS(f"Reminder window: {label}"))
        self.stdout.write(
            f"Window: {target_start.strftime('%d/%m/%Y %H:%M')} "
            f"to {target_end.strftime('%d/%m/%Y %H:%M')}"
        )

        appointments = (
            Appointment.objects.filter(
                status=Appointment.STATUS_CONFIRMED,
                date=target_start.date(),
            )
            .select_related(
                "customer",
                "service",
            )
            .order_by(
                "date",
                "start_time",
            )
        )

        eligible_count = 0
        already_sent_count = 0

        for appointment in appointments:
            appointment_datetime = timezone.make_aware(
                timezone.datetime.combine(
                    appointment.date,
                    appointment.start_time,
                ),
                timezone.get_current_timezone(),
            )

            if not target_start <= appointment_datetime <= target_end:
                continue

            sent_at = getattr(appointment, sent_field)

            if sent_at:
                already_sent_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"[ALREADY SENT] {appointment.reference_code} | "
                        f"{appointment.customer.full_name} | "
                        f"{appointment.service.name} | "
                        f"{appointment_datetime.strftime('%d/%m/%Y %H:%M')} | "
                        f"sent at {timezone.localtime(sent_at).strftime('%d/%m/%Y %H:%M')}"
                    )
                )
            else:
                eligible_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[ELIGIBLE] {appointment.reference_code} | "
                        f"{appointment.customer.full_name} | "
                        f"{appointment.service.name} | "
                        f"{appointment_datetime.strftime('%d/%m/%Y %H:%M')}"
                    )
                )

        if eligible_count == 0 and already_sent_count == 0:
            self.stdout.write("No appointments found for this reminder window.")

        self.stdout.write(
            f"Summary {label}: {eligible_count} eligible, {already_sent_count} already sent."
        )
        self.stdout.write("")

    def show_ignored_appointments(self):
        # Shows appointments that will not receive reminders because of their status.
        now = timezone.localtime()
        tomorrow = now.date() + timedelta(days=1)

        ignored_appointments = (
            Appointment.objects.filter(
                date__in=[
                    now.date(),
                    tomorrow,
                ],
            )
            .exclude(
                status=Appointment.STATUS_CONFIRMED,
            )
            .select_related(
                "customer",
                "service",
            )
            .order_by(
                "date",
                "start_time",
            )
        )

        self.stdout.write(self.style.WARNING("Ignored appointments"))
        self.stdout.write("Only confirmed appointments receive reminders.")

        if not ignored_appointments.exists():
            self.stdout.write("No ignored appointments found.")
            self.stdout.write("")
            return

        for appointment in ignored_appointments:
            self.stdout.write(
                f"[IGNORED] {appointment.reference_code} | "
                f"{appointment.customer.full_name} | "
                f"{appointment.service.name} | "
                f"{appointment.date.strftime('%d/%m/%Y')} "
                f"{appointment.start_time.strftime('%H:%M')} | "
                f"status: {appointment.get_status_display()}"
            )

        self.stdout.write("")
