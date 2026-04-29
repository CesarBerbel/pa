from django.db import models


class EmailTemplate(models.Model):
    # Stores customizable email templates editable via admin.

    key = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique identifier, e.g. appointment_cancelled",
    )

    name = models.CharField(
        max_length=150,
        help_text="Human-readable name",
    )

    subject = models.CharField(
        max_length=255,
    )

    body_text = models.TextField()

    body_html = models.TextField(
        blank=True,
        help_text="Optional HTML version of the email",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name