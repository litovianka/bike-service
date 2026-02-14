from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode

from .security import get_client_ip, is_rate_limited, reset_rate_limit
def home_redirect(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect("service_panel")
        return redirect("customer_home")
    return redirect("login")


def login_view(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect("service_panel")
        return redirect("customer_home")

    error = None

    if request.method == "POST":
        ip = get_client_ip(request)
        if is_rate_limited(scope="login", ident=ip, limit=8, window_seconds=300):
            error = "Príliš veľa pokusov. Skús znova o pár minút."
            return render(request, "login.html", {"error": error}, status=429)

        username = (request.POST.get("username", "") or "").strip()
        password = (request.POST.get("password", "") or "").strip()

        user = authenticate(request, username=username, password=password)
        # Allow login via email as well (useful for staff users with non-email usernames).
        if user is None and "@" in username:
            email_match = User.objects.filter(email__iexact=username).only("username").first()
            if email_match:
                user = authenticate(request, username=email_match.username, password=password)
        if user is not None:
            reset_rate_limit(scope="login", ident=ip)
            login(request, user)
            if user.is_staff:
                return redirect("service_panel")
            return redirect("customer_home")
        error = "Nesprávny e mail alebo heslo."

    return render(request, "login.html", {"error": error})


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def customer_change_password(request):
    if request.user.is_staff:
        return redirect("service_panel")

    if request.method == "POST":
        current_password = (request.POST.get("current_password", "") or "").strip()
        new_password = (request.POST.get("new_password", "") or "").strip()
        new_password2 = (request.POST.get("new_password2", "") or "").strip()

        if not request.user.check_password(current_password):
            messages.error(request, "Aktuálne heslo nesedí.")
            return redirect("customer_change_password")

        if new_password != new_password2:
            messages.error(request, "Nové heslá sa nezhodujú.")
            return redirect("customer_change_password")
        try:
            validate_password(new_password, user=request.user)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return redirect("customer_change_password")

        request.user.set_password(new_password)
        request.user.save()
        update_session_auth_hash(request, request.user)
        messages.success(request, "Heslo bolo zmenené.")
        return redirect("customer_home")

    return render(request, "customer_change_password.html")


def customer_set_password(request, uidb64: str, token: str):
    ip = get_client_ip(request)
    if request.method == "POST" and is_rate_limited(scope="set_password", ident=ip, limit=6, window_seconds=300):
        return render(
            request,
            "customer_set_password.html",
            status=429,
        )

    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=user_id)
    except Exception:
        return HttpResponseBadRequest("Neplatný odkaz.")

    if not default_token_generator.check_token(user, token):
        return HttpResponseBadRequest("Link na nastavenie hesla je neplatný alebo expiroval.")

    if request.method == "POST":
        new_password = (request.POST.get("new_password", "") or "").strip()
        new_password2 = (request.POST.get("new_password2", "") or "").strip()

        if new_password != new_password2:
            messages.error(request, "Nové heslá sa nezhodujú.")
            return redirect("customer_set_password", uidb64=uidb64, token=token)
        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return redirect("customer_set_password", uidb64=uidb64, token=token)

        user.set_password(new_password)
        user.save(update_fields=["password"])
        reset_rate_limit(scope="set_password", ident=ip)
        messages.success(request, "Heslo bolo nastavené. Teraz sa môžeš prihlásiť.")
        return redirect("login")

    return render(request, "customer_set_password.html")
