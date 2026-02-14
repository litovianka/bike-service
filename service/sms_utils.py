# service/sms_utils.py

from __future__ import annotations

from django.conf import settings


def send_sms_safely(*, phone: str, text: str) -> bool:
    phone = (phone or "").strip()
    text = (text or "").strip()

    if not phone or not text:
        return False

    provider = getattr(settings, "SMS_PROVIDER", "console")

    try:
        if provider == "console":
            print(f"SMS to {phone}: {text}")
            return True
        print(f"SMS provider {provider} not configured, fallback console. To {phone}: {text}")
        return True
    except Exception:
        return False