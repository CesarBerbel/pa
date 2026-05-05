from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from appointments.emails import send_appointment_reminder_email
from appointments.models import Appointment, AppointmentReminderLog
from notifications.models import EmailEventSetting
from notifications.services import EmailEventSettingService


class Command(BaseCommand):
    # Sends appointment reminder emails using reminder settings configured in admin.

    help = "Send appointment reminder emails"

    def handle(self, *args, **kwargs):
        reminder_settings = list(
            EmailEventSettingService.get_active_reminder_settings()
        )

        if not reminder_settings:
            self.stdout.write(
                self.style.WARNING(
                    "No active appointment reminder email settings found."
                )
            )
            return

        total_sent_count = 0

        for reminder_setting in reminder_settings:
            total_sent_count += self.send_reminders_for_setting(reminder_setting)

        self.stdout.write(
            self.style.SUCCESS(f"{total_sent_count} reminder(s) sent successfully.")
        )

    def send_reminders_for_setting(self, reminder_setting):
        # Sends reminders for one configured reminder rule.
        now = timezone.localtime()
        lead_delta = self.get_lead_delta(reminder_setting)
        target_datetime = now + lead_delta
        target_start = target_datetime - timedelta(
            minutes=reminder_setting.window_before_minutes,
        )
        target_end = target_datetime + timedelta(
            minutes=reminder_setting.window_after_minutes,
        )
        reminder_type = reminder_setting.get_log_key()
        reminder_label = reminder_setting.get_lead_time_label()

        appointments = Appointment.objects.filter(
            status=Appointment.STATUS_CONFIRMED,
            date__gte=target_start.date(),
            date__lte=target_end.date(),
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

            if not target_start <= appointment_datetime <= target_end:
                continue

            already_sent = AppointmentReminderLog.objects.filter(
                appointment=appointment,
                reminder_type=reminder_type,
                status=AppointmentReminderLog.STATUS_SUCCESS,
            ).exists()

            if already_sent:
                continue

            try:
                send_appointment_reminder_email(
                    appointment=appointment,
                    reminder_label=reminder_label,
                    email_template=reminder_setting.email_template,
                )

                self.mark_legacy_reminder_field(
                    appointment=appointment,
                    reminder_setting=reminder_setting,
                )

                AppointmentReminderLog.objects.create(
                    appointment=appointment,
                    reminder_type=reminder_type,
                    status=AppointmentReminderLog.STATUS_SUCCESS,
                )

                sent_count += 1

            except Exception as error:
                AppointmentReminderLog.objects.create(
                    appointment=appointment,
                    reminder_type=reminder_type,
                    status=AppointmentReminderLog.STATUS_ERROR,
                    error_message=str(error),
                )

                self.stdout.write(
                    self.style.ERROR(
                        f"Failed to send {reminder_label} reminder for "
                        f"{appointment.reference_code}: {error}"
                    )
                )

        return sent_count

    def get_lead_delta(self, reminder_setting):
        # Converts the admin reminder setting into a timedelta.
        if reminder_setting.lead_time_unit == EmailEventSetting.LEAD_TIME_UNIT_DAYS:
            return timedelta(days=reminder_setting.lead_time_value)

        return timedelta(hours=reminder_setting.lead_time_value)

    def mark_legacy_reminder_field(self, appointment, reminder_setting):
        # Keeps old reminder fields compatible for existing screens and diagnostics.
        update_fields = []

        if (
            reminder_setting.lead_time_value == 1
            and reminder_setting.lead_time_unit == EmailEventSetting.LEAD_TIME_UNIT_DAYS
            and not appointment.reminder_24h_sent_at
        ):
            appointment.reminder_24h_sent_at = timezone.now()
            update_fields.append("reminder_24h_sent_at")

        if (
            reminder_setting.lead_time_value == 2
            and reminder_setting.lead_time_unit
            == EmailEventSetting.LEAD_TIME_UNIT_HOURS
            and not appointment.reminder_2h_sent_at
        ):
            appointment.reminder_2h_sent_at = timezone.now()
            update_fields.append("reminder_2h_sent_at")

        if update_fields:
            appointment.save(update_fields=update_fields)
