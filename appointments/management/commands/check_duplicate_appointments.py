from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from appointments.models import Appointment


class Command(BaseCommand):
    # Reports active appointments that share the same date and start time.
    # Run this before applying the unique slot constraint: existing duplicates
    # make the migration fail, and each one needs a manual decision.

    help = (
        "Report active appointments sharing the same date and start time. "
        "Exits with an error when duplicates are found."
    )

    def handle(self, *args, **options):
        duplicated_slots = list(
            Appointment.objects.exclude(status=Appointment.STATUS_CANCELLED)
            .values("date", "start_time")
            .annotate(total=Count("id"))
            .filter(total__gt=1)
            .order_by("date", "start_time")
        )

        if not duplicated_slots:
            self.stdout.write(
                self.style.SUCCESS(
                    "No duplicated active appointments found. "
                    "The unique slot constraint can be applied safely."
                )
            )
            return

        for slot in duplicated_slots:
            self.stdout.write(
                self.style.WARNING(
                    f"{slot['date']} {slot['start_time']} "
                    f"-> {slot['total']} active appointments"
                )
            )

            appointments = (
                Appointment.objects.filter(
                    date=slot["date"],
                    start_time=slot["start_time"],
                )
                .exclude(status=Appointment.STATUS_CANCELLED)
                .select_related("customer", "service")
                .order_by("created_at")
            )

            for appointment in appointments:
                self.stdout.write(
                    f"    {appointment.reference_code} | "
                    f"{appointment.get_status_display()} | "
                    f"{appointment.customer.full_name} | "
                    f"{appointment.service.name} | "
                    f"created at {appointment.created_at:%Y-%m-%d %H:%M}"
                )

        raise CommandError(
            f"{len(duplicated_slots)} slot(s) with duplicated active appointments. "
            "Cancel or reschedule the extra appointments before migrating."
        )
