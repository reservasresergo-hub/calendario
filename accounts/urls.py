from django.urls import path
from . import views


urlpatterns = [
    path(
        "",
        views.home,
        name="home"
    ),

    path(
        "register/",
        views.register_business,
        name="register_business"
    ),

    path(
        "change-password/",
        views.change_password,
        name="change_password"
    ),

    path(
        "aviso-legal/",
        views.aviso_legal,
        name="aviso_legal"
    ),

    path(
        "politica-privacidad/",
        views.politica_privacidad,
        name="politica_privacidad"
    ),

    path(
        "politica-cookies/",
        views.politica_cookies,
        name="politica_cookies"
    ),

    path(
        "condiciones-uso/",
        views.condiciones_uso,
        name="condiciones_uso"
    ),

    # TEMPORAL — quitar esta línea junto con la vista debug_email_test
    # una vez solucionado el problema del envío de emails.
    path(
        "debug-email-test/",
        views.debug_email_test,
        name="debug_email_test"
    ),
]