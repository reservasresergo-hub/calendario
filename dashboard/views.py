from datetime import date, datetime, timedelta
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404

from businesses.models import Business
from bookings.models import Booking
from bookings.utils import get_available_slots, has_conflict
from customers.models import Customer
from employees.models import Employee, EmployeeService
from services_app.models import Service
from schedules.models import WeeklySchedule, BlockedSlot


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
                    time_ranges = [
                        (
                            schedule.start_time_morning,
                            schedule.end_time_morning
                        )
                    ]

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

                        while current + timedelta(minutes=30) <= schedule_end:
                            slot_end = current + timedelta(minutes=30)

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

                            current += timedelta(minutes=30)

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
        customer_name = request.POST.get("customer_name")
        customer_phone = request.POST.get("customer_phone")
        customer_email = request.POST.get("customer_email")

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

            conflict_exists = has_conflict(
                business_id=business.id,
                employee_id=employee.id,
                date=booking_date_obj,
                start_time=start_time_obj,
                end_time=end_dt.time(),
            )

            if conflict_exists:
                error_message = (
                    "Ese hueco ya está ocupado o bloqueado. "
                    "Elige otra hora."
                )
            else:
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

                Booking.objects.create(
                    business=business,
                    customer=customer,
                    employee=employee,
                    service=service,
                    booking_date=booking_date_obj,
                    start_time=start_time_obj,
                    source="dashboard"
                )

                messages.success(request, "Reserva creada correctamente.")
                return redirect("dashboard-home")

        except Exception:
            error_message = "No se pudo crear la reserva. Revisa los datos."

    context = {
        "business": business,
        "services": services,
        "employees": employees,
        "employee_service_data_json": json.dumps(employee_service_data),
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

            conflict = has_conflict(
                business_id=business.id,
                employee_id=employee.id,
                date=date_obj,
                start_time=time_obj,
                end_time=end_dt.time(),
                exclude_booking_id=booking.id,
            )

            if conflict:
                error_message = "Ese horario no está disponible."
            else:
                booking.service = service
                booking.employee = employee
                booking.booking_date = date_obj
                booking.start_time = time_obj
                booking.save()

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
        name = request.POST.get("name")
        duration = request.POST.get("duration")
        price = request.POST.get("price")

        try:
            Service.objects.create(
                business=business,
                name=name,
                duration_minutes=int(duration),
                price=float(price) if price else None,
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
            service.name = request.POST.get("name")
            service.duration_minutes = int(request.POST.get("duration"))

            price = request.POST.get("price")
            service.price = float(price) if price else None

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

    service.delete()

    messages.success(request, "Servicio eliminado correctamente.")
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
        full_name = request.POST.get("full_name")

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

    if request.method == "POST":
        employee.full_name = request.POST.get("full_name")
        employee.active = request.POST.get("active") == "on"
        employee.save()

        messages.success(request, "Empleado actualizado correctamente.")
        return redirect("employee-list")

    return render(request, "dashboard/edit_employee.html", {
        "business": business,
        "employee": employee,
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

    employee.delete()

    messages.success(request, "Empleado eliminado correctamente.")
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

    if request.method == "POST":
        for weekday, day_name in weekdays:
            active = request.POST.get(f"active_{weekday}") == "on"
            start_morning = request.POST.get(f"start_morning_{weekday}")
            end_morning = request.POST.get(f"end_morning_{weekday}")
            start_afternoon = request.POST.get(f"start_afternoon_{weekday}")
            end_afternoon = request.POST.get(f"end_afternoon_{weekday}")

            if active and start_morning and end_morning:
                schedule, created = WeeklySchedule.objects.get_or_create(
                    employee=employee,
                    weekday=weekday,
                    defaults={
                        "start_time_morning": start_morning,
                        "end_time_morning": end_morning,
                        "start_time_afternoon": start_afternoon or None,
                        "end_time_afternoon": end_afternoon or None,
                        "active": True,
                    }
                )

                if not created:
                    schedule.start_time_morning = start_morning
                    schedule.end_time_morning = end_morning
                    schedule.start_time_afternoon = start_afternoon or None
                    schedule.end_time_afternoon = end_afternoon or None
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
            else:
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
            business.logo = request.FILES.get("logo")

        business.allow_past_bookings = (
            request.POST.get("allow_past_bookings") == "on"
        )

        business.min_advance_hours = int(
            request.POST.get("min_advance_hours") or 0
        )

        business.max_advance_days = int(
            request.POST.get("max_advance_days") or 31
        )

        business.save()

        messages.success(request, "Datos del negocio actualizados correctamente.")
        return redirect("dashboard-home")

    return render(request, "dashboard/edit_business.html", {
        "business": business
    })