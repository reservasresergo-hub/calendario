from django.core.mail import send_mail
from django.conf import settings

from automations.models import EmailTemplate


def get_booking_email_context(booking, cancel_url=""):
    """
    Crea el diccionario de variables disponibles para las plantillas de email.
    """

    customer = booking.customer
    business = booking.business
    service = booking.service
    employee = booking.employee

    return {
        "business_name": business.name,
        "business_email": business.email or "",
        "business_phone": business.phone or "",

        "customer_name": customer.full_name,
        "customer_phone": customer.phone,
        "customer_email": customer.email or "No indicado",

        "service_name": service.name,
        "employee_name": employee.full_name,

        "booking_date": booking.booking_date.strftime("%d/%m/%Y"),
        "start_time": booking.start_time.strftime("%H:%M"),
        "end_time": booking.end_time.strftime("%H:%M") if booking.end_time else "",
        "booking_status": booking.status,

        "cancel_url": cancel_url or "",
    }


def render_template_text(template_text, context):
    """
    Sustituye variables tipo {customer_name}, {business_name}, etc.
    """

    try:
        return template_text.format(**context)
    except KeyError as e:
        missing_key = str(e).replace("'", "")
        return (
            template_text
            + f"\n\n[ERROR: falta la variable {{{missing_key}}} en la plantilla]"
        )


def get_or_create_email_template(business):
    """
    Devuelve la plantilla de emails de un negocio.
    Si no existe, la crea automáticamente con textos por defecto.
    """

    template, created = EmailTemplate.objects.get_or_create(
        business=business
    )

    return template


def add_cancel_url_if_needed(message, template_body, cancel_url):
    """
    Añade el enlace de cancelación al final del email del cliente
    si existe cancel_url y la plantilla no lo incluye ya con {cancel_url}.
    """

    if not cancel_url:
        return message

    if "{cancel_url}" in template_body:
        return message

    return (
        message
        + "\n\n"
        + "Si necesitas cancelar tu reserva, puedes hacerlo desde este enlace:\n"
        + cancel_url
    )


def send_booking_confirmation_email(booking, cancel_url=""):
    """
    Envía email editable de confirmación al cliente.
    """

    customer = booking.customer
    business = booking.business

    if not customer.email:
        return

    template = get_or_create_email_template(business)

    if not template.send_customer_email:
        return

    context = get_booking_email_context(
        booking,
        cancel_url=cancel_url
    )

    subject = render_template_text(
        template.customer_subject,
        context
    )

    message = render_template_text(
        template.customer_body,
        context
    )

    message = add_cancel_url_if_needed(
        message=message,
        template_body=template.customer_body,
        cancel_url=cancel_url
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[customer.email],
        fail_silently=False,
    )


def send_booking_emails(booking, cancel_url=""):
    """
    Envía los emails asociados a una nueva reserva.

    Decisión actual de ReserGo:
    - Se envía email de confirmación al cliente.
    - No se envía email al negocio.
    """

    send_booking_confirmation_email(
        booking,
        cancel_url=cancel_url
    )