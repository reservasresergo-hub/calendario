from django.conf import settings
from django.db import models


class Business(models.Model):
    THEME_CHOICES = [
        ("classic", "Clásico"),
        ("modern", "Moderno"),
        ("beauty", "Belleza"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="businesses",
        blank=True,
        null=True,
        verbose_name="Propietario"
    )

    name = models.CharField(
        max_length=150,
        verbose_name="Nombre del negocio"
    )

    slug = models.SlugField(
        unique=True,
        verbose_name="URL del negocio"
    )

    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Teléfono"
    )

    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email"
    )

    logo = models.ImageField(
        upload_to="business_logos/",
        blank=True,
        null=True,
        verbose_name="Logo"
    )

    theme = models.CharField(
        max_length=30,
        choices=THEME_CHOICES,
        default="classic",
        verbose_name="Tema visual"
    )

    allow_past_bookings = models.BooleanField(
        default=False,
        verbose_name="Permitir reservas en fechas pasadas"
    )

    min_advance_hours = models.PositiveIntegerField(
        default=2,
        verbose_name="Horas mínimas de antelación"
    )

    max_advance_days = models.PositiveIntegerField(
        default=31,
        verbose_name="Días máximos de antelación"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación"
    )

    class Meta:
        verbose_name = "Negocio"
        verbose_name_plural = "Negocios"
        ordering = ["name"]

    def __str__(self):
        return self.name