# -*- coding: utf-8 -*-
"""
Created on Fri Apr 24 09:54:05 2026

@author: PRL
"""
from django.urls import path
from .views import (
    dashboard_home,
    update_booking_status,
    create_booking,
    get_availability,
    create_blocked_slot,
    delete_blocked_slot,
    edit_booking,
    delete_booking,
    service_list,
    create_service,
    edit_service,
    delete_service,
    employee_list,
    create_employee,
    edit_employee,
    delete_employee,
    manage_employee_services,
    manage_employee_schedule,
    create_full_day_block,
    edit_business,
)

urlpatterns = [
    path("", dashboard_home, name="dashboard-home"),

    path(
        "booking/<int:booking_id>/status/<str:new_status>/",
        update_booking_status,
        name="update-booking-status"
    ),

    path(
        "new-booking/",
        create_booking,
        name="create-booking"
    ),

    path(
        "availability/",
        get_availability,
        name="dashboard-availability"
    ),

    path(
        "new-block/",
        create_blocked_slot,
        name="create-blocked-slot"
    ),
    path(
    "block/<int:block_id>/delete/",
    delete_blocked_slot,
    name="delete-blocked-slot"
    ),
    path(
    "booking/<int:booking_id>/edit/",
    edit_booking,
    name="edit-booking"
    ),
    path(
    "booking/<int:booking_id>/delete/",
    delete_booking,
    name="delete-booking"
    ),
    path("services/", service_list, name="service-list"),
    path("services/new/", create_service, name="create-service"),
    path("services/<int:service_id>/edit/", edit_service, name="edit-service"),
    path("services/<int:service_id>/delete/", delete_service, name="delete-service"),
    path("employees/", employee_list, name="employee-list"),
    path("employees/new/", create_employee, name="create-employee"),
    path("employees/<int:employee_id>/edit/", edit_employee, name="edit-employee"),
    path("employees/<int:employee_id>/delete/", delete_employee, name="delete-employee"),
    path("employees/<int:employee_id>/services/", manage_employee_services, name="manage-employee-services"),
    path("employees/<int:employee_id>/schedule/",manage_employee_schedule,name="manage-employee-schedule"),
    path("full-day-block/", create_full_day_block, name="create-full-day-block"),
    path("business/settings/", edit_business, name="edit-business"),

]
