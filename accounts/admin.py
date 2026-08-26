from django.contrib import admin

from .models import LoginAttempt


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("username", "attempted_at")
    list_filter = ("username",)
    ordering = ("-attempted_at",)
