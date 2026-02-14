from __future__ import annotations

import base64
import hashlib
from datetime import timedelta
from datetime import date
from decimal import Decimal, ROUND_DOWN

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils.encoding import force_bytes

from .models import Bike, CustomerProfile, ServiceOrder, Ticket
from .tasks import send_email_with_attachment_task, send_plain_email_task, send_sms_task

CHECKLIST_DEFS = [
    ("brakes", "Brzdy"),
    ("shifting", "Radenie"),
    ("tyre_pressure", "Tlak v pneumatikách"),
    ("bearings", "Ložiská"),
    ("torque", "Dotiahnutie skrutiek"),
    ("chain", "Reťaz a pohon"),
    ("wheels", "Kolesá a výplet"),
    ("cleaning", "Čistenie"),
]

SERVICE_PACKAGE_DEFS = {
    "basic": {
        "label": "Basic servis",
        "price": Decimal("29.00"),
        "work_done": "Základná kontrola bicykla, dofúkanie pneumatík, kontrola bŕzd a radenia.",
        "checklist_keys": ["brakes", "shifting", "tyre_pressure", "torque"],
    },
    "full": {
        "label": "Full servis",
        "price": Decimal("69.00"),
        "work_done": "Kompletný servis pohonu, bŕzd, radenia, ložísk a finálne čistenie bicykla.",
        "checklist_keys": ["brakes", "shifting", "tyre_pressure", "bearings", "torque", "chain", "wheels", "cleaning"],
    },
    "brake_setup": {
        "label": "Brake setup",
        "price": Decimal("39.00"),
        "work_done": "Nastavenie bŕzd, centrovanie kotúčov, kontrola opotrebenia platničiek a test funkčnosti.",
        "checklist_keys": ["brakes", "torque", "wheels"],
    },
}


def _is_staff(user):
    return bool(getattr(user, "is_staff", False))


def _send_email_safely(subject: str, body: str, to_list: list[str]) -> bool:
    if not to_list:
        return False
    send_plain_email_task.delay(subject=subject, body=body, to_list=to_list)
    return True


def _send_email_with_attachment_safely(
    *,
    subject: str,
    body: str,
    to_list: list[str],
    filename: str,
    pdf_bytes: bytes,
):
    if not to_list or not pdf_bytes:
        return False
    send_email_with_attachment_task.delay(
        subject=subject,
        body=body,
        to_list=to_list,
        filename=filename,
        pdf_base64=base64.b64encode(pdf_bytes).decode("ascii"),
    )
    return True


def _send_sms_safely(phone: str, text: str) -> bool:
    phone = (phone or "").strip()
    text = (text or "").strip()
    if not phone or not text:
        return False
    send_sms_task.delay(phone=phone, text=text)
    return True


def _get_or_create_customer_user(email: str, full_name: str):
    email_norm = (email or "").strip().lower()
    username = email_norm

    user = User.objects.filter(username__iexact=username).first()
    created = False

    if user is None:
        first = ""
        last = ""
        if full_name:
            parts = full_name.split()
            first = parts[0] if parts else ""
            last = " ".join(parts[1:]) if len(parts) > 1 else ""
        user = User.objects.create_user(
            username=username,
            email=email_norm,
            password=None,
            first_name=first,
            last_name=last,
        )
        created = True
    else:
        if not user.email:
            user.email = email_norm
            user.save(update_fields=["email"])

    return user, created


def _build_set_password_url(request, user: User) -> str:
    token = default_token_generator.make_token(user)
    uid = force_bytes(user.pk)
    from django.utils.http import urlsafe_base64_encode

    path = reverse(
        "customer_set_password",
        kwargs={"uidb64": urlsafe_base64_encode(uid), "token": token},
    )
    return request.build_absolute_uri(path)


def _parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except Exception:
        return None


def _eta_meta(order: ServiceOrder, today: date):
    promised = order.promised_date
    if not promised:
        return ("Bez termínu", "chip-gray", False)

    if order.completed_at:
        return (promised.strftime("%d.%m.%Y"), "chip-gray", False)

    if today > promised:
        return (f"Mešká {promised.strftime('%d.%m.%Y')}", "chip-orange", True)

    if today == promised:
        return (f"Dnes {promised.strftime('%d.%m.%Y')}", "chip-blue", True)

    delta = (promised - today).days
    if delta == 1:
        return (f"Zajtra {promised.strftime('%d.%m.%Y')}", "chip-blue", True)

    if delta <= 2:
        return (f"On time {promised.strftime('%d.%m.%Y')}", "chip-blue", False)

    return (promised.strftime("%d.%m.%Y"), "chip-gray", False)


def _gravatar_url(email: str, size: int = 160) -> str | None:
    email_norm = (email or "").strip().lower()
    if not email_norm:
        return None
    h = hashlib.md5(email_norm.encode("utf-8")).hexdigest()
    return f"https://www.gravatar.com/avatar/{h}?s={size}&d=identicon"


def _loyalty_stats_for_profile(profile: CustomerProfile) -> dict:
    total_spent = (
        ServiceOrder.objects.filter(bike__customer=profile, completed_at__isnull=False)
        .aggregate(
            s=Coalesce(
                Sum("price", output_field=DecimalField(max_digits=12, decimal_places=2)),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
        .get("s")
        or Decimal("0.00")
    )

    total_spent = Decimal(total_spent).quantize(Decimal("0.01"))

    points = int((total_spent / Decimal("2")).to_integral_value(rounding=ROUND_DOWN))
    discount_eur = points // 10
    remainder = points % 10
    points_to_next = 0 if remainder == 0 else 10 - remainder

    return {
        "loyalty_total_spent": total_spent,
        "loyalty_points": points,
        "loyalty_discount_eur": discount_eur,
        "loyalty_points_to_next_eur": points_to_next,
    }


def _get_profile_for_user(user):
    profile = getattr(user, "customer_profile", None)
    if profile is None:
        email = (getattr(user, "email", "") or "").strip().lower()
        if email:
            profile = CustomerProfile.objects.filter(email__iexact=email).first()
            if profile and profile.user_id is None:
                profile.user = user
                profile.save(update_fields=["user"])
    return profile


def invalidate_dashboard_cache() -> None:
    if cache.add("service:dashboard:version", 1, timeout=None):
        return
    try:
        cache.incr("service:dashboard:version")
    except ValueError:
        cache.set("service:dashboard:version", 1, timeout=None)


def get_staff_dashboard_counts(*, today, ttl_seconds: int) -> dict:
    version = cache.get("service:dashboard:version", 1)
    key = f"service:dashboard:stats:v{version}:{today.isoformat()}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    waiting_statuses = [Ticket.Status.OPEN, Ticket.Status.WAITING_ADMIN]
    recent_completed = list(
        ServiceOrder.objects.filter(completed_at__isnull=False)
        .only("created_at", "completed_at")
        .order_by("-completed_at")[:200]
    )
    avg_repair_days = 0.0
    durations = [
        (row.completed_at - row.created_at).total_seconds() / 86400.0
        for row in recent_completed
        if row.completed_at and row.created_at and row.completed_at >= row.created_at
    ]
    if durations:
        avg_repair_days = round(sum(durations) / len(durations), 1)

    data = {
        "waiting_tickets_count": Ticket.objects.filter(status__in=waiting_statuses).count(),
        "stat_orders_new": ServiceOrder.objects.filter(completed_at__isnull=True, status=ServiceOrder.Status.NEW).count(),
        "stat_orders_in_progress": ServiceOrder.objects.filter(
            completed_at__isnull=True,
            status=ServiceOrder.Status.IN_PROGRESS,
        ).count(),
        "stat_orders_done_today": ServiceOrder.objects.filter(completed_at__date=today).count(),
        "unfinished_count": ServiceOrder.objects.exclude(status=ServiceOrder.Status.DONE).count(),
        "open_tickets_count": Ticket.objects.exclude(status=Ticket.Status.CLOSED).count(),
        "completed_last_7_days": ServiceOrder.objects.filter(
            completed_at__isnull=False,
            completed_at__date__gte=today - timedelta(days=6),
        ).count(),
        "avg_repair_days": avg_repair_days,
    }
    cache.set(key, data, timeout=ttl_seconds)
    return data


def get_profile_bikes_with_last_order(profile: CustomerProfile):
    from django.db.models import OuterRef, Subquery

    latest_order_subquery = (
        ServiceOrder.objects.filter(bike_id=OuterRef("pk"))
        .order_by("-created_at")
        .values("pk")[:1]
    )

    bikes = (
        Bike.objects.filter(customer=profile)
        .annotate(last_order_id=Subquery(latest_order_subquery))
        .order_by("brand", "model")
    )
    order_ids = [b.last_order_id for b in bikes if b.last_order_id]
    orders_map = {
        o.id: o
        for o in ServiceOrder.objects.filter(id__in=order_ids)
        .select_related("bike", "bike__customer")
        .only("id", "created_at", "status", "service_code", "bike_id", "promised_date", "completed_at")
    }
    return [{"bike": bike, "last_order": orders_map.get(bike.last_order_id)} for bike in bikes]
