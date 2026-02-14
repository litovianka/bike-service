from __future__ import annotations

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone


def health_check(request):
    db_ok = True
    cache_ok = True

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        db_ok = False

    try:
        cache_key = "health:ping"
        cache.set(cache_key, "ok", timeout=10)
        cache_ok = cache.get(cache_key) == "ok"
    except Exception:
        cache_ok = False

    status_code = 200 if db_ok and cache_ok else 503
    return JsonResponse(
        {
            "status": "ok" if status_code == 200 else "degraded",
            "db": "ok" if db_ok else "error",
            "cache": "ok" if cache_ok else "error",
            "timestamp": timezone.now().isoformat(),
        },
        status=status_code,
    )
