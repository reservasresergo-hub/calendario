from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect


class DemoReadOnlyMiddleware:
    """
    Bloquea cualquier acción de escritura para el usuario demo.

    El usuario demo puede navegar por el panel y ver los datos,
    pero no puede crear, editar, borrar, cancelar ni modificar información.
    """

    DEMO_USERNAME = "demo@resergo.es"

    BLOCKED_METHODS = [
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    ]

    ALLOWED_PATHS = [
        "/logout/",
        "/demo/",
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        is_demo_user = (
            user
            and user.is_authenticated
            and user.username == self.DEMO_USERNAME
        )

        if is_demo_user and request.method in self.BLOCKED_METHODS:
            if any(request.path.startswith(path) for path in self.ALLOWED_PATHS):
                return self.get_response(request)

            if (
                request.headers.get("x-requested-with") == "XMLHttpRequest"
                or request.path.startswith("/api/")
            ):
                return JsonResponse(
                    {
                        "error": (
                            "La demo es solo de lectura. "
                            "No se pueden guardar cambios."
                        )
                    },
                    status=403
                )

            messages.warning(
                request,
                (
                    "La demo es solo de lectura. "
                    "Puedes navegar por el panel, pero no puedes guardar cambios."
                )
            )

            return redirect(
                request.META.get(
                    "HTTP_REFERER",
                    "/dashboard/?week=2026-05-25"
                )
            )

        return self.get_response(request)