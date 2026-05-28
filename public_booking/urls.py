

from django.urls import path
from . import views


urlpatterns = [
    path(
        '<slug:business_slug>/cancelar/<uuid:cancel_token>/',
        views.cancel_booking_public,
        name='cancel-booking-public'
    ),

    path(
        '<slug:business_slug>/',
        views.booking_home,
        name='booking-home'
    ),
]