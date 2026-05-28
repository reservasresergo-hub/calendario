# -*- coding: utf-8 -*-
"""
Created on Tue Apr 14 19:32:29 2026

@author: PRL
"""

from django.urls import path
from .views import availability_view, create_booking_view, services_view

urlpatterns = [
    path("availability/", availability_view, name="availability"),
    path("bookings/", create_booking_view, name="create-booking"),
    path("services/", services_view, name="services"),
]