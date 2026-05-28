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
]