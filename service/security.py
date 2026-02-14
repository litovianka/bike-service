from __future__ import annotations

from django.core.cache import cache


def get_client_ip(request) -> str:
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return (request.META.get("REMOTE_ADDR") or "unknown").strip() or "unknown"


def _rate_limit_key(scope: str, ident: str) -> str:
    return f"rl:{scope}:{ident}"


def is_rate_limited(*, scope: str, ident: str, limit: int, window_seconds: int) -> bool:
    key = _rate_limit_key(scope, ident)
    if cache.add(key, 1, timeout=window_seconds):
        return False

    count = cache.incr(key)
    return count > limit


def reset_rate_limit(*, scope: str, ident: str) -> None:
    cache.delete(_rate_limit_key(scope, ident))
