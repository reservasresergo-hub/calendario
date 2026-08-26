from datetime import timedelta
import traceback

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from businesses.models import Business
from .forms import BusinessRegisterForm
from .models import LoginAttempt


# Tras este número de intentos fallidos seguidos, se bloquea la cuenta
# temporalmente. Se cuentan solo los fallos dentro de la ventana de
# tiempo de abajo — pasado ese tiempo, los intentos antiguos ya no
# cuentan.
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_WINDOW_MINUTES = 15



def home(request):
    """
    Página comercial pública del SaaS.

    Esta será la landing principal en /.
    """
    return render(
        request,
        "accounts/home.html"
    )


def demo_login(request):
    """
    Acceso automático al panel demo de ReserGo.

    Entra como usuario demo, asegura que tiene asignada la empresa demo
    y redirige al dashboard en la semana donde existen reservas demo.
    """

    User = get_user_model()

    demo_user = User.objects.filter(username="demo@resergo.es").first()

    if not demo_user:
        messages.error(
            request,
            "La demo todavía no está disponible."
        )
        return redirect("/login/")

    business = Business.objects.filter(slug="demo-peluqueria").first()

    if business:
        business.owner = demo_user
        business.save()

    login(request, demo_user)

    return redirect("/dashboard/?week=2026-05-25")


def aviso_legal(request):
    return render(
        request,
        "accounts/aviso_legal.html"
    )


def politica_privacidad(request):
    return render(
        request,
        "accounts/politica_privacidad.html"
    )


def politica_cookies(request):
    return render(
        request,
        "accounts/politica_cookies.html"
    )


def condiciones_uso(request):
    return render(
        request,
        "accounts/condiciones_uso.html"
    )


def generate_unique_business_slug(business_name):
    """
    Genera un slug único a partir del nombre del negocio.

    Ejemplo:
    Peluquería Ana -> peluqueria-ana

    Si ya existe:
    peluqueria-ana-2
    peluqueria-ana-3
    etc.
    """

    base_slug = slugify(business_name)

    if not base_slug:
        base_slug = "negocio"

    slug = base_slug
    counter = 2

    while Business.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


@never_cache
@csrf_protect
def login_user(request):
    """
    Login personalizado para evitar problemas raros de CSRF/cache
    y mostrar mensajes claros si el usuario o contraseña son incorrectos.
    """

    # Si la sesión activa es la del usuario demo, la cerramos primero.
    # Si no, alguien que probó la demo y luego pulsa "Iniciar sesión" o
    # "Ya soy cliente" se quedaría siempre atrapado en el panel de demo,
    # sin poder llegar nunca al formulario para entrar con su cuenta real.
    if request.user.is_authenticated and request.user.username == "demo@resergo.es":
        logout(request)

    elif request.user.is_authenticated:
        return redirect("dashboard-home")

    if request.method == "POST":
        email = (request.POST.get("username") or "").strip()
        password = request.POST.get("password")

        # =====================================================
        # PROTECCIÓN CONTRA FUERZA BRUTA
        # =====================================================
        # Antes se podían probar contraseñas sin límite contra la
        # misma cuenta. Ahora, si hay demasiados fallos seguidos en
        # poco tiempo, se bloquea el acceso temporalmente, aunque la
        # contraseña que se envíe a partir de ahí sea la correcta.
        # =====================================================

        window_start = timezone.now() - timedelta(minutes=LOGIN_LOCKOUT_WINDOW_MINUTES)

        # Aprovechamos para limpiar los intentos ya caducados de esta
        # misma cuenta, para que la tabla no crezca sin límite.
        LoginAttempt.objects.filter(
            username=email,
            attempted_at__lt=window_start,
        ).delete()

        recent_failed_attempts = LoginAttempt.objects.filter(
            username=email,
            attempted_at__gte=window_start,
        ).count()

        if recent_failed_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
            messages.error(
                request,
                "Demasiados intentos fallidos. Por seguridad, espera unos "
                "minutos antes de volver a intentarlo."
            )
            return redirect("login")

        user = authenticate(
            request,
            username=email,
            password=password
        )

        if user is not None:
            # Login correcto: los fallos anteriores de esta cuenta ya
            # no importan, se limpian.
            LoginAttempt.objects.filter(username=email).delete()

            login(request, user)
            return redirect("dashboard-home")

        LoginAttempt.objects.create(username=email)

        messages.error(
            request,
            "Usuario o contraseña incorrectos. Revisa los datos e inténtalo de nuevo."
        )

        return redirect("login")

    return render(
        request,
        "dashboard/login.html"
    )


@never_cache
@csrf_protect
@login_required
def register_business(request):
    """
    Registro interno de negocios.

    IMPORTANTE:
    Solo puede acceder un superusuario.
    Esta página sirve para que tú crees cuentas de negocios que ya han contratado/pagado.
    """

    if not request.user.is_superuser:
        messages.error(
            request,
            "No tienes permisos para crear nuevos negocios."
        )
        return redirect("dashboard-home")

    created_business_data = None

    if request.method == "POST":
        form = BusinessRegisterForm(request.POST)

        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]
            business_name = form.cleaned_data["business_name"]

            slug = generate_unique_business_slug(business_name)

            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
            )

            business = Business.objects.create(
                owner=user,
                name=business_name,
                slug=slug,
                phone=form.cleaned_data["business_phone"],
                email=email,
            )

            public_url = f"/{business.slug}/"

            created_business_data = {
                "business_name": business.name,
                "user_email": email,
                "public_url": public_url,
                "login_url": "/login/",
            }

            messages.success(
                request,
                "Negocio creado correctamente. Copia los datos de acceso y envíaselos al cliente."
            )

            form = BusinessRegisterForm()

    else:
        form = BusinessRegisterForm()

    return render(
        request,
        "accounts/register.html",
        {
            "form": form,
            "created_business_data": created_business_data,
        }
    )


@never_cache
def logout_user(request):
    logout(request)
    messages.success(
        request,
        "Has cerrado sesión correctamente."
    )
    return redirect("login")


@login_required
def debug_email_test(request):
    """
    VISTA TEMPORAL DE DIAGNÓSTICO — para probar el envío de email
    directamente en producción sin necesitar acceso por Shell (que
    requiere plan de pago en Render). Solo accesible para superusuario.

    Borrar esta vista (y su URL en accounts/urls.py) una vez
    solucionado el problema del envío de emails — no debe quedarse
    para siempre en el proyecto.
    """

    if not request.user.is_superuser:
        return HttpResponse("No autorizado.", status=403)

    target_email = request.GET.get("to", "")

    if not target_email:
        return HttpResponse(
            "Añade el email de destino en la URL, así: "
            "?to=tu_email@ejemplo.com"
        )

    output = [f"EMAIL_HOST = {settings.EMAIL_HOST}"]
    output.append(f"EMAIL_PORT = {settings.EMAIL_PORT}")
    output.append(f"EMAIL_USE_TLS = {settings.EMAIL_USE_TLS}")
    output.append(f"EMAIL_USE_SSL = {settings.EMAIL_USE_SSL}")
    output.append(f"EMAIL_HOST_USER = {settings.EMAIL_HOST_USER}")
    output.append(
        f"EMAIL_HOST_PASSWORD = "
        f"{'(puesta, ' + str(len(settings.EMAIL_HOST_PASSWORD)) + ' caracteres)' if settings.EMAIL_HOST_PASSWORD else '(VACÍA)'}"
    )
    output.append(f"DEFAULT_FROM_EMAIL = {settings.DEFAULT_FROM_EMAIL}")
    output.append("")
    output.append(f"Intentando enviar un email de prueba a: {target_email}")
    output.append("")

    try:
        send_mail(
            subject="Email de prueba - ReserGo",
            message="Esto es un email de prueba para diagnosticar el envío.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[target_email],
            fail_silently=False,
        )
        output.append("✅ ENVIADO SIN ERRORES.")

    except Exception as e:
        output.append("❌ FALLÓ. Error exacto:")
        output.append(f"{type(e).__name__}: {e}")
        output.append("")
        output.append(traceback.format_exc())

    return HttpResponse("\n".join(output), content_type="text/plain; charset=utf-8")


@login_required
def change_password(request):
    """
    Permite al usuario cambiar su contraseña desde el panel.
    Útil cuando tú le das una contraseña temporal manualmente.
    """

    if request.method == "POST":
        form = PasswordChangeForm(
            user=request.user,
            data=request.POST
        )

        if form.is_valid():
            user = form.save()

            update_session_auth_hash(request, user)

            messages.success(
                request,
                "Tu contraseña se ha cambiado correctamente."
            )

            return redirect("dashboard-home")

        messages.error(
            request,
            "No se pudo cambiar la contraseña. Revisa los datos."
        )

    else:
        form = PasswordChangeForm(user=request.user)

    return render(
        request,
        "accounts/change_password.html",
        {
            "form": form,
        }
    )


def custom_csrf_failure(request, reason=""):
    messages.error(
        request,
        "La sesión ha caducado o el formulario estaba desactualizado. Vuelve a intentarlo."
    )

    if request.user.is_authenticated and request.user.is_superuser:
        return redirect("register_business")

    return redirect("login")