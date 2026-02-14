# service/pdf_utils.py

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Iterable, Tuple

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def _wrap_text(text: str, max_chars: int) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    words = text.split()
    lines = []
    current = ""
    for w in words:
        if not current:
            current = w
            continue
        if len(current) + 1 + len(w) <= max_chars:
            current = f"{current} {w}"
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def build_service_protocol_pdf(
    *,
    order_code: str,
    customer_name: str,
    customer_email: str,
    customer_phone: str,
    bike_name: str,
    serial_number: str,
    status_label: str,
    created_at_str: str,
    promised_date_str: str,
    completed_at_str: str,
    price_str: str,
    issue_description: str,
    work_done: str,
    checklist_items: Iterable[Tuple[str, bool]],
) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 48

    # Header logo (falls back silently if image is not available).
    logo_path = Path(__file__).resolve().parent / "static" / "service" / "blackbike-logo.jpeg"
    if logo_path.exists():
        try:
            logo = ImageReader(str(logo_path))
            c.drawImage(logo, 48, y - 10, width=140, height=30, mask="auto", preserveAspectRatio=True, anchor="sw")
        except Exception:
            pass

    c.setFont("Helvetica-Bold", 18)
    c.drawRightString(width - 48, y, "Servisný protokol")
    y -= 26

    c.setFont("Helvetica", 11)
    c.drawString(48, y, f"Servis: #{order_code}")
    y -= 16
    c.drawString(48, y, f"Zákazník: {customer_name}")
    y -= 14
    c.drawString(48, y, f"Email: {customer_email}")
    y -= 14
    if customer_phone:
        c.drawString(48, y, f"Telefón: {customer_phone}")
        y -= 14
    c.drawString(48, y, f"Bicykel: {bike_name}")
    y -= 14
    c.drawString(48, y, f"Sériové číslo: {serial_number or 'nezadané'}")
    y -= 18

    c.setFont("Helvetica-Bold", 11)
    c.drawString(48, y, "Stav a termíny")
    y -= 14

    c.setFont("Helvetica", 11)
    c.drawString(48, y, f"Stav: {status_label}")
    y -= 14
    c.drawString(48, y, f"Vytvorené: {created_at_str}")
    y -= 14
    c.drawString(48, y, f"Sľúbený termín: {promised_date_str or 'nezadané'}")
    y -= 14
    c.drawString(48, y, f"Dokončené: {completed_at_str or 'nedokončené'}")
    y -= 14
    c.drawString(48, y, f"Cena: {price_str}")
    y -= 18

    c.setFont("Helvetica-Bold", 11)
    c.drawString(48, y, "Nahlásená vada")
    y -= 14
    c.setFont("Helvetica", 11)
    for line in _wrap_text(issue_description, 95)[:8]:
        c.drawString(48, y, line)
        y -= 13
    if not issue_description.strip():
        c.drawString(48, y, "nezadané")
        y -= 13
    y -= 10

    c.setFont("Helvetica-Bold", 11)
    c.drawString(48, y, "Čo sa urobilo")
    y -= 14
    c.setFont("Helvetica", 11)
    for line in _wrap_text(work_done, 95)[:10]:
        c.drawString(48, y, line)
        y -= 13
    if not work_done.strip():
        c.drawString(48, y, "nezadané")
        y -= 13
    y -= 10

    c.setFont("Helvetica-Bold", 11)
    c.drawString(48, y, "Checklist")
    y -= 14
    c.setFont("Helvetica", 11)
    for label, done in checklist_items:
        mark = "OK" if done else "neoznačené"
        c.drawString(48, y, f"{label}: {mark}")
        y -= 13
        if y < 90:
            c.showPage()
            y = height - 48
            c.setFont("Helvetica", 11)

    y -= 18
    if y < 120:
        c.showPage()
        y = height - 48

    c.setFont("Helvetica", 11)
    c.drawString(48, y, "Ďakujeme, že ste navštívili náš servis BlackBike.")
    y -= 16
    c.drawString(48, y, "Tešíme sa na vašu ďalšiu návštevu.")

    c.showPage()
    c.save()
    return buffer.getvalue()
