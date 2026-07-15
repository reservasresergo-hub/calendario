from django.db import models
from employees.models import Employee
from businesses.models import Business


class WeeklySchedule(models.Model):
    WEEKDAY_CHOICES = [
        (0, 'Lunes'),
        (1, 'Martes'),
        (2, 'Miércoles'),
        (3, 'Jueves'),
        (4, 'Viernes'),
        (5, 'Sábado'),
        (6, 'Domingo'),
    ]

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='weekly_schedules'
    )
    weekday = models.IntegerField(choices=WEEKDAY_CHOICES)

    start_time_morning = models.TimeField(blank=True, null=True)
    end_time_morning = models.TimeField(blank=True, null=True)
    
    start_time_afternoon = models.TimeField(blank=True, null=True)
    end_time_afternoon = models.TimeField(blank=True, null=True)

    active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.employee.full_name} - {self.get_weekday_display()}"


class BlockedSlot(models.Model):
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="blocked_slots"
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="blocked_slots"
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "start_time"]

    def __str__(self):
        return f"{self.employee.full_name} bloqueado {self.date} {self.start_time}-{self.end_time}"
    