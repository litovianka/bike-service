# service/admin.py
from __future__ import annotations

from django.contrib import admin
from django.utils import timezone

from .models import (
    Bike,
    CustomerProfile,
    ServiceOrder,
    ServiceOrderLog,
    ServiceOrderPhoto,
    Ticket,
    TicketMessage,
)
from .tasks import send_plain_email_task


def _send_email_safely(subject: str, body: str, to_list: list[str]) -> None:
    if not to_list:
        return
    send_plain_email_task.delay(subject=subject, body=body, to_list=to_list)


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "email", "phone_number", "created_at")
    search_fields = ("full_name", "email", "phone_number")
    ordering = ("full_name", "email")
    readonly_fields = ("created_at",)


@admin.register(Bike)
class BikeAdmin(admin.ModelAdmin):
    list_display = ("id", "brand", "model", "serial_number", "customer", "created_at")
    search_fields = ("brand", "model", "serial_number", "customer__full_name", "customer__email")
    list_filter = ("brand",)
    ordering = ("brand", "model", "serial_number")
    readonly_fields = ("created_at",)


@admin.register(ServiceOrder)
class ServiceOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "service_code", "bike", "status", "promised_date", "price", "created_at", "completed_at")
    search_fields = (
        "id",
        "service_code",
        "bike__brand",
        "bike__model",
        "bike__serial_number",
        "bike__customer__full_name",
        "bike__customer__email",
        "issue_description",
        "work_done",
    )
    list_filter = ("status",)
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "completed_at")

    def save_model(self, request, obj: ServiceOrder, form, change):
        status_before = None
        completed_before = None

        if change and obj.pk:
            try:
                prev = ServiceOrder.objects.only("status", "completed_at").get(pk=obj.pk)
                status_before = prev.status
                completed_before = prev.completed_at
            except Exception:
                status_before = None
                completed_before = None

        super().save_model(request, obj, form, change)

        just_completed = False
        if obj.status == ServiceOrder.Status.DONE and obj.completed_at is None:
            obj.completed_at = timezone.now()
            obj.save(update_fields=["completed_at"])
            just_completed = True

        if obj.status == ServiceOrder.Status.DONE and status_before != ServiceOrder.Status.DONE:
            just_completed = True

        if just_completed and completed_before is None:
            customer_email = ""
            customer_name = ""
            if obj.bike and obj.bike.customer:
                customer_email = (obj.bike.customer.email or "").strip()
                customer_name = (obj.bike.customer.full_name or "").strip()

            if customer_email:
                code = obj.service_code or str(obj.id)
                _send_email_safely(
                    subject=f"Servis hotový #{code}",
                    body=(
                        f"Ahoj {customer_name or customer_email},\n\n"
                        f"Servisná objednávka #{code} je hotová.\n\n"
                        f"Čo sa urobilo:\n{obj.work_done or ''}\n\n"
                        f"Cena: {obj.price} €\n"
                    ),
                    to_list=[customer_email],
                )

                ServiceOrderLog.objects.create(
                    order=obj,
                    kind=ServiceOrderLog.Kind.EMAIL_DONE,
                    body=f"Email DONE odoslaný na {customer_email}",
                    created_by=request.user,
                )


@admin.register(ServiceOrderPhoto)
class ServiceOrderPhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "created_at")
    search_fields = ("id", "order__id", "order__bike__serial_number")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)


class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 1
    fields = ("role", "author_user", "message", "created_at")
    readonly_fields = ("created_at",)

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        original_save_new = formset.save_new

        def save_new(form, commit=True):
            instance: TicketMessage = original_save_new(form, commit=False)
            instance.role = TicketMessage.Role.ADMIN
            if instance.author_user_id is None:
                instance.author_user = request.user
            if commit:
                instance.save()
                form.save_m2m()
            return instance

        formset.save_new = save_new
        return formset


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "status", "order", "updated_at", "created_at")
    list_filter = ("status",)
    search_fields = (
        "id",
        "subject",
        "message",
        "order__id",
        "order__service_code",
        "order__bike__serial_number",
        "order__bike__brand",
        "order__bike__model",
        "order__bike__customer__full_name",
        "order__bike__customer__email",
    )
    ordering = ("-updated_at",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (TicketMessageInline,)

    def save_formset(self, request, form, formset, change):
        new_messages = []
        instances = formset.save(commit=False)

        for inst in instances:
            if isinstance(inst, TicketMessage) and inst.pk is None:
                inst.role = TicketMessage.Role.ADMIN
                if inst.author_user_id is None:
                    inst.author_user = request.user
                new_messages.append(inst)
            inst.save()

        formset.save_m2m()

        if new_messages:
            ticket: Ticket = form.instance
            ticket.status = Ticket.Status.WAITING_CUSTOMER
            ticket.updated_at = timezone.now()
            ticket.save(update_fields=["status", "updated_at"])

            customer_email = (ticket.order.bike.customer.email or "").strip()
            customer_name = (ticket.order.bike.customer.full_name or "").strip()

            if customer_email:
                last_msg = new_messages[-1].message or ""
                _send_email_safely(
                    subject=f"Odpoveď zo servisu k ticketu #{ticket.id}",
                    body=(
                        f"Ahoj {customer_name or customer_email},\n\n"
                        f"Servis odpovedal na tvoj ticket #{ticket.id}.\n\n"
                        f"Správa:\n{last_msg}\n\n"
                        f"Prihlás sa do zóny a odpíš priamo v tickete.\n"
                    ),
                    to_list=[customer_email],
                )


@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket", "role", "author_user", "created_at")
    search_fields = ("id", "ticket__id", "message", "author_user__username")
    list_filter = ("role",)
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)


@admin.register(ServiceOrderLog)
class ServiceOrderLogAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "kind", "created_by", "created_at")
    list_filter = ("kind",)
    search_fields = ("order__id", "order__service_code", "body", "created_by__username")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
