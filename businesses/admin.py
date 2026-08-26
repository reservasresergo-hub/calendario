from django.contrib import admin
from django.db import transaction

from .models import Business


@admin.action(description="⚠️ Eliminar negocio COMPLETO (incluye todo su historial de reservas)")
def delete_business_completely(modeladmin, request, queryset):
    """
    Borra uno o varios negocios de verdad, con todo lo que tengan dentro.

    Por qué existe esto: desde que las reservas quedaron protegidas
    contra borrados accidentales (no se puede borrar un empleado o
    servicio que tenga reservas, para no perder el historial sin
    querer), el borrado normal de Django ya no puede eliminar un
    negocio entero si tiene alguna reserva — se bloquearía con el
    mismo error de protección.

    Esta acción borra primero las reservas de cada negocio (que no
    tienen nada que las proteja a ellas mismas) y, ya sin reservas de
    por medio, borra el negocio entero con normalidad — lo que arrastra
    automáticamente sus empleados, servicios y clientes.

    Solo debe usarse cuando de verdad quieras eliminar un negocio para
    siempre (por ejemplo, si te lo pide un cliente que se da de baja).
    No hay forma de deshacer esto.
    """

    total_bookings_deleted = 0
    business_names = []

    with transaction.atomic():
        for business in queryset:
            business_names.append(business.name)
            deleted_count, _ = business.bookings.all().delete()
            total_bookings_deleted += deleted_count

        queryset.delete()

    modeladmin.message_user(
        request,
        f"Eliminados por completo: {', '.join(business_names)} "
        f"(incluidas {total_bookings_deleted} reservas de su historial)."
    )


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "owner", "theme", "phone", "email", "created_at")
    search_fields = ("name", "slug", "phone", "email")
    list_filter = ("theme", "owner")
    actions = [delete_business_completely]