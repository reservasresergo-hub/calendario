from datetime import datetime, timedelta
import logging

from django.db import transaction, IntegrityError, OperationalError
from django.shortcuts import render, get_object_or_404
from django.urls import reverse

from businesses.models import Business
from services_app.models import Service
from employees.models import Employee, EmployeeService
from bookings.utils import get_available_slots, has_conflict, lock_employee_day_bookings, safe_json_for_script
from customers.models import Customer
from bookings.models import Booking
from bookings.emails import send_booking_emails


logger = logging.getLogger(__name__)


def booking_home(request, business_slug):
    business = get_object_or_404(Business, slug=business_slug)
    services = Service.objects.filter(business=business, active=True)

    employee_service_data = []

    employee_services = EmployeeService.objects.filter(
        employee__business=business,
        employee__active=True,
        service__business=business,
        service__active=True,
    ).select_related("employee", "service")

    for relation in employee_services:
        employee_service_data.append({
            "service_id": relation.service.id,
            "employee_id": relation.employee.id,
            "employee_name": relation.employee.full_name,
        })

    slots = []
    selected_service_id = None
    selected_date = ""
    selected_time = ""
    selected_employee_id = "any"
    employee_id = ""
    error_message = ""

    if request.method == "POST":
        selected_service_id = request.POST.get("service_id")
        selected_date = request.POST.get("booking_date")
        selected_time = request.POST.get("start_time")
        employee_id = request.POST.get("employee_id")
        selected_employee_id = request.POST.get("selected_employee_id", "any")

        # =========================================================
        # VALIDACIONES GENERALES FECHA
        # =========================================================

        try:
            if selected_date:
                booking_date_obj = datetime.strptime(
                    selected_date,
                    "%Y-%m-%d"
                ).date()

                today = datetime.now().date()

                # NO PASADO
                if not business.allow_past_bookings and booking_date_obj < today:
                    error_message = "No se puede reservar en fechas pasadas."

                # MAX DÍAS CONFIGURABLE
                max_date = today + timedelta(days=business.max_advance_days)

                if booking_date_obj > max_date:
                    error_message = (
                        f"Solo se puede reservar con un máximo de "
                        f"{business.max_advance_days} días de antelación."
                    )

        except Exception:
            error_message = "Fecha inválida."

        # =========================================================
        # CONFIRMAR RESERVA
        # =========================================================

        if "confirm_booking" in request.POST and not error_message:
            # =====================================================
            # CAMPO TRAMPA PARA BOTS ("honeypot")
            # =====================================================
            # Un usuario real nunca ve ni rellena este campo (está
            # oculto con CSS). Si viene relleno, es casi seguro que
            # quien lo envió es un script automático, no una persona.
            # Lo tratamos como un error genérico, sin dar pistas de
            # que se ha detectado, para no ayudar a que lo esquiven.
            # =====================================================

            if (request.POST.get("website") or "").strip():
                error_message = "No se pudo procesar la reserva. Inténtalo de nuevo."

            customer_name = (request.POST.get("customer_name") or "").strip()
            customer_phone = (request.POST.get("customer_phone") or "").strip()
            customer_email = (request.POST.get("customer_email") or "").strip()

            # =====================================================
            # VALIDAR DATOS DEL CLIENTE (por si se salta el formulario)
            # =====================================================

            if not error_message and not customer_name:
                error_message = "Falta el nombre del cliente."
            elif not error_message and not customer_phone:
                error_message = "Falta el teléfono del cliente."

            booking_date_obj = datetime.strptime(
                selected_date,
                "%Y-%m-%d"
            ).date()

            start_time_obj = datetime.strptime(
                selected_time,
                "%H:%M"
            ).time()

            service = get_object_or_404(
                Service,
                id=int(selected_service_id),
                business=business,
                active=True
            )

            # =====================================================
            # VALIDAR QUE EL EMPLEADO ES REAL, DE ESTE NEGOCIO Y
            # OFRECE ESTE SERVICIO (el employee_id llega en un campo
            # oculto del formulario, así que no nos podemos fiar de él
            # sin comprobarlo en el servidor)
            # =====================================================

            employee = None

            if not error_message:
                try:
                    employee = get_object_or_404(
                        Employee,
                        id=int(employee_id),
                        business=business,
                        active=True,
                        employee_services__service=service,
                    )
                except (TypeError, ValueError):
                    error_message = "Profesional no válido."

            start_dt = datetime.combine(
                booking_date_obj,
                start_time_obj
            )

            end_dt = start_dt + timedelta(
                minutes=service.duration_minutes
            )

            # =====================================================
            # MÍNIMO HORAS CONFIGURABLE
            # =====================================================

            now = datetime.now()

            if not error_message and start_dt < now + timedelta(hours=business.min_advance_hours):
                error_message = (
                    f"Las reservas deben hacerse con al menos "
                    f"{business.min_advance_hours} horas de antelación."
                )

            # =====================================================
            # CONFLICTOS + CREAR RESERVA
            # =====================================================
            # Todo esto ocurre dentro de una única transacción con
            # bloqueo de filas (select_for_update). Así, si dos
            # clientes confirman el mismo hueco casi a la vez, la
            # segunda petición espera a que termine la primera y
            # vuelve a comprobar el conflicto ya con el hueco ocupado.
            # La restricción única de la base de datos actúa además
            # como red de seguridad final.
            # =====================================================

            booking = None

            if not error_message:
                try:
                    with transaction.atomic():
                        lock_employee_day_bookings(
                            business_id=business.id,
                            employee_id=employee.id,
                            date=booking_date_obj,
                        )

                        conflict_exists = has_conflict(
                            business_id=business.id,
                            employee_id=employee.id,
                            date=booking_date_obj,
                            start_time=start_time_obj,
                            end_time=end_dt.time(),
                        )

                        if conflict_exists:
                            raise IntegrityError("conflict")

                        customer, created = Customer.objects.get_or_create(
                            business=business,
                            phone=customer_phone,
                            defaults={
                                "full_name": customer_name,
                                "email": customer_email,
                            }
                        )

                        if not created:
                            customer.full_name = customer_name
                            customer.email = customer_email
                            customer.save()

                        booking = Booking.objects.create(
                            business=business,
                            customer=customer,
                            employee=employee,
                            service=service,
                            booking_date=booking_date_obj,
                            start_time=start_time_obj,
                            source="web"
                        )

                except (IntegrityError, OperationalError):
                    # Conflicto real (restricción única) o la base de datos
                    # estaba momentáneamente bloqueada por otra reserva
                    # simultánea. En ambos casos, tratamos el hueco como
                    # no disponible en vez de mostrar un error al cliente.
                    booking = None

            if not error_message and booking is None:
                return render(
                    request,
                    "public_booking/booking_conflict.html",
                    {
                        "business": business,
                        "booking_date": selected_date,
                        "start_time": selected_time,
                        "service_id": selected_service_id,
                    }
                )

            # =====================================================
            # RESERVA CREADA: ENVIAR EMAIL SIN ROMPER LA RESERVA
            # =====================================================
            # Importante:
            # La reserva ya está creada.
            # Si Brevo/SMTP falla o tarda, NO debe aparecer error 500.
            # El fallo queda registrado en Render Logs.
            # =====================================================

            if not error_message and booking is not None:
                cancel_url = request.build_absolute_uri(
                    reverse(
                        "cancel-booking-public",
                        kwargs={
                            "business_slug": business.slug,
                            "cancel_token": booking.cancel_token,
                        }
                    )
                )

                try:
                    email_sent = send_booking_emails(
                        booking,
                        cancel_url=cancel_url
                    )

                    if not email_sent:
                        logger.warning(
                            "La reserva %s se creó correctamente, pero el email no se envió.",
                            booking.id
                        )

                except Exception:
                    logger.exception(
                        "La reserva %s se creó correctamente, pero falló el envío de email.",
                        booking.id
                    )

                return render(
                    request,
                    "public_booking/booking_success.html",
                    {
                        "business": business,
                        "booking_date": selected_date,
                        "start_time": selected_time,
                        "cancel_url": cancel_url,
                    }
                )

        # =========================================================
        # SELECCIONAR SLOT
        # =========================================================

        if (
            "select_slot" in request.POST
            and selected_time
            and not error_message
        ):
            return render(
                request,
                "public_booking/booking_form.html",
                {
                    "business": business,
                    "service_id": selected_service_id,
                    "booking_date": selected_date,
                    "start_time": selected_time,
                    "employee_id": employee_id,
                    "selected_employee_id": selected_employee_id,
                }
            )

        # =========================================================
        # CARGAR DISPONIBILIDAD
        # =========================================================

        if selected_service_id and selected_date and not error_message:
            try:
                booking_date = datetime.strptime(
                    selected_date,
                    "%Y-%m-%d"
                ).date()

                employee_filter = None

                if (
                    selected_employee_id
                    and selected_employee_id != "any"
                ):
                    employee_filter = int(selected_employee_id)

                slots = get_available_slots(
                    business_id=business.id,
                    service_id=int(selected_service_id),
                    booking_date=booking_date,
                    employee_id=employee_filter
                )

                # =================================================
                # FILTRAR HORAS < HORAS CONFIGURABLES
                # =================================================

                filtered_slots = []

                now = datetime.now()

                for slot in slots:
                    slot_datetime = datetime.combine(
                        booking_date,
                        datetime.strptime(
                            slot["start_time"],
                            "%H:%M"
                        ).time()
                    )

                    if slot_datetime >= now + timedelta(hours=business.min_advance_hours):
                        filtered_slots.append(slot)

                slots = filtered_slots

            except Exception:
                slots = []
                error_message = "No se pudo calcular la disponibilidad."

    if selected_service_id:
        employees = Employee.objects.filter(
            business=business,
            active=True,
            employee_services__service_id=selected_service_id,
            employee_services__service__active=True,
        ).distinct().order_by("full_name")

    else:
        employees = Employee.objects.none()

    context = {
        "business": business,
        "services": services,
        "employees": employees,
        "slots": slots,
        "selected_service_id": selected_service_id,
        "selected_date": selected_date,
        "selected_employee_id": selected_employee_id,
        "employee_service_data_json": safe_json_for_script(employee_service_data),
        "error_message": error_message,
    }

    return render(
        request,
        "public_booking/booking_home.html",
        context
    )


def cancel_booking_public(request, business_slug, cancel_token):
    business = get_object_or_404(Business, slug=business_slug)

    booking = get_object_or_404(
        Booking,
        business=business,
        cancel_token=cancel_token
    )

    booking_datetime = datetime.combine(
        booking.booking_date,
        booking.start_time
    )

    now = datetime.now()

    can_cancel = True
    cancel_error = ""

    if booking.status == "cancelled":
        can_cancel = False
        cancel_error = "Esta reserva ya estaba cancelada."

    elif booking.status == "completed":
        can_cancel = False
        cancel_error = "Esta reserva ya está completada y no se puede cancelar."

    elif booking_datetime <= now:
        can_cancel = False
        cancel_error = "No se puede cancelar una reserva que ya ha pasado."

    if request.method == "POST":
        if can_cancel:
            booking.status = "cancelled"
            booking.save()

            return render(
                request,
                "public_booking/cancel_booking_success.html",
                {
                    "business": business,
                    "booking": booking,
                }
            )

    return render(
        request,
        "public_booking/cancel_booking.html",
        {
            "business": business,
            "booking": booking,
            "can_cancel": can_cancel,
            "cancel_error": cancel_error,
        }
    )