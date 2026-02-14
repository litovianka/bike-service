# service/decorators.py

from __future__ import annotations

from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect


def staff_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if not request.user.is_staff:
            messages.error(request, "Nemáš prístup do servisného panelu.")
            return redirect("customer_home")
        return view_func(request, *args, **kwargs)

    return _wrapped


def customer_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if request.user.is_staff:
            return redirect("service_panel")
        return view_func(request, *args, **kwargs)

    return _wrapped