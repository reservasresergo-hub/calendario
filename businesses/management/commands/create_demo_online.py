# -*- coding: utf-8 -*-
"""
Created on Wed Jun 10 09:51:48 2026

@author: PRL
"""

from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from businesses.models import Business
from services_app.models import Service
from employees.models import Employee, EmployeeService
from schedules.models import WeeklySchedule
from customers.models import Customer
from bookings.models import Booking


class Command(BaseCommand):
    help = "Crea una demo online de ReserGo."

    def handle(self, *args, **options):
        User = get_user_model()

        demo_email = "demo@resergo.es"
        demo_password = "DemoReserGo2026!"
        demo_slug = "demo-peluqueria"

        self.stdout.write("Creando usuario demo...")

        demo_user, created = User.objects.get_or_create(
            username=demo_email,
            defaults={
                "email": demo_email,
                "first_name": "Demo",
                "last_name": "ReserGo",
            }
        )

        demo_user.email = demo_email
        demo_user.first_name = "Demo"
        demo_user.last_name = "ReserGo"
        demo_user.is_staff = False
        demo_user.is_superuser = False
        demo_user.set_password(demo_password)
        demo_user.save()

        self.stdout.write("Creando negocio demo...")

        business, created = Business.objects.get_or_create(
            slug=demo_slug,
            defaults={
                "owner": demo_user,
                "name": "Demo Peluquería",
                "phone": "600000000",
                "email": demo_email,
            }
        )

        business.owner = demo_user
        business.name = "Demo Peluquería"
        business.phone = "600000000"
        business.email = demo_email
        business.save()

        self.stdout.write("Limpiando datos demo anteriores...")

        Booking.objects.filter(business=business).delete()
        Customer.objects.filter(business=business).delete()
        EmployeeService.objects.filter(employee__business=business).delete()
        WeeklySchedule.objects.filter(employee__business=business).delete()
        Employee.objects.filter(business=business).delete()
        Service.objects.filter(business=business).delete()

        self.stdout.write("Creando servicios demo...")

        services_data = [
            ("Corte mujer", 45, 25),
            ("Corte hombre", 30, 15),
            ("Peinado", 45, 22),
            ("Tinte", 90, 45),
            ("Mechas", 120, 70),
        ]

        services = []

        for name, duration, price in services_data:
            service = Service.objects.create(
                business=business,
                name=name,
                duration_minutes=duration,
                price=price,
                active=True,
            )
            services.append(service)

        self.stdout.write("Creando empleados demo...")

        employees = []

        for employee_name in ["Ana", "Lucía", "Mario"]:
            employee = Employee.objects.create(
                business=business,
                full_name=employee_name,
                active=True,
            )
            employees.append(employee)

        self.stdout.write("Asignando servicios a empleados...")

        for employee in employees:
            for service in services:
                EmployeeService.objects.create(
                    employee=employee,
                    service=service,
                )

        self.stdout.write("Creando horarios demo...")

        for employee in employees:
            for weekday in range(0, 6):
                WeeklySchedule.objects.create(
                    employee=employee,
                    weekday=weekday,
                    start_time_morning=time(9, 0),
                    end_time_morning=time(14, 0),
                    start_time_afternoon=time(16, 0),
                    end_time_afternoon=time(20, 0),
                    active=True,
                )

        self.stdout.write("Creando clientes demo...")

        customers = []

        for i in range(1, 21):
            customer = Customer.objects.create(
                business=business,
                full_name=f"Cliente Demo {i}",
                phone=f"600000{i:03d}",
                email=f"cliente.demo.{i}@example.com",
            )
            customers.append(customer)

        self.stdout.write("Creando reservas demo...")

        week_start = date(2026, 5, 25)

        demo_times = [
            time(9, 0),
            time(10, 0),
            time(11, 30),
            time(16, 0),
            time(17, 30),
            time(18, 30),
        ]

        booking_count = 0

        for day_offset in range(0, 6):
            current_date = week_start + timedelta(days=day_offset)

            for index, start_time in enumerate(demo_times):
                employee = employees[index % len(employees)]
                service = services[index % len(services)]
                customer = customers[
                    (day_offset * len(demo_times) + index) % len(customers)
                ]

                Booking.objects.create(
                    business=business,
                    customer=customer,
                    employee=employee,
                    service=service,
                    booking_date=current_date,
                    start_time=start_time,
                    status="confirmed",
                    notes="Reserva de demostración",
                )

                booking_count += 1

        self.stdout.write(self.style.SUCCESS("Demo online creada correctamente."))
        self.stdout.write("")
        self.stdout.write("Datos de acceso:")
        self.stdout.write(f"Email: {demo_email}")
        self.stdout.write(f"Contraseña: {demo_password}")
        self.stdout.write("")
        self.stdout.write("URLs:")
        self.stdout.write(f"Panel demo: /login/")
        self.stdout.write(f"Web pública demo: /{demo_slug}/")
        self.stdout.write(f"Reservas creadas: {booking_count}")