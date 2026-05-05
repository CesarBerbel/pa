from django.contrib import admin
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html

from .models import EmailEventSetting, EmailTemplate
from .services import EmailTemplateService


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    # Admin configuration for editable email templates.

    list_display = (
        "name",
        "key",
        "is_active",
        "preview_link",
    )

    search_fields = (
        "name",
        "key",
    )

    list_filter = ("is_active",)

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Identificação",
            {
                "fields": (
                    "name",
                    "key",
                    "is_active",
                ),
            },
        ),
        (
            "Conteúdo",
            {
                "fields": (
                    "subject",
                    "body_text",
                    "body_html",
                ),
            },
        ),
        (
            "Controle",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    def get_urls(self):
        # Adds custom admin URL for email template preview.
        urls = super().get_urls()

        custom_urls = [
            path(
                "<int:template_id>/preview/",
                self.admin_site.admin_view(self.preview_view),
                name="notifications_emailtemplate_preview",
            ),
        ]

        return custom_urls + urls

    def preview_link(self, obj):
        # Shows a direct preview button in the admin list.
        url = reverse(
            "admin:notifications_emailtemplate_preview",
            kwargs={
                "template_id": obj.pk,
            },
        )

        return format_html(
            '<a class="button" href="{}" target="_blank">Preview</a>',
            url,
        )

    preview_link.short_description = "Preview"

    def preview_view(self, request, template_id):
        # Renders the selected email template using sample data.
        email_template = get_object_or_404(
            EmailTemplate,
            pk=template_id,
        )

        sample_context = EmailTemplateService.get_sample_context()

        rendered_email = EmailTemplateService.render_template_object(
            email_template=email_template,
            context_data=sample_context,
        )

        context = {
            **self.admin_site.each_context(request),
            "title": f"Preview: {email_template.name}",
            "email_template": email_template,
            "rendered_email": rendered_email,
            "sample_context": sample_context,
        }

        return render(
            request,
            "admin/notifications/emailtemplate/preview.html",
            context,
        )


@admin.register(EmailEventSetting)
class EmailEventSettingAdmin(admin.ModelAdmin):
    # Admin configuration for email event rules.

    list_display = (
        "name",
        "event_type",
        "is_active",
        "email_template",
        "lead_time_display",
        "window_display",
    )

    list_filter = (
        "event_type",
        "is_active",
        "lead_time_unit",
    )

    search_fields = (
        "name",
        "email_template__name",
        "email_template__key",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Ação de email",
            {
                "fields": (
                    "name",
                    "event_type",
                    "is_active",
                    "email_template",
                ),
            },
        ),
        (
            "Configuração de aviso antes da marcação",
            {
                "fields": (
                    "lead_time_value",
                    "lead_time_unit",
                    "window_before_minutes",
                    "window_after_minutes",
                ),
                "description": "Use estes campos apenas quando a ação for 'Lembrete antes da marcação'.",
            },
        ),
        (
            "Controle",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    def lead_time_display(self, obj):
        if obj.event_type != EmailEventSetting.EVENT_APPOINTMENT_REMINDER:
            return "-"

        return obj.get_lead_time_label()

    lead_time_display.short_description = "Aviso"

    def window_display(self, obj):
        if obj.event_type != EmailEventSetting.EVENT_APPOINTMENT_REMINDER:
            return "-"

        return f"-{obj.window_before_minutes} min / +{obj.window_after_minutes} min"

    window_display.short_description = "Janela de envio"
