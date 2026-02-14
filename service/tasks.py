from __future__ import annotations

import base64
import logging

from django.conf import settings
from django.core.mail import EmailMessage, send_mail

from .sms_utils import send_sms_safely

logger = logging.getLogger("service.tasks")

try:
    from celery import shared_task
except Exception:  # pragma: no cover
    def shared_task(*dargs, **dkwargs):
        def decorator(func):
            bind = bool(dkwargs.get("bind", False))

            def _delay(*args, **kwargs):
                if bind:
                    return func(None, *args, **kwargs)
                return func(*args, **kwargs)

            func.delay = _delay
            return func

        if dargs and callable(dargs[0]) and len(dargs) == 1 and not dkwargs:
            return decorator(dargs[0])
        return decorator


@shared_task(bind=True, ignore_result=True)
def send_plain_email_task(self, subject: str, body: str, to_list: list[str]) -> bool:
    if not to_list:
        return False
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "servis@mojbike.sk"),
            recipient_list=to_list,
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Failed to send plain email")
        return False


@shared_task(bind=True, ignore_result=True)
def send_email_with_attachment_task(
    self,
    *,
    subject: str,
    body: str,
    to_list: list[str],
    filename: str,
    pdf_base64: str,
) -> bool:
    if not to_list or not pdf_base64:
        return False
    try:
        pdf_bytes = base64.b64decode(pdf_base64.encode("ascii"))
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "servis@mojbike.sk"),
            to=to_list,
        )
        msg.attach(filename, pdf_bytes, "application/pdf")
        msg.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Failed to send email with attachment")
        return False


@shared_task(bind=True, ignore_result=True)
def send_sms_task(self, *, phone: str, text: str) -> bool:
    try:
        return bool(send_sms_safely(phone=phone, text=text))
    except Exception:
        logger.exception("Failed to send SMS")
        return False
