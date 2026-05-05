from appointments.models import AppointmentLog


class AppointmentAuditService:
    # Centralizes appointment audit log creation.

    @staticmethod
    def log(appointment, action, user=None, description=""):
        # Create an audit log entry for appointment changes.
        return AppointmentLog.objects.create(
            appointment=appointment,
            action=action,
            performed_by=user if user and user.is_authenticated else None,
            description=description,
        )
