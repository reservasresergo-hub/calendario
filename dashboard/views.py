from datetime import date, datetime, timedelta
import logging

from PIL import Image, UnidentifiedImageError
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction, IntegrityError
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from businesses.models import Business
from bookings.models import Booking
from bookings.emails import send_booking_emails
from bookings.utils import get_available_slots, has_conflict, lock_employee_day_bookings, safe_json_for_script
from customers.models import Customer
from employees.models import Employee, EmployeeService
from services_app.models import Service
from schedules.models import WeeklySchedule, BlockedSlot


logger = logging.getLogger(__name__)

def get_current_business(request):
    """
    Devuelve el negocio asociado al usuario actual.

    Como Business.owner es ForeignKey, un usuario podría tener varios negocios.
    Por ahora usamos el primero.
    """
    return Business.objects.filter(owner=request.user).first()


def overlaps(start1, end1, start2, end2):
    return start1 < end2 and end1 > start2


@login_required
def dashboard_home(request):
    business = get_current_business(request)

    week_param = request.GET.get("week")
    employee_param = request.GET.get("employee", "all")

    is_demo_user = (
        request.user.is_authenticated
        and request.user.username == "demo@resergo.es"
    )

    if is_demo_user:
        selected_day = date(2026, 5, 25)
    else:
        if week_param:
            try:
                selected_day = datetime.strptime(
                    week_param,
                    "%Y-%m-%d"
                ).date()
            except ValueError:
                selected_day = date.today()
        else:
            selected_day = date.today()

    week_start = selected_day - timedelta(days=selected_day.weekday())
    week_end = week_start + timedelta(days=6)

    if is_demo_user:
        previous_week = week_start
        next_week = week_start
    else:
        previous_week = week_start - timedelta(days=7)
        next_week = week_start + timedelta(days=7)

    employees = []
    reservations = []
    blocked_slots = []
    week_days = []
    selected_employee_obj = None

    if business:
        employees = Employee.objects.filter(
            business=business,
            active=True
        ).order_by("full_name")

        reservations_query = Booking.objects.filter(
            business=business,
            booking_date__gte=week_start,
            booking_date__lte=week_end,
        ).select_related(
            "customer",
            "employee",
            "service"
        ).order_by("booking_date", "start_time")

        blocked_query = BlockedSlot.objects.filter(
            business=business,
            date__gte=week_start,
            date__lte=week_end,
        ).select_related("employee").order_by("date", "start_time")

        if employee_param != "all":
            try:
                selected_employee_obj = employees.get(id=int(employee_param))
                reservations_query = reservations_query.filter(
                    employee=selected_employee_obj
                )
                blocked_query = blocked_query.filter(
                    employee=selected_employee_obj
                )
            except (ValueError, Employee.DoesNotExist):
                employee_param = "all"
                selected_employee_obj = None

        reservations = list(reservations_query)
        blocked_slots = list(blocked_query)

        for i in range(7):
            current_day = week_start + timedelta(days=i)

            day_reservations = [
                booking for booking in reservations
                if booking.booking_date == current_day
            ]

            day_blocked_slots = [
                blocked for blocked in blocked_slots
                if blocked.date == current_day
            ]

            day_items = []

            if selected_employee_obj:
                schedules = WeeklySchedule.objects.filter(
                    employee=selected_employee_obj,
                    weekday=current_day.weekday(),
                    active=True
                )

                blocked_ranges = []

                for booking in day_reservations:
                    blocked_ranges.append((
                        datetime.combine(current_day, booking.start_time),
                        datetime.combine(current_day, booking.end_time),
                    ))

                for blocked in day_blocked_slots:
                    blocked_ranges.append((
                        datetime.combine(current_day, blocked.start_time),
                        datetime.combine(current_day, blocked.end_time),
                    ))

                for booking in day_reservations:
                    day_items.append({
                        "type": "booking",
                        "start_dt": datetime.combine(
                            current_day,
                            booking.start_time
                        ),
                        "start_time": booking.start_time.strftime("%H:%M"),
                        "end_time": booking.end_time.strftime("%H:%M"),
                        "booking": booking,
                    })

                for blocked in day_blocked_slots:
                    day_items.append({
                        "type": "blocked",
                        "start_dt": datetime.combine(
                            current_day,
                            blocked.start_time
                        ),
                        "start_time": blocked.start_time.strftime("%H:%M"),
                        "end_time": blocked.end_time.strftime("%H:%M"),
                        "blocked": blocked,
                    })

                for schedule in schedules:
                    time_ranges = []

                    if schedule.start_time_morning and schedule.end_time_morning:
                        time_ranges.append(
                            (
                                schedule.start_time_morning,
                                schedule.end_time_morning
                            )
                        )

                    if (
                        schedule.start_time_afternoon
                        and schedule.end_time_afternoon
                    ):
                        time_ranges.append(
                            (
                                schedule.start_time_afternoon,
                                schedule.end_time_afternoon
                            )
                        )

                    for range_start, range_end in time_ranges:
                        current = datetime.combine(current_day, range_start)
                        schedule_end = datetime.combine(current_day, range_end)
                        slot_step = timedelta(minutes=business.slot_interval_minutes)

                        while current + slot_step <= schedule_end:
                            slot_end = current + slot_step

                            slot_has_conflict = any(
                                overlaps(
                                    current,
                                    slot_end,
                                    blocked_start,
                                    blocked_end
                                )
                                for blocked_start, blocked_end in blocked_ranges
                            )

                            if not slot_has_conflict:
                                day_items.append({
                                    "type": "free",
                                    "start_dt": current,
                                    "start_time": current.strftime("%H:%M"),
                                    "end_time": slot_end.strftime("%H:%M"),
                                })

                            current += slot_step

                day_items.sort(key=lambda item: item["start_dt"])

            else:
                for booking in day_reservations:
                    day_items.append({
                        "type": "booking",
                        "start_dt": datetime.combine(
                            current_day,
                            booking.start_time
                        ),
                        "start_time": booking.start_time.strftime("%H:%M"),
                        "end_time": booking.end_time.strftime("%H:%M"),
                        "booking": booking,
                    })

                for blocked in day_blocked_slots:
                    day_items.append({
                        "type": "blocked",
                        "start_dt": datetime.combine(
                            current_day,
                            blocked.start_time
                        ),
                        "start_time": blocked.start_time.strftime("%H:%M"),
                        "end_time": blocked.end_time.strftime("%H:%M"),
                        "blocked": blocked,
                    })

                day_items.sort(key=lambda item: item["start_dt"])

            week_days.append({
                "date": current_day,
                "name": [
                    "Lunes",
                    "Martes",
                    "Miércoles",
                    "Jueves",
                    "Viernes",
                    "Sábado",
                    "Domingo",
                ][i],
                "reservations": day_reservations,
                "blocked_slots": day_blocked_slots,
                "items": day_items,
            })

    context = {
        "business": business,
        "employees": employees,
        "selected_employee": employee_param,
        "selected_employee_obj": selected_employee_obj,
        "reservations": reservations,
        "blocked_slots": blocked_slots,
        "week_days": week_days,
        "week_start": week_start,
        "week_end": week_end,
        "previous_week": previous_week,
        "next_week": next_week,
        "is_demo_user": is_demo_user,
    }

    return render(request, "dashboard/dashboard_home.html", context)


@login_required
def update_booking_status(request, booking_id, new_status):
    if request.method != "POST":
        return redirect("dashboard-home")

    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    booking = get_object_or_404(
        Booking,
        id=booking_id,
        business=business
    )

    if new_status not in ["confirmed", "completed", "cancelled"]:
        return redirect("dashboard-home")

    booking.status = new_status
    booking.save()

    messages.success(request, "Estado de la reserva actualizado correctamente.")
    return redirect("dashboard-home")


@login_required
def create_booking(request):
    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    services = Service.objects.filter(
        business=business,
        active=True
    ).order_by("name")

    employees = Employee.objects.filter(
        business=business,
        active=True
    ).order_by("full_name")

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

    error_message = ""

    if request.method == "POST":
        customer_name = (request.POST.get("customer_name") or "").strip()
        customer_phone = (request.POST.get("customer_phone") or "").strip()
        customer_email = (request.POST.get("customer_email") or "").strip()

        service_id = request.POST.get("service_id")
        employee_id = request.POST.get("employee_id")
        booking_date = request.POST.get("booking_date")
        start_time = request.POST.get("start_time")

        if not customer_name:
            error_message = "Falta el nombre del cliente."
        elif not customer_phone:
            error_message = "Falta el teléfono del cliente."

        if not error_message:
            try:
                service = get_object_or_404(
                    Service,
                    id=int(service_id),
                    business=business,
                    active=True
                )

                employee = get_object_or_404(
                    Employee,
                    id=int(employee_id),
                    business=business,
                    active=True,
                    employee_services__service=service
                )

                booking_date_obj = datetime.strptime(
                    booking_date,
                    "%Y-%m-%d"
                ).date()

                start_time_obj = datetime.strptime(
                    start_time,
                    "%H:%M"
                ).time()

                start_dt = datetime.combine(booking_date_obj, start_time_obj)
                end_dt = start_dt + timedelta(minutes=service.duration_minutes)

                booking_created = False
                booking = None

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
                            source="dashboard"
                        )

                        booking_created = True

                except IntegrityError:
                    error_message = (
                        "Ese hueco ya está ocupado o bloqueado. "
                        "Elige otra hora."
                    )

                if booking_created:
                    # =====================================================
                    # ENVIAR EMAIL DE CONFIRMACIÓN
                    # =====================================================
                    # Antes, una reserva creada a mano desde el panel
                    # (a diferencia de una reserva hecha por un cliente
                    # desde la web pública) nunca enviaba ningún email
                    # de confirmación. Ahora se envía igual en los dos
                    # casos. Si el email falla, la reserva ya está
                    # creada y no se rompe nada — el fallo solo queda
                    # registrado en los logs.
                    # =====================================================

                    try:
                        cancel_url = request.build_absolute_uri(
                            reverse(
                                "cancel-booking-public",
                                kwargs={
                                    "business_slug": business.slug,
                                    "cancel_token": booking.cancel_token,
                                }
                            )
                        )

                        email_sent = send_booking_emails(
                            booking,
                            cancel_url=cancel_url
                        )

                        if not email_sent:
                            logger.warning(
                                "La reserva %s (creada desde el panel) no envió email.",
                                booking.id
                            )

                    except Exception:
                        logger.exception(
                            "La reserva %s (creada desde el panel) se creó "
                            "correctamente, pero falló el envío de email.",
                            booking.id
                        )

                    messages.success(request, "Reserva creada correctamente.")
                    return redirect("dashboard-home")

            except Exception:
                error_message = "No se pudo crear la reserva. Revisa los datos."

    context = {
        "business": business,
        "services": services,
        "employees": employees,
        "employee_service_data_json": safe_json_for_script(employee_service_data),
        "error_message": error_message,
    }

    return render(request, "dashboard/create_booking.html", context)


@login_required
def get_availability(request):
    business = get_current_business(request)

    if not business:
        return JsonResponse({"slots": []})

    service_id = request.GET.get("service_id")
    employee_id = request.GET.get("employee_id")
    booking_date = request.GET.get("date")
    exclude_booking_id = request.GET.get("exclude_booking_id")

    try:
        booking_date_obj = datetime.strptime(
            booking_date,
            "%Y-%m-%d"
        ).date()

        exclude_id = None

        if exclude_booking_id:
            exclude_id = int(exclude_booking_id)

        slots = get_available_slots(
            business_id=business.id,
            service_id=int(service_id),
            booking_date=booking_date_obj,
            employee_id=int(employee_id),
            exclude_booking_id=exclude_id,
        )

        return JsonResponse({"slots": slots})

    except Exception:
        return JsonResponse({"slots": []})


@login_required
def create_blocked_slot(request):
    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    employees = Employee.objects.filter(
        business=business,
        active=True
    ).order_by("full_name")

    error_message = ""

    if request.method == "POST":
        employee_id = request.POST.get("employee_id")
        block_date = request.POST.get("date")
        start_time = request.POST.get("start_time")
        end_time = request.POST.get("end_time")
        next_url = request.POST.get("next", "/dashboard/")

        try:
            employee = get_object_or_404(
                Employee,
                id=int(employee_id),
                business=business,
                active=True
            )

            date_obj = datetime.strptime(
                block_date,
                "%Y-%m-%d"
            ).date()

            start_time_obj = datetime.strptime(
                start_time,
                "%H:%M"
            ).time()

            end_time_obj = datetime.strptime(
                end_time,
                "%H:%M"
            ).time()

            start_dt = datetime.combine(date_obj, start_time_obj)
            end_dt = datetime.combine(date_obj, end_time_obj)

            if start_dt >= end_dt:
                error_message = "La hora de inicio debe ser menor que la de fin."
            else:
                conflict = has_conflict(
                    business_id=business.id,
                    employee_id=employee.id,
                    date=date_obj,
                    start_time=start_time_obj,
                    end_time=end_time_obj,
                )

                if conflict:
                    error_message = "Ese rango ya está ocupado o bloqueado."
                else:
                    BlockedSlot.objects.create(
                        business=business,
                        employee=employee,
                        date=date_obj,
                        start_time=start_time_obj,
                        end_time=end_time_obj
                    )

                    messages.success(request, "Horario bloqueado correctamente.")

                    if next_url.startswith("/dashboard/"):
                        return redirect(next_url)

                    return redirect("dashboard-home")

        except Exception:
            error_message = "Error al crear el bloqueo."

    return render(request, "dashboard/create_block.html", {
        "business": business,
        "employees": employees,
        "error_message": error_message,
    })


@login_required
def delete_blocked_slot(request, block_id):
    if request.method != "POST":
        return redirect("dashboard-home")

    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    block = get_object_or_404(
        BlockedSlot,
        id=block_id,
        business=business
    )

    block.delete()
    messages.success(request, "Horario desbloqueado correctamente.")
    return redirect("dashboard-home")


@login_required
def edit_booking(request, booking_id):
    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    booking = get_object_or_404(
        Booking,
        id=booking_id,
        business=business
    )

    services = Service.objects.filter(
        business=business,
        active=True
    ).order_by("name")

    employees = Employee.objects.filter(
        business=business,
        active=True
    ).order_by("full_name")

    error_message = ""

    if request.method == "POST":
        service_id = request.POST.get("service_id")
        employee_id = request.POST.get("employee_id")
        booking_date = request.POST.get("booking_date")
        start_time = request.POST.get("start_time")

        try:
            service = get_object_or_404(
                Service,
                id=int(service_id),
                business=business,
                active=True
            )

            employee = get_object_or_404(
                Employee,
                id=int(employee_id),
                business=business,
                active=True
            )

            date_obj = datetime.strptime(booking_date, "%Y-%m-%d").date()
            time_obj = datetime.strptime(start_time, "%H:%M").time()

            start_dt = datetime.combine(date_obj, time_obj)
            end_dt = start_dt + timedelta(minutes=service.duration_minutes)

            saved = False

            try:
                with transaction.atomic():
                    lock_employee_day_bookings(
                        business_id=business.id,
                        employee_id=employee.id,
                        date=date_obj,
                    )

                    conflict = has_conflict(
                        business_id=business.id,
                        employee_id=employee.id,
                        date=date_obj,
                        start_time=time_obj,
                        end_time=end_dt.time(),
                        exclude_booking_id=booking.id,
                    )

                    if conflict:
                        raise IntegrityError("conflict")

                    booking.service = service
                    booking.employee = employee
                    booking.booking_date = date_obj
                    booking.start_time = time_obj
                    booking.save()
                    saved = True

            except IntegrityError:
                error_message = "Ese horario no está disponible."

            if saved:
                messages.success(request, "Reserva editada correctamente.")
                return redirect("dashboard-home")

        except Exception:
            error_message = "Error al editar la reserva."

    return render(request, "dashboard/edit_booking.html", {
        "business": business,
        "booking": booking,
        "services": services,
        "employees": employees,
        "error_message": error_message,
    })


@login_required
def delete_booking(request, booking_id):
    if request.method != "POST":
        return redirect("dashboard-home")

    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    booking = get_object_or_404(
        Booking,
        id=booking_id,
        business=business
    )

    booking.delete()
    messages.success(request, "Reserva eliminada correctamente.")

    return redirect("dashboard-home")


@login_required
def service_list(request):
    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    services = Service.objects.filter(
        business=business
    ).order_by("name")

    return render(request, "dashboard/service_list.html", {
        "business": business,
        "services": services
    })


@login_required
def create_service(request):
    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    error_message = ""

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        duration = request.POST.get("duration")
        price = request.POST.get("price")

        try:
            duration_value = int(duration)
            price_value = float(price) if price else None

            # =====================================================
            # VALIDAR DURACIÓN Y PRECIO
            # =====================================================
            # Una duración de 0 minutos parece inofensiva, pero rompe
            # la protección contra dobles reservas: dos citas de 0
            # minutos a la misma hora exacta no se detectan como
            # solapadas entre sí, así que dos clientes podrían
            # "reservar" el mismo instante sin ningún aviso.
            # =====================================================

            if not name:
                error_message = "Falta el nombre del servicio."
            elif duration_value <= 0:
                error_message = "La duración debe ser de al menos 1 minuto."
            elif price_value is not None and price_value < 0:
                error_message = "El precio no puede ser negativo."

            if not error_message:
                Service.objects.create(
                    business=business,
                    name=name,
                    duration_minutes=duration_value,
                    price=price_value,
                    active=True
                )

                messages.success(request, "Servicio creado correctamente.")
                return redirect("service-list")

        except Exception:
            error_message = "Error al crear el servicio."

    return render(request, "dashboard/create_service.html", {
        "business": business,
        "error_message": error_message
    })

@login_required
def edit_service(request, service_id):
    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    service = get_object_or_404(
        Service,
        id=service_id,
        business=business
    )

    error_message = ""

    if request.method == "POST":
        try:
            name = (request.POST.get("name") or "").strip()
            duration_value = int(request.POST.get("duration"))

            price = request.POST.get("price")
            price_value = float(price) if price else None

            if not name:
                error_message = "Falta el nombre del servicio."
            elif duration_value <= 0:
                error_message = "La duración debe ser de al menos 1 minuto."
            elif price_value is not None and price_value < 0:
                error_message = "El precio no puede ser negativo."

            if not error_message:
                service.name = name
                service.duration_minutes = duration_value
                service.price = price_value
                service.active = request.POST.get("active") == "on"
                service.save()

                messages.success(request, "Servicio actualizado correctamente.")
                return redirect("service-list")

        except Exception:
            error_message = "Error al actualizar el servicio."

    return render(request, "dashboard/edit_service.html", {
        "service": service,
        "business": business,
        "error_message": error_message,
    })


@login_required
def delete_service(request, service_id):
    if request.method != "POST":
        return redirect("service-list")

    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    service = get_object_or_404(
        Service,
        id=service_id,
        business=business
    )

    try:
        service.delete()
        messages.success(request, "Servicio eliminado correctamente.")

    except ProtectedError:
        # El servicio ya tiene reservas asociadas (pasadas o futuras).
        # Antes esto habría borrado el servicio Y todas esas reservas
        # de golpe, sin avisar. Ahora se bloquea, y se indica la
        # alternativa correcta: desactivarlo en vez de borrarlo.
        messages.error(
            request,
            "No se puede eliminar: este servicio tiene reservas asociadas. "
            "Márcalo como inactivo en su lugar (así deja de ofrecerse, "
            "pero conservas el historial de reservas)."
        )

    return redirect("service-list")

@login_required
def employee_list(request):
    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    employees = Employee.objects.filter(
        business=business
    ).order_by("full_name")

    return render(request, "dashboard/employee_list.html", {
        "business": business,
        "employees": employees,
    })


@login_required
def create_employee(request):
    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    error_message = ""

    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()

        if not full_name:
            error_message = "Falta el nombre del empleado."
        else:
            try:
                Employee.objects.create(
                    business=business,
                    full_name=full_name,
                    active=True
                )

                messages.success(request, "Empleado creado correctamente.")
                return redirect("employee-list")

            except Exception:
                error_message = "Error al crear el empleado."

    return render(request, "dashboard/create_employee.html", {
        "business": business,
        "error_message": error_message,
    })


@login_required
def edit_employee(request, employee_id):
    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    employee = get_object_or_404(
        Employee,
        id=employee_id,
        business=business
    )

    error_message = ""

    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()

        if not full_name:
            error_message = "Falta el nombre del empleado."
        else:
            was_active = employee.active

            employee.full_name = full_name
            employee.active = request.POST.get("active") == "on"
            employee.save()

            # =====================================================
            # AVISO DE CITAS FUTURAS AL DESACTIVAR UN EMPLEADO
            # =====================================================
            # Desactivar a un empleado (por ejemplo, porque deja el
            # negocio) no toca sus citas futuras ya confirmadas: se
            # quedan tal cual, asignadas a él. Antes esto pasaba
            # desapercibido — el cliente llegaría esperando a alguien
            # que ya no está, sin que nadie se hubiera dado cuenta.
            # Ahora, si al desactivar quedan citas futuras, se muestra
            # una lista clara con los datos de contacto de cada
            # cliente, para que el propio negocio decida cómo
            # reubicarlas (llamando, reasignando a otro empleado,
            # cancelando, etc. — eso lo decide el negocio, no el
            # sistema).
            # =====================================================

            if was_active and not employee.active:
                future_bookings = Booking.objects.filter(
                    employee=employee,
                    status="confirmed",
                    booking_date__gte=date.today(),
                ).select_related("customer", "service").order_by(
                    "booking_date", "start_time"
                )

                if future_bookings.exists():
                    return render(
                        request,
                        "dashboard/employee_deactivated.html",
                        {
                            "business": business,
                            "employee": employee,
                            "future_bookings": future_bookings,
                        }
                    )

            messages.success(request, "Empleado actualizado correctamente.")
            return redirect("employee-list")

    return render(request, "dashboard/edit_employee.html", {
        "business": business,
        "employee": employee,
        "error_message": error_message,
    })


@login_required
def delete_employee(request, employee_id):
    if request.method != "POST":
        return redirect("employee-list")

    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    employee = get_object_or_404(
        Employee,
        id=employee_id,
        business=business
    )

    try:
        employee.delete()
        messages.success(request, "Empleado eliminado correctamente.")

    except ProtectedError:
        # El empleado ya tiene reservas asociadas (pasadas o futuras).
        # Antes esto habría borrado el empleado Y todas sus reservas
        # de golpe, sin avisar. Ahora se bloquea, y se indica la
        # alternativa correcta: desactivarlo en vez de borrarlo.
        messages.error(
            request,
            "No se puede eliminar: este empleado tiene reservas asociadas. "
            "Márcalo como inactivo en su lugar (así deja de aparecer para "
            "nuevas reservas, pero conservas su historial)."
        )

    return redirect("employee-list")


@login_required
def manage_employee_services(request, employee_id):
    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    employee = get_object_or_404(
        Employee,
        id=employee_id,
        business=business
    )

    services = Service.objects.filter(
        business=business,
        active=True
    ).order_by("name")

    assigned_service_ids = EmployeeService.objects.filter(
        employee=employee
    ).values_list("service_id", flat=True)

    if request.method == "POST":
        selected_service_ids = request.POST.getlist("services")

        EmployeeService.objects.filter(employee=employee).delete()

        for service_id in selected_service_ids:
            service = get_object_or_404(
                Service,
                id=int(service_id),
                business=business,
                active=True
            )

            EmployeeService.objects.create(
                employee=employee,
                service=service
            )

        messages.success(
            request,
            "Servicios del empleado actualizados correctamente."
        )
        return redirect("employee-list")

    return render(request, "dashboard/manage_employee_services.html", {
        "business": business,
        "employee": employee,
        "services": services,
        "assigned_service_ids": list(assigned_service_ids),
    })


@login_required
def manage_employee_schedule(request, employee_id):
    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    employee = get_object_or_404(
        Employee,
        id=employee_id,
        business=business
    )

    weekdays = [
        (0, "Lunes"),
        (1, "Martes"),
        (2, "Miércoles"),
        (3, "Jueves"),
        (4, "Viernes"),
        (5, "Sábado"),
        (6, "Domingo"),
    ]

    error_message = ""

    if request.method == "POST":
        day_names = dict(weekdays)
        pending_days = []

        for weekday, day_name in weekdays:
            active = request.POST.get(f"active_{weekday}") == "on"
            start_morning = request.POST.get(f"start_morning_{weekday}")
            end_morning = request.POST.get(f"end_morning_{weekday}")
            start_afternoon = request.POST.get(f"start_afternoon_{weekday}")
            end_afternoon = request.POST.get(f"end_afternoon_{weekday}")

            has_morning = bool(start_morning and end_morning)
            has_afternoon = bool(start_afternoon and end_afternoon)

            # =====================================================
            # VALIDAR QUE CADA TRAMO TENGA SENTIDO (INICIO < FIN)
            # =====================================================
            # Antes se podía guardar, por ejemplo, un horario de
            # mañana de 18:00 a 09:00. No daba ningún error, pero el
            # empleado se quedaba sin ningún hueco disponible ese día
            # sin ninguna explicación visible en el panel.
            # =====================================================

            if has_morning and start_morning >= end_morning:
                error_message = (
                    f"{day_name}: la hora de inicio de la mañana "
                    f"debe ser antes que la de fin."
                )
                break

            if has_afternoon and start_afternoon >= end_afternoon:
                error_message = (
                    f"{day_name}: la hora de inicio de la tarde "
                    f"debe ser antes que la de fin."
                )
                break

            pending_days.append((
                weekday, active, has_morning, has_afternoon,
                start_morning, end_morning, start_afternoon, end_afternoon,
            ))

        if not error_message:
            with transaction.atomic():
                for (
                    weekday, active, has_morning, has_afternoon,
                    start_morning, end_morning, start_afternoon, end_afternoon,
                ) in pending_days:
                    if active and (has_morning or has_afternoon):
                        schedule, created = WeeklySchedule.objects.get_or_create(
                            employee=employee,
                            weekday=weekday,
                            defaults={
                                "start_time_morning": start_morning if has_morning else None,
                                "end_time_morning": end_morning if has_morning else None,
                                "start_time_afternoon": start_afternoon if has_afternoon else None,
                                "end_time_afternoon": end_afternoon if has_afternoon else None,
                                "active": True,
                            }
                        )

                        if not created:
                            schedule.start_time_morning = start_morning if has_morning else None
                            schedule.end_time_morning = end_morning if has_morning else None
                            schedule.start_time_afternoon = start_afternoon if has_afternoon else None
                            schedule.end_time_afternoon = end_afternoon if has_afternoon else None
                            schedule.active = True
                            schedule.save()

                    else:
                        WeeklySchedule.objects.filter(
                            employee=employee,
                            weekday=weekday
                        ).update(active=False)

            messages.success(request, "Horario semanal actualizado correctamente.")
            return redirect("employee-list")

    schedules = {
        schedule.weekday: schedule
        for schedule in WeeklySchedule.objects.filter(employee=employee)
    }

    schedule_rows = []

    for weekday, day_name in weekdays:
        schedule = schedules.get(weekday)

        schedule_rows.append({
            "weekday": weekday,
            "day_name": day_name,
            "active": schedule.active if schedule else False,
            "start_morning": (
                schedule.start_time_morning.strftime("%H:%M")
                if schedule and schedule.start_time_morning
                else ""
            ),
            "end_morning": (
                schedule.end_time_morning.strftime("%H:%M")
                if schedule and schedule.end_time_morning
                else ""
            ),
            "start_afternoon": (
                schedule.start_time_afternoon.strftime("%H:%M")
                if schedule and schedule.start_time_afternoon
                else ""
            ),
            "end_afternoon": (
                schedule.end_time_afternoon.strftime("%H:%M")
                if schedule and schedule.end_time_afternoon
                else ""
            ),
        })

    return render(request, "dashboard/manage_employee_schedule.html", {
        "business": business,
        "employee": employee,
        "schedule_rows": schedule_rows,
        "error_message": error_message,
    })

@login_required
def create_full_day_block(request):
    business = get_current_business(request)

    if not business:
        return redirect("dashboard-home")

    employees = Employee.objects.filter(
        business=business,
        active=True
    ).order_by("full_name")

    error_message = ""

    if request.method == "POST":
        employee_id = request.POST.get("employee_id")
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date")

        try:
            employee = get_object_or_404(
                Employee,
                id=int(employee_id),
                business=business,
                active=True
            )

            start_date_obj = datetime.strptime(
                start_date,
                "%Y-%m-%d"
            ).date()

            end_date_obj = datetime.strptime(
                end_date,
                "%Y-%m-%d"
            ).date()

            if start_date_obj > end_date_obj:
                error_message = (
                    "La fecha de inicio no puede ser posterior a la fecha de fin."
                )
            elif (end_date_obj - start_date_obj).days > 7:
                # Límite de seguridad: si necesitas bloquear más de una
                # semana (vacaciones largas, baja...), hazlo en varias
                # veces. Esto evita bloqueos enormes por un año mal
                # escrito y mantiene la petición siempre rápida.
                error_message = (
                    "No se puede bloquear más de una semana de una vez. "
                    "Si necesitas más días, hazlo en varias veces."
                )
            else:
                with transaction.atomic():
                    current_date = start_date_obj

                    while current_date <= end_date_obj:
                        BlockedSlot.objects.get_or_create(
                            business=business,
                            employee=employee,
                            date=current_date,
                            start_time="00:00",
                            end_time="23:59"
                        )

                        current_date += timedelta(days=1)

                messages.success(request, "Día(s) bloqueado(s) correctamente.")
                return redirect("dashboard-home")

        except Exception:
            error_message = "Error al bloquear los días."

    return render(request, "dashboard/create_full_day_block.html", {
        "business": business,
        "employees": employees,
        "error_message": error_message,
    })


@login_required
def edit_business(request):
    business = get_current_business(request)
    if not business:
        return redirect("dashboard-home")
    if request.method == "POST":
        business.name = request.POST.get("name")
        business.phone = request.POST.get("phone")
        business.email = request.POST.get("email")
        if request.POST.get("delete_logo") == "on":
            if business.logo:
                business.logo.delete(save=False)
            business.logo = None
        elif request.FILES.get("logo"):
            logo_file = request.FILES.get("logo")

            # =====================================================
            # VALIDAR QUE EL "LOGO" ES REALMENTE UNA IMAGEN
            # =====================================================
            # Antes se guardaba cualquier archivo tal cual, confiando
            # solo en su nombre. Alguien podía subir un archivo .html
            # con código dentro, y al visitarlo directamente desde su
            # enlace público, el navegador lo habría ejecutado como
            # una página real de tu dominio. Aquí comprobamos el
            # contenido real del archivo (no el nombre) con Pillow,
            # y limitamos el tamaño para evitar subidas enormes.
            # =====================================================

            max_logo_size_bytes = 5 * 1024 * 1024  # 5 MB

            if logo_file.size > max_logo_size_bytes:
                messages.error(
                    request,
                    "El logo no se ha guardado: el archivo pesa más de 5 MB."
                )
            else:
                try:
                    with Image.open(logo_file) as img:
                        img.verify()

                    logo_file.seek(0)
                    business.logo = logo_file

                except (UnidentifiedImageError, OSError, ValueError):
                    messages.error(
                        request,
                        "El logo no se ha guardado: el archivo no es una imagen válida."
                    )
        business.allow_past_bookings = (
            request.POST.get("allow_past_bookings") == "on"
        )
        business.min_advance_hours = int(
            request.POST.get("min_advance_hours") or 0
        )
        business.max_advance_days = int(
            request.POST.get("max_advance_days") or 31
        )
        allowed_intervals = [choice[0] for choice in business.SLOT_INTERVAL_CHOICES]
        slot_interval = int(
            request.POST.get("slot_interval_minutes") or business.slot_interval_minutes
        )
        if slot_interval in allowed_intervals:
            business.slot_interval_minutes = slot_interval
        allowed_themes = [choice[0] for choice in business.THEME_CHOICES]
        theme = request.POST.get("theme")
        if theme in allowed_themes:
            business.theme = theme
        business.save()
        messages.success(request, "Datos del negocio actualizados correctamente.")
        return redirect("dashboard-home")
    return render(request, "dashboard/edit_business.html", {
        "business": business
    })