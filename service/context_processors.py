# service/context_processors.py

from __future__ import annotations

from django.core.cache import cache

from .models import CustomerProfile, Ticket


def _safe_profile_for_user(user):
    profile = getattr(user, "customer_profile", None)
    if profile is None:
        email = (getattr(user, "email", "") or "").strip().lower()
        if email:
            profile = CustomerProfile.objects.filter(email__iexact=email).first()
    return profile


def ticket_badges(request):
    """
    Jeden context processor pre obe roly.

    admin_ticket_badge_count
      tickety ktoré čakajú na servis

    customer_ticket_badge_count
      tickety ktoré čakajú na zákazníka a patria jeho servisom
    """
    data = {
        "admin_ticket_badge_count": 0,
        "customer_ticket_badge_count": 0,
    }

    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return data

    try:
        if getattr(user, "is_staff", False):
            cache_key = "badge:admin:waiting"
            cached = cache.get(cache_key)
            if cached is None:
                cached = Ticket.objects.filter(status=Ticket.Status.WAITING_ADMIN).count()
                cache.set(cache_key, cached, timeout=30)
            data["admin_ticket_badge_count"] = cached
            return data

        profile = _safe_profile_for_user(user)
        if profile:
            cache_key = f"badge:customer:{profile.id}:waiting"
            cached = cache.get(cache_key)
            if cached is None:
                cached = Ticket.objects.filter(
                    order__bike__customer=profile,
                    status=Ticket.Status.WAITING_CUSTOMER,
                ).count()
                cache.set(cache_key, cached, timeout=30)
            data["customer_ticket_badge_count"] = cached

        return data
    except Exception:
        return data


def admin_ticket_badge(request):
    """
    Alias kvôli tomu, že máš v settings.py pravdepodobne uvedené
    service.context_processors.admin_ticket_badge

    Vráti rovnaké premenné ako ticket_badges, takže nič ďalšie netreba meniť.
    """
    return ticket_badges(request)
