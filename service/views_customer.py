from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .models import Bike, ServiceOrder
from .view_common import _get_profile_for_user, _gravatar_url, _loyalty_stats_for_profile, get_profile_bikes_with_last_order


@login_required
def customer_home(request):
    if request.user.is_staff:
        return redirect("service_panel")

    profile = _get_profile_for_user(request.user)

    bikes_data = []
    if profile is not None:
        bikes_data = get_profile_bikes_with_last_order(profile)

    return render(
        request,
        "moje_biky_dashboard.html",
        {"profile": profile, "bikes_data": bikes_data},
    )


@login_required
def bike_detail(request, bike_id):
    if request.user.is_staff:
        return redirect("service_panel")

    profile = _get_profile_for_user(request.user)

    bike = get_object_or_404(Bike.objects.select_related("customer"), pk=bike_id)
    if profile is None or bike.customer_id != profile.id:
        return redirect("customer_home")

    orders = ServiceOrder.objects.filter(bike=bike).order_by("-created_at")
    return render(request, "bike_detail.html", {"bike": bike, "orders": orders})


@login_required
def customer_profile_view(request):
    if request.user.is_staff:
        return redirect("service_panel")

    profile = _get_profile_for_user(request.user)

    if profile is None:
        return redirect("customer_home")

    if request.method == "POST":
        full_name = (request.POST.get("full_name", "") or "").strip()
        phone_number = (request.POST.get("phone_number", "") or "").strip()

        profile.full_name = full_name
        profile.phone_number = phone_number
        profile.save(update_fields=["full_name", "phone_number"])

        messages.success(request, "Profil bol uložený.")
        return redirect("customer_profile")

    avatar_url = _gravatar_url(profile.email or "")
    loyalty = _loyalty_stats_for_profile(profile)

    return render(
        request,
        "customer_profile.html",
        {
            "profile": profile,
            "avatar_url": avatar_url,
            "loyalty": loyalty,
        },
    )


@login_required
def loyalty_landing(request):
    if request.user.is_staff:
        return redirect("service_panel")

    profile = _get_profile_for_user(request.user)
    if profile is None:
        return redirect("customer_home")

    loyalty = _loyalty_stats_for_profile(profile)

    return render(
        request,
        "loyalty_landing.html",
        {
            "profile": profile,
            "loyalty": loyalty,
        },
    )
