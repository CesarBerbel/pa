from django import forms
from django.contrib import admin
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html

from .models import (
    BeforeAfterCase,
    EmailEventSetting,
    EmailTemplate,
    InstagramPost,
    MessagingSetting,
    ServiceFollowUp,
    WhatsAppEventSetting,
    WhatsAppMessageLog,
)
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
    )

    list_filter = (
        "event_type",
        "is_active",
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
            "Controle",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )


@admin.register(WhatsAppMessageLog)
class WhatsAppMessageLogAdmin(admin.ModelAdmin):
    # Read-only audit screen for WhatsApp Cloud API sending attempts.

    list_display = (
        "sent_at",
        "appointment",
        "event_type",
        "provider",
        "status",
        "template_name",
        "recipient_phone",
        "whatsapp_message_id",
    )

    list_filter = (
        "status",
        "provider",
        "event_type",
        "template_name",
        "sent_at",
    )

    search_fields = (
        "appointment__reference_code",
        "appointment__customer__full_name",
        "recipient_phone",
        "whatsapp_message_id",
        "error_message",
    )

    readonly_fields = (
        "appointment",
        "event_type",
        "status",
        "template_name",
        "recipient_phone",
        "whatsapp_message_id",
        "request_payload",
        "response_payload",
        "error_message",
        "sent_at",
    )

    fieldsets = (
        (
            "Identificação",
            {
                "fields": (
                    "appointment",
                    "event_type",
                    "status",
                    "template_name",
                    "recipient_phone",
                    "whatsapp_message_id",
                    "sent_at",
                ),
            },
        ),
        (
            "Payloads e erro",
            {
                "fields": (
                    "request_payload",
                    "response_payload",
                    "error_message",
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        return False


class InstagramPostAdminForm(forms.ModelForm):
    class Meta:
        model = InstagramPost
        fields = "__all__"
        widgets = {
            "embed_code": forms.Textarea(attrs={"rows": 10}),
        }


@admin.register(InstagramPost)
class InstagramPostAdmin(admin.ModelAdmin):
    # Manual list of real Instagram posts, shown via Instagram's own embed
    # (blockquote + embed.js) in the homepage carousel.

    form = InstagramPostAdminForm

    list_display = (
        "post_link",
        "display_order",
        "is_active",
        "created_at",
    )

    list_display_links = ("post_link",)

    list_editable = (
        "display_order",
        "is_active",
    )

    list_filter = ("is_active",)

    search_fields = ("embed_code",)

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Publicação",
            {
                "fields": ("embed_code",),
                "description": (
                    'No Instagram, abra a publicação → "..." → Copiar código de '
                    "incorporação, e cole aqui o bloco inteiro."
                ),
            },
        ),
        (
            "Exibição",
            {
                "fields": (
                    "display_order",
                    "is_active",
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

    def post_link(self, obj):
        if not obj.permalink:
            return "(sem link identificado)"

        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>',
            obj.permalink,
            obj.permalink,
        )

    post_link.short_description = "Publicação"


@admin.register(ServiceFollowUp)
class ServiceFollowUpAdmin(admin.ModelAdmin):
    # A gestão do dia a dia é feita na área interna; o admin fica para
    # inspeção e correções pontuais.

    list_display = (
        "service",
        "trigger",
        "email_template",
        "days_after",
        "is_active",
    )

    list_filter = (
        "trigger",
        "is_active",
        "service",
    )

    search_fields = (
        "service__name",
        "email_template__name",
    )

    autocomplete_fields = ("email_template",)


@admin.register(WhatsAppEventSetting)
class WhatsAppEventSettingAdmin(admin.ModelAdmin):
    # A gestão do dia a dia é na área interna; aqui fica a inspeção.

    list_display = (
        "event_type",
        "audience",
        "is_active",
    )

    list_filter = (
        "event_type",
        "audience",
        "is_active",
    )


@admin.register(MessagingSetting)
class MessagingSettingAdmin(admin.ModelAdmin):
    # O sítio para mexer nisto é a área interna, em Configurações. Aqui fica
    # visível para inspeção e para o caso de a área interna estar inacessível.

    list_display = (
        "__str__",
        "send_emails",
        "send_whatsapp",
        "updated_by",
        "updated_at",
    )

    readonly_fields = ("updated_by", "updated_at")

    def has_add_permission(self, request):
        # Só existe uma linha, criada na primeira leitura.
        return not MessagingSetting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BeforeAfterCase)
class BeforeAfterCaseAdmin(admin.ModelAdmin):
    # A gestão do dia a dia é feita na área interna; isto é a porta de trás,
    # para quando é preciso ver ou corrigir um registo em bruto.

    list_display = ("title", "display_order", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("title", "caption", "title_en", "caption_en")
    ordering = ("display_order", "-created_at")
