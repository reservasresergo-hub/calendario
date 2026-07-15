import json
from datetime import datetime, timedelta

from django.db import transaction, IntegrityError, OperationalError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from bookings.utils import get_available_slots, has_conflict, lock_employee_day_bookings
from bookings.models import Booking
from bookings.emails import send_booking_emails
from customers.models import Customer
from employees.models import Employee, EmployeeService
from services_app.models import Service
from businesses.models import Business


def check_api_key(request):
    # Si no se ha configurado una API_SECRET_KEY propia por variable de
    # entorno, esta API queda desactivada por seguridad: la clave por
    # defecto del código quedó expuesta en documentos antiguos del
    # proyecto y no debe usarse en producción.
    if not settings.API_SECRET_KEY or settings.API_SECRET_KEY == "mi_clave_super_secreta_123":
        return False

    api_key = request.headers.get("X-API-KEY")
    return api_key == settings.API_SECRET_KEY


@csrf_exempt
def availability_view(request):
    if not check_api_key(request):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        data = json.loads(request.body)

        business_slug = data["business_slug"]
        service_id = data["service_id"]
        booking_date = datetime.strptime(
            data["booking_date"], "%Y-%m-%d"
        ).date()

        business = Business.objects.get(slug=business_slug)

        slots = get_available_slots(
            business_id=business.id,
            service_id=service_id,
            booking_date=booking_date,
        )

        return JsonResponse({"slots": slots}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def create_booking_view(request):
    if not check_api_key(request):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        data = json.loads(request.body)

        business_slug = data["business_slug"]
        service_id = data["service_id"]
        employee_id = data["employee_id"]
        booking_date = datetime.strptime(
            data["booking_date"], "%Y-%m-%d"
        ).date()
        start_time = datetime.strptime(
            data["start_time"], "%H:%M"
        ).time()

        customer_name = data["customer_name"]
        customer_phone = data["customer_phone"]
        customer_email = data.get("customer_email", "")

        if not customer_name or not customer_phone:
            return JsonResponse(
                {"error": "Faltan customer_name o customer_phone"},
                status=400
            )

        business = Business.objects.get(slug=business_slug)
        service = Service.objects.get(id=service_id, business=business, active=True)

        # El empleado debe pertenecer a este negocio Y ofrecer este servicio.
        employee = Employee.objects.get(
            id=employee_id,
            business=business,
            active=True,
            employee_services__service=service,
        )

        start_dt = datetime.combine(booking_date, start_time)
        end_dt = start_dt + timedelta(minutes=service.duration_minutes)

        # Igual que en la web pública: bloqueo + comprobación de conflicto
        # + creación, todo en una única transacción, con la restricción
        # única de la base de datos como red de seguridad final.
        try:
            with transaction.atomic():
                lock_employee_day_bookings(
                    business_id=business.id,
                    employee_id=employee.id,
                    date=booking_date,
                )

                if has_conflict(
                    business_id=business.id,
                    employee_id=employee.id,
                    date=booking_date,
                    start_time=start_time,
                    end_time=end_dt.time(),
                ):
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
                    booking_date=booking_date,
                    start_time=start_time,
                    end_time=end_dt.time(),
                    status="confirmed",
                )
        except (IntegrityError, OperationalError):
            return JsonResponse(
                {"error": "Ese hueco ya está ocupado. Elige otra hora."},
                status=409
            )

        # Enviar emails automáticos
        send_booking_emails(booking)

        return JsonResponse({
            "message": "Reserva creada correctamente",
            "booking": {
                "id": booking.id,
                "business_slug": business.slug,
                "customer_id": customer.id,
                "employee_id": employee.id,
                "service_id": service.id,
                "booking_date": str(booking_date),
                "start_time": start_time.strftime("%H:%M"),
                "end_time": end_dt.time().strftime("%H:%M"),
                "status": booking.status,
            }
        }, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


def services_view(request):
    if not check_api_key(request):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    if request.method != "GET":
        return JsonResponse({"error": "Only GET allowed"}, status=405)

    try:
        business_slug = request.GET.get("business_slug")

        if not business_slug:
            return JsonResponse({"error": "Falta business_slug"}, status=400)

        business = Business.objects.get(slug=business_slug)

        services = Service.objects.filter(
            business=business,
            active=True
        )

        data = []
        for s in services:
            data.append({
                "id": s.id,
                "name": s.name,
                "duration_minutes": s.duration_minutes,
                "price": str(s.price) if s.price else None,
            })

        return JsonResponse({"services": data}, status=200)

    except Business.DoesNotExist:
        return JsonResponse({"error": "Empresa no encontrada"}, status=404)