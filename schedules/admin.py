from django.contrib import admin
from .models import WeeklySchedule, BlockedSlot


@admin.register(WeeklySchedule)
class WeeklyScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "weekday",
        "start_time_morning",
        "end_time_morning",
        "start_time_afternoon",
        "end_time_afternoon",
        "active",
    )
    list_filter = ("weekday", "active", "employee")


@admin.register(BlockedSlot)
class BlockedSlotAdmin(admin.ModelAdmin):
    list_display = (
        "business",
        "employee",
        "date",
        "start_time",
        "end_time",
        "created_at",
    )
    list_filter = ("business", "employee", "date")