from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password


class BusinessRegisterForm(forms.Form):
    first_name = forms.CharField(
        max_length=100,
        label="Nombre"
    )

    last_name = forms.CharField(
        max_length=100,
        label="Apellidos",
        required=False
    )

    email = forms.EmailField(
        label="Email"
    )

    password = forms.CharField(
        widget=forms.PasswordInput,
        label="Contraseña"
    )

    business_name = forms.CharField(
        max_length=150,
        label="Nombre del negocio"
    )

    business_phone = forms.CharField(
        max_length=20,
        label="Teléfono del negocio",
        required=False
    )

    def clean_email(self):
        email = self.cleaned_data["email"]

        if User.objects.filter(username=email).exists():
            raise forms.ValidationError(
                "Ya existe una cuenta con este email."
            )

        return email

    def clean_password(self):
        password = self.cleaned_data["password"]

        # Aplica las mismas reglas de seguridad que ya usa el cambio de
        # contraseña normal (longitud mínima, que no sea una contraseña
        # demasiado común, que no sea solo números, etc.). Antes este
        # formulario no comprobaba nada, así que se podía crear una
        # cuenta de negocio real con una contraseña como "1234".
        validate_password(password)

        return password