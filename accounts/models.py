from django.db import models


class LoginAttempt(models.Model):
    """
    Registra los intentos de inicio de sesión fallidos, por email, para
    poder bloquear temporalmente una cuenta si alguien está probando
    contraseñas a lo bruto (ataque de fuerza bruta). Antes no había
    ningún límite: se podían probar miles de contraseñas seguidas
    contra la misma cuenta sin ningún tipo de bloqueo ni retraso.
    """

    username = models.CharField(max_length=255, db_index=True)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-attempted_at"]