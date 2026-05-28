from django import forms
from django.contrib.auth.models import User


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