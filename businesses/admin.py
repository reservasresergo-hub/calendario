from django.contrib import admin
from .models import Business


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "owner", "theme", "phone", "email", "created_at")
    search_fields = ("name", "slug", "phone", "email")
    list_filter = ("theme", "owner")