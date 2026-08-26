"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve as serve_static

from accounts.views import login_user, logout_user, demo_login

urlpatterns = [
    path("admin/", admin.site.urls),

    path("api/", include("api.urls")),

    path("login/",login_user,name="login"),

    path("logout/",logout_user,name="logout"),

    path("dashboard/", include("dashboard.urls")),
    path("demo/", demo_login, name="demo_login"),

    path("", include("accounts.urls")),

    path("", include("public_booking.urls")),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
else:
    # WhiteNoise solo sirve los archivos estáticos (STATIC_URL), no los
    # archivos subidos por los negocios (logos, en MEDIA_URL). Sin esta
    # ruta, cualquier logo subido da 404 en producción, aunque el archivo
    # sí se haya guardado correctamente en el servidor.
    #
    # Aviso importante que sigue pendiente: en Render, el disco donde se
    # guardan estos archivos no es persistente entre despliegues — un
    # logo subido puede desaparecer en el siguiente deploy. Para que
    # los logos sean fiables a largo plazo, lo correcto es moverlos a
    # almacenamiento en la nube (por ejemplo Cloudinary o S3), no solo
    # arreglar esta ruta.
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            serve_static,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]