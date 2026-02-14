from __future__ import annotations

import os
from decimal import Decimal

from django.conf import settings
from django.db import models


def service_photo_upload_path(instance, filename: str) -> str:
    name = os.path.basename(filename or "photo.jpg")
    order_id = getattr(instance, "order_id", None) or "unknown"
    return f"service_photos/order_{order_id}/{name}"


class CustomerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_profile",
    )
    full_name = models.CharField(max_length=200, blank=True, default="")
    email = models.EmailField(max_length=254, db_index=True)
    phone_number = models.CharField(max_length=40, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.full_name or self.email or f"Customer {self.pk}"


class Bike(models.Model):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="bikes")
    brand = models.CharField(max_length=120, blank=True, default="")
    model = models.CharField(max_length=160, blank=True, default="")
    serial_number = models.CharField(max_length=160, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        base = f"{self.brand} {self.model}".strip()
        return base or f"Bike {self.pk}"


class ServiceOrder(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "Nová"
        IN_PROGRESS = "IN_PROGRESS", "V procese"
        WAITING_PART = "WAITING_PART", "Čakáme na diel"
        READY = "READY", "Pripravené"
        DONE = "DONE", "Hotová"

    bike = models.ForeignKey(Bike, on_delete=models.CASCADE, related_name="service_orders")

    service_code = models.CharField(max_length=40, blank=True, default="")

    issue_description = models.TextField(blank=True, default="")
    work_done = models.TextField(blank=True, default="")

    status = models.CharField(max_length=30, choices=Status.choices, default=Status.NEW, db_index=True)

    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    promised_date = models.DateField(null=True, blank=True, db_index=True)

    checklist = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "completed_at"]),
            models.Index(fields=["status", "promised_date"]),
        ]

    def __str__(self) -> str:
        code = self.service_code or str(self.pk)
        return f"Servis #{code}"


class ServiceOrderPhoto(models.Model):
    order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to=service_photo_upload_path)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Photo {self.pk} for order {self.order_id}"


class Ticket(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Otvorený"
        WAITING_ADMIN = "WAITING_ADMIN", "Čaká na servis"
        WAITING_CUSTOMER = "WAITING_CUSTOMER", "Čaká na zákazníka"
        CLOSED = "CLOSED", "Zatvorený"

    order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name="tickets")
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.OPEN, db_index=True)

    subject = models.CharField(max_length=200, blank=True, default="")
    message = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "updated_at"]),
        ]

    def __str__(self) -> str:
        return f"Ticket {self.pk} order {self.order_id}"


class TicketMessage(models.Model):
    class Role(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Zákazník"
        ADMIN = "ADMIN", "Servis"

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    author_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ticket_messages",
    )
    message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Msg {self.pk} ticket {self.ticket_id}"


class ServiceOrderLog(models.Model):
    class Kind(models.TextChoices):
        SMS = "SMS", "SMS"
        EMAIL_INVITE = "EMAIL_INVITE", "Email pozvánka"
        EMAIL_PROTOCOL = "EMAIL_PROTOCOL", "Email protokol"
        EMAIL_DONE = "EMAIL_DONE", "Email hotová"

    order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name="logs")
    kind = models.CharField(max_length=40, choices=Kind.choices)
    body = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.kind} for order {self.order_id}"
