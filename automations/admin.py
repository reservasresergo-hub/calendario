from django.contrib import admin
from .models import EmailTemplate


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "business",
        "send_customer_email",
        "send_business_email",
        "updated_at",
    )

    fieldsets = (
        ("Negocio", {
            "fields": ("business",)
        }),
        ("Activación de emails", {
            "fields": (
                "send_customer_email",
                "send_business_email",
            )
        }),
        ("Email al cliente", {
            "fields": (
                "customer_subject",
                "customer_body",
            )
        }),
        ("Email al negocio", {
            "fields": (
                "business_subject",
                "business_body",
            )
        }),
    )