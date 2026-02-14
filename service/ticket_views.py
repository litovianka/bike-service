# service/ticket_views.py

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import ServiceOrder, Ticket, TicketMessage
from .view_common import _get_profile_for_user, _is_staff, invalidate_dashboard_cache


def _touch(ticket: Ticket):
    if hasattr(ticket, "updated_at"):
        ticket.updated_at = timezone.now()
        ticket.save(update_fields=["updated_at"])


@login_required
def customer_ticket_list(request):
    if request.user.is_staff:
        return redirect("service_panel")

    profile = _get_profile_for_user(request.user)
    if not profile:
        messages.error(request, "Chýba zákaznícky profil.")
        return redirect("customer_home")

    tickets_qs = (
        Ticket.objects.select_related("order", "order__bike", "order__bike__customer")
        .filter(order__bike__customer=profile)
        .order_by("-updated_at", "-created_at")
    )
    page_obj = Paginator(tickets_qs, 30).get_page(request.GET.get("page", 1))

    return render(request, "customer_ticket_list.html", {"tickets": page_obj.object_list, "page_obj": page_obj})


@login_required
def customer_ticket_detail(request, ticket_id: int):
    if request.user.is_staff:
        return redirect("service_panel")

    profile = _get_profile_for_user(request.user)
    if not profile:
        messages.error(request, "Chýba zákaznícky profil.")
        return redirect("customer_home")

    ticket = get_object_or_404(
        Ticket.objects.select_related("order", "order__bike", "order__bike__customer").prefetch_related("messages"),
        pk=ticket_id,
        order__bike__customer=profile,
    )

    is_closed = ticket.status == Ticket.Status.CLOSED

    if request.method == "POST":
        if is_closed:
            messages.error(request, "Ticket je zatvorený.")
            return redirect("customer_ticket_detail", ticket_id=ticket.id)

        text = (request.POST.get("message", "") or "").strip()
        if not text:
            messages.error(request, "Správa nemôže byť prázdna.")
            return redirect("customer_ticket_detail", ticket_id=ticket.id)

        TicketMessage.objects.create(
            ticket=ticket,
            role=TicketMessage.Role.CUSTOMER,
            author_user=request.user,
            message=text,
        )
        ticket.status = Ticket.Status.WAITING_ADMIN
        ticket.save(update_fields=["status"])
        _touch(ticket)
        invalidate_dashboard_cache()

        messages.success(request, "Správa bola odoslaná.")
        return redirect("customer_ticket_detail", ticket_id=ticket.id)

    return render(
        request,
        "customer_ticket_detail.html",
        {
            "ticket": ticket,
            "is_closed": is_closed,
        },
    )


@login_required
def customer_ticket_create(request, order_id: int):
    if request.user.is_staff:
        return redirect("service_panel")

    profile = _get_profile_for_user(request.user)
    if not profile:
        messages.error(request, "Chýba zákaznícky profil.")
        return redirect("customer_home")

    order = get_object_or_404(
        ServiceOrder.objects.select_related("bike", "bike__customer"),
        pk=order_id,
        bike__customer=profile,
    )

    if request.method == "POST":
        subject = (request.POST.get("subject", "") or "").strip()
        text = (request.POST.get("message", "") or "").strip()

        if not subject:
            code = order.service_code or str(order.id)
            subject = f"Otázka k servisu #{code}"

        ticket = Ticket.objects.create(
            order=order,
            subject=subject,
            status=Ticket.Status.WAITING_ADMIN,
        )
        _touch(ticket)
        invalidate_dashboard_cache()

        if text:
            TicketMessage.objects.create(
                ticket=ticket,
                role=TicketMessage.Role.CUSTOMER,
                author_user=request.user,
                message=text,
            )
            _touch(ticket)

        messages.success(request, "Ticket bol vytvorený.")
        return redirect("customer_ticket_detail", ticket_id=ticket.id)

    return render(request, "customer_ticket_create.html", {"order": order})


@login_required
@user_passes_test(_is_staff)
def admin_ticket_list(request):
    status = (request.GET.get("status", "") or "").strip()
    q = (request.GET.get("q", "") or "").strip()

    tickets = Ticket.objects.select_related("order", "order__bike", "order__bike__customer")

    if status and status in dict(Ticket.Status.choices):
        tickets = tickets.filter(status=status)

    if q:
        tickets = tickets.filter(
            Q(id__icontains=q)
            | Q(subject__icontains=q)
            | Q(message__icontains=q)
            | Q(order__id__icontains=q)
            | Q(order__service_code__icontains=q)
            | Q(order__bike__brand__icontains=q)
            | Q(order__bike__model__icontains=q)
            | Q(order__bike__serial_number__icontains=q)
            | Q(order__bike__customer__full_name__icontains=q)
            | Q(order__bike__customer__email__icontains=q)
        )

    page_obj = Paginator(tickets.order_by("-updated_at", "-created_at"), 40).get_page(request.GET.get("page", 1))

    return render(
        request,
        "admin_ticket_list.html",
        {
            "tickets": page_obj.object_list,
            "page_obj": page_obj,
            "active_status": status,
            "q": q,
        },
    )


@login_required
@user_passes_test(_is_staff)
def admin_ticket_detail(request, ticket_id: int):
    ticket = get_object_or_404(
        Ticket.objects.select_related("order", "order__bike", "order__bike__customer").prefetch_related("messages"),
        pk=ticket_id,
    )

    is_closed = ticket.status == Ticket.Status.CLOSED
    status_choices = Ticket.Status.choices

    if request.method == "POST":
        if request.POST.get("close") == "1":
            ticket.status = Ticket.Status.CLOSED
            ticket.save(update_fields=["status"])
            _touch(ticket)
            invalidate_dashboard_cache()
            messages.success(request, "Ticket bol zatvorený.")
            return redirect("admin_ticket_detail", ticket_id=ticket.id)

        new_status = (request.POST.get("status", "") or "").strip()
        if new_status and new_status in dict(Ticket.Status.choices):
            ticket.status = new_status
            ticket.save(update_fields=["status"])
            _touch(ticket)
            invalidate_dashboard_cache()

        if ticket.status == Ticket.Status.CLOSED:
            messages.success(request, "Ticket bol uložený.")
            return redirect("admin_ticket_detail", ticket_id=ticket.id)

        text = (request.POST.get("message", "") or "").strip()
        if text:
            TicketMessage.objects.create(
                ticket=ticket,
                role=TicketMessage.Role.ADMIN,
                author_user=request.user,
                message=text,
            )
            ticket.status = Ticket.Status.WAITING_CUSTOMER
            ticket.save(update_fields=["status"])
            _touch(ticket)
            invalidate_dashboard_cache()
            messages.success(request, "Odpoveď bola odoslaná.")
            return redirect("admin_ticket_detail", ticket_id=ticket.id)

        messages.success(request, "Ticket bol uložený.")
        return redirect("admin_ticket_detail", ticket_id=ticket.id)

    return render(
        request,
        "admin_ticket_detail.html",
        {
            "ticket": ticket,
            "is_closed": is_closed,
            "status_choices": status_choices,
        },
    )
