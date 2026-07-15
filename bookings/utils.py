from datetime import datetime, timedelta

from bookings.models import Booking
from businesses.models import Business
from employees.models import EmployeeService
from schedules.models import WeeklySchedule, BlockedSlot
from services_app.models import Service


def lock_employee_day_bookings(business_id, employee_id, date):
    """
    Bloquea (SELECT ... FOR UPDATE) las reservas confirmadas de un empleado
    en un día concreto. Se usa dentro de una transacción justo antes de
    comprobar conflictos y crear una reserva, para que dos peticiones
    simultáneas para el mismo hueco no puedan colarse las dos a la vez.

    Debe llamarse siempre dentro de un transaction.atomic().
    """
    return list(
        Booking.objects.select_for_update().filter(
            business_id=business_id,
            employee_id=employee_id,
            booking_date=date,
            status="confirmed",
        )
    )


def overlaps(start1, end1, start2, end2):
    return start1 < end2 and end1 > start2


def has_conflict(
    business_id,
    employee_id,
    date,
    start_time,
    end_time,
    exclude_booking_id=None,
    exclude_block_id=None,
):
    start_dt = datetime.combine(date, start_time)
    end_dt = datetime.combine(date, end_time)

    bookings = Booking.objects.filter(
        business_id=business_id,
        employee_id=employee_id,
        booking_date=date,
        status="confirmed",
    )

    if exclude_booking_id:
        bookings = bookings.exclude(id=exclude_booking_id)

    for booking in bookings:
        booking_start = datetime.combine(date, booking.start_time)
        booking_end = datetime.combine(date, booking.end_time)

        if overlaps(start_dt, end_dt, booking_start, booking_end):
            return True

    blocked_slots = BlockedSlot.objects.filter(
        business_id=business_id,
        employee_id=employee_id,
        date=date,
    )

    if exclude_block_id:
        blocked_slots = blocked_slots.exclude(id=exclude_block_id)

    for blocked in blocked_slots:
        blocked_start = datetime.combine(date, blocked.start_time)
        blocked_end = datetime.combine(date, blocked.end_time)

        if overlaps(start_dt, end_dt, blocked_start, blocked_end):
            return True

    return False


def get_available_slots(
    business_id,
    service_id,
    booking_date,
    employee_id=None,
    exclude_booking_id=None,
):
    service = Service.objects.get(
        id=service_id,
        business_id=business_id,
        active=True
    )

    # Cada cuántos minutos se prueba un posible hueco de inicio.
    # Cada negocio elige el suyo en su configuración (por defecto 15 min).
    # Un intervalo fijo a 30 minutos dejaba huecos muertos sin usar cuando
    # un servicio duraba, por ejemplo, 45 minutos (10:00-10:45, y el
    # siguiente hueco válido, 10:45, nunca se llegaba a ofrecer). Con un
    # paso más fino, los huecos se ajustan justo después de que termine
    # cualquier cita anterior, sea cual sea su duración.
    slot_step_minutes = Business.objects.get(id=business_id).slot_interval_minutes

    duration = timedelta(minutes=service.duration_minutes)

    employee_services = EmployeeService.objects.filter(
        service_id=service_id,
        employee__business_id=business_id,
        employee__active=True,
    ).select_related("employee")

    if employee_id:
        employee_services = employee_services.filter(employee_id=employee_id)

    weekday = booking_date.weekday()
    available_slots = []

    for employee_service in employee_services:
        employee = employee_service.employee

        schedules = WeeklySchedule.objects.filter(
            employee=employee,
            weekday=weekday,
            active=True,
        )

        for schedule in schedules:
            time_ranges = [
                (schedule.start_time_morning, schedule.end_time_morning)
            ]

            if schedule.start_time_afternoon and schedule.end_time_afternoon:
                time_ranges.append(
                    (schedule.start_time_afternoon, schedule.end_time_afternoon)
                )

            for range_start, range_end in time_ranges:
                current = datetime.combine(booking_date, range_start)
                schedule_end = datetime.combine(booking_date, range_end)

                while current + duration <= schedule_end:
                    slot_end = current + duration

                    conflict = has_conflict(
                        business_id=business_id,
                        employee_id=employee.id,
                        date=booking_date,
                        start_time=current.time(),
                        end_time=slot_end.time(),
                        exclude_booking_id=exclude_booking_id,
                    )

                    if not conflict:
                        available_slots.append({
                            "employee_id": employee.id,
                            "employee_name": employee.full_name,
                            "start_time": current.strftime("%H:%M"),
                        })

                    current += timedelta(minutes=slot_step_minutes)

    available_slots.sort(key=lambda x: (x["start_time"], x["employee_name"]))
    return available_slots