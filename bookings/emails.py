from django.core.mail import send_mail
from django.conf import settings
from django.db import close_old_connections
import logging
import threading

from automations.models import EmailTemplate

logger = logging.getLogger(__name__)


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

    Importante:
    - Si el cliente no tiene email, no envía nada.
    - Si el negocio tiene desactivado el email al cliente, no envía nada.
    - Si Brevo/SMTP falla, NO rompe la reserva.
    - Devuelve True si se envía correctamente.
    - Devuelve False si no se envía o falla.
    """

    customer = booking.customer
    business = booking.business

    if not customer.email:
        logger.info(
            "Reserva %s sin email de cliente. No se envía confirmación.",
            booking.id
        )
        return False

    template = get_or_create_email_template(business)

    if not template.send_customer_email:
        logger.info(
            "El negocio %s tiene desactivado el email al cliente. Reserva %s.",
            business.id,
            booking.id
        )
        return False

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

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[customer.email],
            fail_silently=False,
        )

        logger.info(
            "Email de confirmación enviado correctamente. Reserva %s. Cliente: %s",
            booking.id,
            customer.email
        )

        return True

    except Exception:
        logger.exception(
            "Error enviando email de confirmación. Reserva %s. Cliente: %s",
            booking.id,
            customer.email
        )

        return False


def send_booking_emails(booking, cancel_url=""):
    """
    Envía los emails asociados a una nueva reserva.

    Decisión actual de ReserGo:
    - Se envía email de confirmación al cliente.
    - No se envía email al negocio.

    Importante:
    - Esta función nunca debe romper la creación de una reserva.
    - Si el email falla, se registra el error en logs y devuelve False.
    """

    try:
        customer_email_sent = send_booking_confirmation_email(
            booking,
            cancel_url=cancel_url
        )

        return customer_email_sent

    except Exception:
        logger.exception(
            "Error general enviando emails de la reserva %s",
            booking.id
        )

        return False


def send_booking_emails_async(booking, cancel_url=""):
    """
    Igual que send_booking_emails(), pero sin hacer esperar al cliente
    mientras se manda el correo.

    Por qué existe esto: mandar un email por SMTP tarda unos segundos
    (la conexión con Brevo). Antes, ese tiempo se sumaba directamente
    a la respuesta que recibía el cliente al confirmar su reserva —
    y, como el servidor solo atiende una petición a la vez, mientras
    tanto CUALQUIER otro visitante de CUALQUIER negocio se quedaba
    esperando también, aunque solo quisiera mirar la web.

    Con esto, la reserva se confirma al cliente al instante, y el
    email se manda por detrás, en un hilo aparte, sin bloquear a nadie
    más. Si el envío falla, sigue registrándose en los logs exactamente
    igual que antes (toda la lógica de aviso ya vive dentro de
    send_booking_emails() y no cambia).
    """

    def _enviar_en_segundo_plano():
        try:
            send_booking_emails(booking, cancel_url=cancel_url)
        finally:
            # Cada hilo nuevo abre su propia conexión a la base de
            # datos si la necesita (aquí, para leer la plantilla de
            # email). Sin cerrarla explícitamente al terminar, esas
            # conexiones se quedarían acumulando poco a poco.
            close_old_connections()

    thread = threading.Thread(target=_enviar_en_segundo_plano, daemon=True)
    thread.start()