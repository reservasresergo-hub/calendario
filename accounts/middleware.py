# -*- coding: utf-8 -*-
"""
Created on Thu May 21 15:32:44 2026

@author: PRL
"""

from django.contrib import messages
from django.shortcuts import redirect


class DemoReadOnlyMiddleware:
    """
    Bloquea acciones de escritura para el usuario demo.

    El usuario demo puede ver el panel, pero no puede modificar datos.
    """

    DEMO_USERNAME = "demo@reservaspro.com"

    BLOCKED_PATH_PREFIXES = [
        "/dashboard/",
        "/change-password/",
    ]

    BLOCKED_METHODS = [
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        if (
            user
            and user.is_authenticated
            and user.username == self.DEMO_USERNAME
            and request.method in self.BLOCKED_METHODS
            and self.is_blocked_path(request.path)
        ):
            messages.error(
                request,
                "La demo es solo lectura. No se pueden guardar cambios."
            )
            return redirect("dashboard-home")

        return self.get_response(request)

    def is_blocked_path(self, path):
        for prefix in self.BLOCKED_PATH_PREFIXES:
            if path.startswith(prefix):
                return True

        return False