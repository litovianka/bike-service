from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import Bike, CustomerProfile, ServiceOrder, ServiceOrderLog, Ticket
from .pdf_utils import build_service_protocol_pdf
from .view_common import (
    CHECKLIST_DEFS,
    SERVICE_PACKAGE_DEFS,
    _build_set_password_url,
    _eta_meta,
    _get_or_create_customer_user,
    _is_staff,
    _parse_date,
    _send_email_safely,
    _send_email_with_attachment_safely,
    _send_sms_safely,
    get_staff_dashboard_counts,
    invalidate_dashboard_cache,
)


def _apply_service_panel_smart_search(orders_qs, query: str):
    q = (query or "").strip()
    if not q:
        return orders_qs

    code_match = re.fullmatch(r"#?\s*(\d+)", q)
    if code_match:
        code = code_match.group(1)
        return orders_qs.filter(Q(id=int(code)) | Q(service_code__icontains=code))

    tokens = [t for t in re.split(r"\s+", q) if t]
    for token in tokens:
        token_phone = re.sub(r"\D+", "", token)
        token_filter = (
            Q(bike__customer__full_name__icontains=token)
            | Q(bike__customer__email__icontains=token)
            | Q(bike__brand__icontains=token)
            | Q(bike__model__icontains=token)
            | Q(bike__serial_number__icontains=token)
            | Q(issue_description__icontains=token)
            | Q(work_done__icontains=token)
            | Q(service_code__icontains=token)
            | Q(tickets__subject__icontains=token)
            | Q(tickets__message__icontains=token)
            | Q(tickets__messages__message__icontains=token)
        )
        if token_phone:
            token_filter |= Q(bike__customer__phone_number__icontains=token_phone)
        orders_qs = orders_qs.filter(token_filter)

    return orders_qs.distinct()


def _invite_customer_to_portal(request, profile: CustomerProfile) -> bool:
    email = (getattr(profile, "email", "") or "").strip().lower()
    full_name = (getattr(profile, "full_name", "") or "").strip()

    if not email:
        return False

    user, created = _get_or_create_customer_user(email=email, full_name=full_name)

    if getattr(profile, "user_id", None) is None:
        profile.user = user
        profile.save(update_fields=["user"])

    login_url = request.build_absolute_uri(reverse("login"))
    set_password_url = _build_set_password_url(request, user)
    intro = "Vytvorili sme ti prístup do BlackBike portálu." if created else "Posielame ti prístup do BlackBike portálu."

    _send_email_safely(
        subject="Pozvánka do BlackBike portálu",
        body=(
            f"Ahoj {full_name or ''}\n\n"
            f"{intro}\n\n"
            f"Nastavenie hesla\n{set_password_url}\n\n"
            f"Prihlásenie nájdeš tu\n{login_url}\n\n"
            f"Link na nastavenie hesla je jednorazový a časovo obmedzený.\n"
        ),
        to_list=[email],
    )
    return True


@login_required
@user_passes_test(_is_staff)
def service_panel(request):
    if request.method == "POST":
        action = (request.POST.get("action", "") or "").strip()

        tab = request.POST.get("tab", "active")
        query = (request.POST.get("q", "") or "").strip()
        status_filter = (request.POST.get("status", "") or "").strip()
        tickets_filter = (request.POST.get("tickets", "") or "").strip()
        done_today_filter = (request.POST.get("done_today", "") or "").strip()
        page_num = (request.POST.get("page", "1") or "1").strip()

        def _redirect_back():
            params = {}
            if tab:
                params["tab"] = tab
            if query:
                params["q"] = query
            if status_filter:
                params["status"] = status_filter
            if tickets_filter:
                params["tickets"] = tickets_filter
            if done_today_filter:
                params["done_today"] = done_today_filter
            if page_num and page_num.isdigit() and int(page_num) > 1:
                params["page"] = page_num
            url = reverse("service_panel")
            if params:
                url = f"{url}?{urlencode(params)}"
            return redirect(url)

        if action == "row_update_status":
            order_id_raw = (request.POST.get("order_id", "") or "").strip()
            new_status = (request.POST.get("new_status", "") or "").strip()

            if order_id_raw.isdigit() and new_status in dict(ServiceOrder.Status.choices):
                order = ServiceOrder.objects.filter(pk=int(order_id_raw)).first()
                if order is not None:
                    order.status = new_status
                    if new_status == ServiceOrder.Status.DONE:
                        if order.completed_at is None:
                            order.completed_at = timezone.now()
                    else:
                        order.completed_at = None
                    order.save(update_fields=["status", "completed_at"])
                    invalidate_dashboard_cache()
                    messages.success(request, "Stav bol uložený.")
                    return _redirect_back()

            messages.error(request, "Nepodarilo sa uložiť stav.")
            return _redirect_back()

        if action == "row_update_eta":
            order_id_raw = (request.POST.get("order_id", "") or "").strip()
            promised_raw = (request.POST.get("promised_date", "") or "").strip()

            if order_id_raw.isdigit():
                promised = _parse_date(promised_raw)
                order = ServiceOrder.objects.filter(pk=int(order_id_raw)).first()
                if order is not None:
                    order.promised_date = promised
                    order.save(update_fields=["promised_date"])
                    invalidate_dashboard_cache()
                    messages.success(request, "Termín bol uložený.")
                    return _redirect_back()

            messages.error(request, "Nepodarilo sa uložiť termín.")
            return _redirect_back()

        return redirect("service_panel")

    tab = request.GET.get("tab", "active")
    query = (request.GET.get("q", "") or "").strip()
    status_filter = (request.GET.get("status", "") or "").strip()
    tickets_filter = (request.GET.get("tickets", "") or "").strip()
    done_today_filter = (request.GET.get("done_today", "") or "").strip()

    orders_qs = ServiceOrder.objects.select_related("bike", "bike__customer").order_by("-created_at")

    if tab == "completed":
        orders_qs = orders_qs.filter(completed_at__isnull=False)
    else:
        orders_qs = orders_qs.filter(completed_at__isnull=True)

    if status_filter in dict(ServiceOrder.Status.choices):
        orders_qs = orders_qs.filter(status=status_filter)

    today = timezone.localdate()

    if done_today_filter == "1":
        orders_qs = orders_qs.filter(completed_at__date=today)

    orders_qs = _apply_service_panel_smart_search(orders_qs, query)

    waiting_statuses = [Ticket.Status.OPEN, Ticket.Status.WAITING_ADMIN]
    if tickets_filter == "waiting":
        orders_qs = orders_qs.filter(tickets__status__in=waiting_statuses).distinct()

    paginator = Paginator(orders_qs, 50)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    orders = list(page_obj.object_list)

    order_ids = [o.id for o in orders]
    waiting_ticket_order_ids = set()
    if order_ids:
        waiting_ticket_order_ids = set(
            Ticket.objects.filter(status__in=waiting_statuses, order_id__in=order_ids)
            .values_list("order_id", flat=True)
            .distinct()
        )

    for o in orders:
        label, chip_class, row_warn = _eta_meta(o, today)
        setattr(o, "_eta_label", label)
        setattr(o, "_eta_chip", chip_class)
        setattr(o, "_eta_warn", bool(row_warn))

    stats = get_staff_dashboard_counts(
        today=today,
        ttl_seconds=int(getattr(settings, "SERVICE_DASHBOARD_CACHE_TTL", 60)),
    )
    waiting_tickets_url = f"{reverse('admin_ticket_list')}?status={Ticket.Status.WAITING_ADMIN}"

    context = {
        "orders": orders,
        "page_obj": page_obj,
        "active_tab": tab,
        "query": query,
        "status_filter": status_filter,
        "tickets_filter": tickets_filter,
        "done_today_filter": done_today_filter,
        "waiting_ticket_order_ids": waiting_ticket_order_ids,
        "waiting_tickets_count": stats["waiting_tickets_count"],
        "waiting_tickets_url": waiting_tickets_url,
        "stat_orders_new": stats["stat_orders_new"],
        "stat_orders_in_progress": stats["stat_orders_in_progress"],
        "unfinished_count": stats["unfinished_count"],
        "open_tickets_count": stats["open_tickets_count"],
        "completed_last_7_days": stats["completed_last_7_days"],
        "avg_repair_days": stats["avg_repair_days"],
        "STATUS_NEW": ServiceOrder.Status.NEW,
        "STATUS_IN_PROGRESS": ServiceOrder.Status.IN_PROGRESS,
        "STATUS_DONE": ServiceOrder.Status.DONE,
        "status_choices": ServiceOrder.Status.choices,
    }
    return render(request, "servis_panel.html", context)


@login_required
@user_passes_test(_is_staff)
def service_order_protocol_pdf(request, order_id: int):
    order = get_object_or_404(ServiceOrder.objects.select_related("bike", "bike__customer"), pk=order_id)

    code = order.service_code or str(order.id)
    customer = order.bike.customer
    customer_name = customer.full_name or customer.email
    customer_email = customer.email
    customer_phone = customer.phone_number or ""

    bike_name = f"{order.bike.brand} {order.bike.model}".strip()
    serial_number = order.bike.serial_number or ""

    status_label = order.get_status_display() if hasattr(order, "get_status_display") else order.status
    created_at_str = timezone.localtime(order.created_at).strftime("%d.%m.%Y %H:%M")
    promised_date_str = order.promised_date.strftime("%d.%m.%Y") if order.promised_date else ""
    completed_at_str = timezone.localtime(order.completed_at).strftime("%d.%m.%Y %H:%M") if order.completed_at else ""
    price_str = f"{order.price} €"

    checklist_items = []
    for key, label in CHECKLIST_DEFS:
        checklist_items.append((label, bool((order.checklist or {}).get(key))))

    pdf_bytes = build_service_protocol_pdf(
        order_code=code,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        bike_name=bike_name,
        serial_number=serial_number,
        status_label=status_label,
        created_at_str=created_at_str,
        promised_date_str=promised_date_str,
        completed_at_str=completed_at_str,
        price_str=price_str,
        issue_description=order.issue_description or "",
        work_done=order.work_done or "",
        checklist_items=checklist_items,
    )

    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="servis_protokol_{code}.pdf"'
    return resp


@login_required
@user_passes_test(_is_staff)
def service_order_admin_detail(request, order_id):
    order = get_object_or_404(
        ServiceOrder.objects.select_related("bike", "bike__customer"),
        pk=order_id,
    )
    photos = list(order.photos.all().order_by("-created_at"))
    customer_history_qs = (
        ServiceOrder.objects.filter(bike__customer=order.bike.customer)
        .exclude(pk=order.pk)
        .select_related("bike")
        .order_by("-created_at")
    )
    customer_recent_orders = list(customer_history_qs[:5])
    customer_total_orders = customer_history_qs.count() + 1
    customer_paid_total = (
        ServiceOrder.objects.filter(bike__customer=order.bike.customer, completed_at__isnull=False).aggregate(total=Sum("price")).get("total")
        or Decimal("0.00")
    )

    if not isinstance(order.checklist, dict):
        order.checklist = {}

    if request.method == "POST":
        action = (request.POST.get("action", "") or "").strip()

        if action == "invite_customer_portal":
            profile = order.bike.customer
            ok = _invite_customer_to_portal(request, profile)
            if ok:
                ServiceOrderLog.objects.create(
                    order=order,
                    kind=ServiceOrderLog.Kind.EMAIL_INVITE,
                    body=f"Pozvánka do portálu odoslaná na {getattr(profile, 'email', '')}",
                    created_by=request.user,
                )
                messages.success(request, "Pozvánka do portálu bola odoslaná.")
            else:
                messages.error(request, "Pozvánku sa nepodarilo odoslať. Skontroluj email zákazníka.")
            return redirect("service_order_admin_detail", order_id=order.id)

        if action == "send_sms":
            phone = (request.POST.get("sms_phone", "") or "").strip()
            text = (request.POST.get("sms_text", "") or "").strip()
            ok = _send_sms_safely(phone=phone, text=text)
            if ok:
                ServiceOrderLog.objects.create(
                    order=order,
                    kind=ServiceOrderLog.Kind.SMS,
                    body=f"To {phone}: {text}",
                    created_by=request.user,
                )
                messages.success(request, "SMS bola zaradená do odoslania.")
            else:
                messages.error(request, "SMS sa nepodarilo zaradiť do odoslania.")
            return redirect("service_order_admin_detail", order_id=order.id)

        if action == "send_protocol_email":
            code = order.service_code or str(order.id)
            to_email = (order.bike.customer.email or "").strip()
            if not to_email:
                messages.error(request, "Zákazník nemá email.")
                return redirect("service_order_admin_detail", order_id=order.id)

            checklist_lines = []
            for key, label in CHECKLIST_DEFS:
                if bool((order.checklist or {}).get(key)):
                    checklist_lines.append(f"OK: {label}")
            checklist_text = "\n".join(checklist_lines) if checklist_lines else "Checklist nebol vyplnený."

            pdf_bytes = build_service_protocol_pdf(
                order_code=code,
                customer_name=order.bike.customer.full_name or order.bike.customer.email,
                customer_email=order.bike.customer.email,
                customer_phone=order.bike.customer.phone_number or "",
                bike_name=f"{order.bike.brand} {order.bike.model}".strip(),
                serial_number=order.bike.serial_number or "",
                status_label=order.get_status_display(),
                created_at_str=timezone.localtime(order.created_at).strftime("%d.%m.%Y %H:%M"),
                promised_date_str=order.promised_date.strftime("%d.%m.%Y") if order.promised_date else "",
                completed_at_str=timezone.localtime(order.completed_at).strftime("%d.%m.%Y %H:%M") if order.completed_at else "",
                price_str=f"{order.price} €",
                issue_description=order.issue_description or "",
                work_done=order.work_done or "",
                checklist_items=[(label, bool((order.checklist or {}).get(key))) for key, label in CHECKLIST_DEFS],
            )

            ok = _send_email_with_attachment_safely(
                subject=f"Servis protokol #{code}",
                body=(
                    f"Ahoj {order.bike.customer.full_name or ''}\n\n"
                    f"V prílohe posielame servis protokol k zákazke #{code}.\n\n"
                    f"Checklist\n{checklist_text}\n\n"
                    f"Cena: {order.price} €\n"
                ),
                to_list=[to_email],
                filename=f"servis_protokol_{code}.pdf",
                pdf_bytes=pdf_bytes,
            )

            if ok:
                ServiceOrderLog.objects.create(
                    order=order,
                    kind=ServiceOrderLog.Kind.EMAIL_PROTOCOL,
                    body=f"To {to_email}: servis_protokol_{code}.pdf",
                    created_by=request.user,
                )
                messages.success(request, "Protokol bol zaradený do odoslania.")
            else:
                messages.error(request, "Email sa nepodarilo zaradiť do odoslania.")
            return redirect("service_order_admin_detail", order_id=order.id)

        if action == "apply_service_package":
            package_key = (request.POST.get("service_package", "") or "").strip()
            package = SERVICE_PACKAGE_DEFS.get(package_key)
            if package is None:
                messages.error(request, "Vybraný balík neexistuje.")
                return redirect("service_order_admin_detail", order_id=order.id)

            order.price = package["price"]
            order.work_done = package["work_done"]
            order.checklist = {key: key in package["checklist_keys"] for key, _ in CHECKLIST_DEFS}
            order.save(update_fields=["price", "work_done", "checklist"])
            invalidate_dashboard_cache()
            messages.success(request, f"Balík „{package['label']}“ bol aplikovaný.")
            return redirect("service_order_admin_detail", order_id=order.id)

        status = (request.POST.get("status", "") or "").strip()
        price_raw = (request.POST.get("price", "") or "").strip()
        issue_description = (request.POST.get("issue_description", "") or "").strip()
        work_done = (request.POST.get("work_done", "") or "").strip()
        promised_date_raw = (request.POST.get("promised_date", "") or "").strip()

        if status in dict(ServiceOrder.Status.choices):
            order.status = status

        promised = _parse_date(promised_date_raw)
        order.promised_date = promised

        # Checklist fields may be absent when checklist UI is hidden; keep existing data in that case.
        checklist_keys = [f"cl_{key}" for key, _label in CHECKLIST_DEFS]
        if any(k in request.POST for k in checklist_keys):
            new_checklist = {}
            for key, _label in CHECKLIST_DEFS:
                new_checklist[key] = bool(request.POST.get(f"cl_{key}"))
            order.checklist = new_checklist

        if price_raw:
            try:
                normalized = price_raw.replace(",", ".")
                order.price = Decimal(normalized)
            except (InvalidOperation, ValueError):
                messages.error(request, "Cena nie je v správnom formáte.")
                return render(
                    request,
                    "service_order_admin_detail.html",
                    {
                        "order": order,
                        "photos": photos,
                        "status_choices": ServiceOrder.Status.choices,
                        "checklist_defs": CHECKLIST_DEFS,
                        "service_packages": SERVICE_PACKAGE_DEFS.items(),
                        "customer_recent_orders": customer_recent_orders,
                        "customer_total_orders": customer_total_orders,
                        "customer_paid_total": customer_paid_total,
                    },
                )

        order.issue_description = issue_description
        order.work_done = work_done

        just_completed = False
        if order.status == ServiceOrder.Status.DONE and order.completed_at is None:
            order.completed_at = timezone.now()
            just_completed = True

        if order.status != ServiceOrder.Status.DONE:
            order.completed_at = None

        order.save()
        invalidate_dashboard_cache()

        if just_completed and order.bike and order.bike.customer and order.bike.customer.email:
            code = order.service_code or str(order.id)

            checklist_lines = []
            for key, label in CHECKLIST_DEFS:
                if bool((order.checklist or {}).get(key)):
                    checklist_lines.append(f"OK: {label}")
            checklist_text = "\n".join(checklist_lines) if checklist_lines else "Checklist nebol vyplnený."

            _send_email_safely(
                subject=f"Servis hotový #{code}",
                body=(
                    f"Ahoj {order.bike.customer.full_name},\n\n"
                    f"Servisná objednávka #{code} je hotová.\n\n"
                    f"Čo sa urobilo:\n{order.work_done}\n\n"
                    f"Checklist:\n{checklist_text}\n\n"
                    f"Cena: {order.price} €\n"
                ),
                to_list=[order.bike.customer.email],
            )

            ServiceOrderLog.objects.create(
                order=order,
                kind=ServiceOrderLog.Kind.EMAIL_DONE,
                body=f"To {order.bike.customer.email}: servis hotový",
                created_by=request.user,
            )

        messages.success(request, "Servisná objednávka bola uložená.")
        return redirect("service_order_admin_detail", order_id=order.id)

    return render(
        request,
        "service_order_admin_detail.html",
        {
            "order": order,
            "photos": photos,
            "status_choices": ServiceOrder.Status.choices,
            "checklist_defs": CHECKLIST_DEFS,
            "service_packages": SERVICE_PACKAGE_DEFS.items(),
            "customer_recent_orders": customer_recent_orders,
            "customer_total_orders": customer_total_orders,
            "customer_paid_total": customer_paid_total,
        },
    )


@login_required
@user_passes_test(_is_staff)
def create_customer_with_bike(request):
    if request.method == "POST":
        full_name = (request.POST.get("full_name", "") or "").strip()
        email = (request.POST.get("email", "") or "").strip().lower()
        phone_number = (request.POST.get("phone_number", "") or "").strip()
        brand = (request.POST.get("brand", "") or "").strip()
        model = (request.POST.get("model", "") or "").strip()
        serial_number = (request.POST.get("serial_number", "") or "").strip()

        if not full_name or not email or not brand:
            messages.error(request, "Vyplň meno, email a bicykel.")
            return redirect("create_customer_with_bike")

        profile = CustomerProfile.objects.filter(email__iexact=email).first()
        user, user_created = _get_or_create_customer_user(email=email, full_name=full_name)

        if profile is None:
            profile = CustomerProfile.objects.create(
                user=user,
                full_name=full_name,
                email=email,
                phone_number=phone_number,
            )
        else:
            if profile.user_id is None:
                profile.user = user
            profile.full_name = full_name
            profile.phone_number = phone_number
            profile.save()

        Bike.objects.create(
            customer=profile,
            brand=brand,
            model=model,
            serial_number=serial_number,
        )

        if user_created:
            login_url = request.build_absolute_uri(reverse("login"))
            set_password_url = _build_set_password_url(request, user)
            _send_email_safely(
                subject="Prihlasovacie údaje do Bike Service",
                body=(
                    f"Ahoj {full_name}\n\n"
                    f"Vytvorili sme ti prístup do Bike Service.\n\n"
                    f"Nastavenie hesla\n{set_password_url}\n\n"
                    f"Prihlásenie\nMeno: {user.username}\n\n"
                    f"Prihlásenie nájdeš tu\n{login_url}\n"
                ),
                to_list=[email],
            )

        messages.success(request, "Zákazník bol vytvorený.")
        return redirect("service_panel")

    return render(request, "create_customer_with_bike.html")


@login_required
@user_passes_test(_is_staff)
def quick_create_customer_with_bike(request):
    if request.method != "POST":
        return redirect("service_panel")

    full_name = (request.POST.get("qc_full_name", "") or "").strip()
    email = (request.POST.get("qc_email", "") or "").strip().lower()
    phone_number = (request.POST.get("qc_phone_number", "") or "").strip()
    brand = (request.POST.get("qc_brand", "") or "").strip()
    model = (request.POST.get("qc_model", "") or "").strip()
    serial_number = (request.POST.get("qc_serial_number", "") or "").strip()

    if not full_name or not email or not brand:
        messages.error(request, "Vyplň meno, email a bicykel.")
        return redirect("service_panel")

    profile = CustomerProfile.objects.filter(email__iexact=email).first()
    user, user_created = _get_or_create_customer_user(email=email, full_name=full_name)

    if profile is None:
        profile = CustomerProfile.objects.create(
            user=user,
            full_name=full_name,
            email=email,
            phone_number=phone_number,
        )
    else:
        if profile.user_id is None:
            profile.user = user
        profile.full_name = full_name
        profile.phone_number = phone_number
        profile.save()

    Bike.objects.create(
        customer=profile,
        brand=brand,
        model=model,
        serial_number=serial_number,
    )

    if user_created:
        login_url = request.build_absolute_uri(reverse("login"))
        set_password_url = _build_set_password_url(request, user)
        _send_email_safely(
            subject="Prihlasovacie údaje do Bike Service",
            body=(
                f"Ahoj {full_name}\n\n"
                f"Vytvorili sme ti prístup do Bike Service.\n\n"
                f"Nastavenie hesla\n{set_password_url}\n\n"
                f"Prihlásenie\nMeno: {user.username}\n\n"
                f"Prihlásenie nájdeš tu\n{login_url}\n"
            ),
            to_list=[email],
        )

    messages.success(request, "Zákazník bol pridaný.")
    return redirect("service_panel")


@login_required
@user_passes_test(_is_staff)
def create_service_order(request):
    customers = CustomerProfile.objects.order_by("full_name", "email")
    customer_id = (request.GET.get("customer_id", "") or "").strip()
    selected_customer = None
    bikes = Bike.objects.none()
    pref_bike = None

    if customer_id.isdigit():
        selected_customer = CustomerProfile.objects.filter(pk=int(customer_id)).first()
        if selected_customer is not None:
            bikes = Bike.objects.filter(customer=selected_customer).order_by("brand", "model")
            pref_bike = bikes.first()

    if request.method == "POST":
        bike_id = (request.POST.get("bike_id", "") or "").strip()
        edit_customer_id = (request.POST.get("edit_customer_id", "") or "").strip()

        new_full_name = (request.POST.get("new_full_name", "") or "").strip()
        new_email = (request.POST.get("new_email", "") or "").strip().lower()
        new_phone = (request.POST.get("new_phone_number", "") or "").strip()
        new_brand = (request.POST.get("new_brand", "") or "").strip()
        new_model = (request.POST.get("new_model", "") or "").strip()
        new_serial = (request.POST.get("new_serial_number", "") or "").strip()

        issue_description = (request.POST.get("issue_description", "") or "").strip()

        if bike_id.isdigit():
            bike = get_object_or_404(Bike.objects.select_related("customer"), pk=int(bike_id))
            order = ServiceOrder.objects.create(
                bike=bike,
                issue_description=issue_description,
                status=ServiceOrder.Status.NEW,
            )
            invalidate_dashboard_cache()
            code = order.service_code or str(order.id)
            messages.success(request, f"Servisná objednávka #{code} bola vytvorená.")
            return redirect("service_order_admin_detail", order_id=order.id)

        if not new_full_name or not new_email or not new_brand:
            messages.error(request, "Vyplň meno, email a aspoň značku bicykla, alebo vyber existujúci bicykel.")
            return redirect("create_service_order")

        profile = None
        if edit_customer_id.isdigit():
            profile = CustomerProfile.objects.filter(pk=int(edit_customer_id)).first()

        if profile is not None:
            profile.full_name = new_full_name
            profile.email = new_email
            profile.phone_number = new_phone
            profile.save(update_fields=["full_name", "email", "phone_number"])
            messages.info(request, "Použitý bol existujúci zákazník a údaje sa aktualizovali.")
        else:
            profile = CustomerProfile.objects.filter(email__iexact=new_email).first()
            if profile is None and new_phone:
                profile = CustomerProfile.objects.filter(phone_number=new_phone).first()
            if profile is not None:
                messages.info(request, "Našli sme existujúceho zákazníka podľa emailu/telefónu a použili sme jeho profil.")

        if profile is None:
            profile = CustomerProfile.objects.create(
                user=None,
                full_name=new_full_name,
                email=new_email,
                phone_number=new_phone,
            )
        else:
            if not profile.full_name:
                profile.full_name = new_full_name
            if new_phone and not profile.phone_number:
                profile.phone_number = new_phone
            if not profile.email:
                profile.email = new_email
            profile.save(update_fields=["full_name", "email", "phone_number"])

        bike = Bike.objects.create(
            customer=profile,
            brand=new_brand,
            model=new_model,
            serial_number=new_serial,
        )

        order = ServiceOrder.objects.create(
            bike=bike,
            issue_description=issue_description,
            status=ServiceOrder.Status.NEW,
        )
        invalidate_dashboard_cache()

        code = order.service_code or str(order.id)
        messages.success(request, f"Servisná objednávka #{code} bola vytvorená.")
        return redirect("service_order_admin_detail", order_id=order.id)

    return render(
        request,
        "create_service_order.html",
        {
            "customers": customers,
            "selected_customer": selected_customer,
            "bikes": bikes,
            "edit_mode": selected_customer is not None,
            "new_full_name": (selected_customer.full_name if selected_customer else ""),
            "new_email": (selected_customer.email if selected_customer else ""),
            "new_phone_number": (selected_customer.phone_number if selected_customer else ""),
            "new_brand": (pref_bike.brand if pref_bike else ""),
            "new_model": (pref_bike.model if pref_bike else ""),
            "new_serial_number": (pref_bike.serial_number if pref_bike else ""),
        },
    )
