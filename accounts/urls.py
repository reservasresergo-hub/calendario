from django.urls import path
from . import views


urlpatterns = [
    path(
        "",
        views.home,
        name="home"
    ),

    path(
        "demo/",
        views.demo_login,
        name="demo_login"
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
]
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