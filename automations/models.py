from django.db import models

from businesses.models import Business


class EmailTemplate(models.Model):
    business = models.OneToOneField(
        Business,
        on_delete=models.CASCADE,
        related_name="email_template"
    )

    send_customer_email = models.BooleanField(
        default=True,
        verbose_name="Enviar email al cliente"
    )

    send_business_email = models.BooleanField(
        default=True,
        verbose_name="Enviar email al negocio"
    )

    customer_subject = models.CharField(
        max_length=200,
        default="Reserva confirmada en {business_name}",
        verbose_name="Asunto email cliente"
    )

    customer_body = models.TextField(
        default="""Hola {customer_name},

Tu reserva ha sido confirmada correctamente.

Detalles de la reserva:

Negocio: {business_name}
Servicio: {service_name}
Profesional: {employee_name}
Fecha: {booking_date}
Hora: {start_time}
Fin estimado: {end_time}

Gracias por reservar con nosotros.

Un saludo,
{business_name}
""",
        verbose_name="Mensaje email cliente"
    )

    business_subject = models.CharField(
        max_length=200,
        default="Nueva reserva recibida - {business_name}",
        verbose_name="Asunto email negocio"
    )

    business_body = models.TextField(
        default="""Hola {business_name},

Has recibido una nueva reserva.

Detalles de la reserva:

Cliente: {customer_name}
Teléfono: {customer_phone}
Email: {customer_email}

Servicio: {service_name}
Profesional: {employee_name}
Fecha: {booking_date}
Hora: {start_time}
Fin estimado: {end_time}

Estado: {booking_status}

Puedes verla desde tu panel de reservas.

Un saludo,
Sistema de reservas
""",
        verbose_name="Mensaje email negocio"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Plantilla emails - {self.business.name}"
