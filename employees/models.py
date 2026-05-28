from django.db import models
from businesses.models import Business
from services_app.models import Service


class Employee(models.Model):
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name='employees'
    )
    full_name = models.CharField(max_length=150)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} - {self.business.name}"
class EmployeeService(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='employee_services'
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='service_employees'
    )

    class Meta:
        unique_together = ('employee', 'service')

    def __str__(self):
        return f"{self.employee.full_name} -> {self.service.name}"