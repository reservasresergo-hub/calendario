import uuid

from django.db import models
from businesses.models import Business
from customers.models import Customer
from employees.models import Employee
from services_app.models import Service
from datetime import datetime, timedelta


class Booking(models.Model):
    STATUS_CHOICES = [
        ('confirmed', 'Confirmada'),
        ('cancelled', 'Cancelada'),
        ('completed', 'Completada'),
    ]

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name='bookings'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='bookings'
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='bookings'
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='bookings'
    )

    booking_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='confirmed'
    )

    cancel_token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        null=True,
        blank=True
    )

    notes = models.TextField(blank=True, null=True)
    source = models.CharField(max_length=30, default='admin')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.cancel_token:
            self.cancel_token = uuid.uuid4()

        if self.start_time and self.service:
            start_dt = datetime.combine(self.booking_date, self.start_time)
            end_dt = start_dt + timedelta(minutes=self.service.duration_minutes)
            self.end_time = end_dt.time()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.booking_date} {self.start_time} - {self.customer.full_name}"