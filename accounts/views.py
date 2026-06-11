from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from businesses.models import Business
from .forms import BusinessRegisterForm



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

    if request.user.is_authenticated:
        return redirect("dashboard-home")

    if request.method == "POST":
        email = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=email,
            password=password
        )

        if user is not None:
            login(request, user)
            return redirect("dashboard-home")

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