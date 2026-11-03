"""Privacy-minimal RFC 5545 calendar export for fictional CircleSplit event agendas.

Times are deliberately FLOATING wall-clock values (no TZID or UTC marker).
No participants, tokens, payments, prices, consent, or organizer notes appear.
"""
from datetime import date, datetime, timezone
import hashlib
import re

_HHMM = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]\Z")


def _clean(value):
    """Preserve human text while removing raw control chars and NULs."""
    value = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return "".join(char for char in value if char == "\n" or ord(char) >= 32 and ord(char) != 127)


def escape_ics(value):
    text = _clean(value)
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line):
    """Fold at <= 75 UTF-8 octets (continuation line includes leading space)."""
    pieces = []
    current = ""
    current_bytes = 0
    for char in line:
        size = len(char.encode("utf-8"))
        if current_bytes + size > 75:
            pieces.append(current)
            current = " "
            current_bytes = 1
        current += char
        current_bytes += size
    pieces.append(current)
    return "\r\n".join(pieces)


def build_ics(event_id, name, event_date, agenda, revision, *, stamp=None):
    """Create portable .ics: same-day agenda entries, no automatic timezone inference."""
    if not isinstance(event_id, int) or event_id < 1:
        raise ValueError("Invalid event identifier")
    try:
        calendar_date = date.fromisoformat(event_date)
    except (ValueError, TypeError):
        raise ValueError("Invalid event date") from None
    if calendar_date.isoformat() != event_date:
        raise ValueError("Event date must use ISO YYYY-MM-DD")
    if not isinstance(revision, int) or revision < 0:
        raise ValueError("Invalid agenda revision")
    items = list(agenda)
    if not items:
        raise ValueError("Event has no scheduled activities")
    if len(items) > 20:
        raise ValueError("Agenda exceeds the 20-slot limit")
    now = stamp or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Calendar stamp must contain a timezone")
    dtstamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    day = calendar_date.strftime("%Y%m%d")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CircleSplit AI//Private Event Agenda//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:" + escape_ics(name),
    ]
    previous_end = ""
    for item in sorted(items, key=lambda item: (item["start_time"], item.get("id", 0))):
        start = item["start_time"]
        end = item["end_time"]
        if not _HHMM.fullmatch(start) or not _HHMM.fullmatch(end) or start >= end:
            raise ValueError("Invalid same-day agenda slot")
        if previous_end and start < previous_end:
            raise ValueError("Overlapping agenda entries")
        previous_end = end
        slot_id = item["id"]
        if not isinstance(slot_id, int) or slot_id < 1:
            raise ValueError("Invalid agenda slot identifier")
        opaque_uid = hashlib.sha256(f"{event_id}:{slot_id}".encode("ascii")).hexdigest()[:32]
        details = _clean(item.get("note", ""))
        guidance = ("Floating local event time (not timezone-converted). "
                    "Confirm location/timezone with the organizer. "
                    "Calendar plan only; not a booking or payment.")
        description = guidance + (("\n" + details) if details else "")
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{opaque_uid}@calendar.circlesplit.invalid",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{day}T{start.replace(':', '')}00",
            f"DTEND:{day}T{end.replace(':', '')}00",
            f"SEQUENCE:{revision}",
            "SUMMARY:" + escape_ics(f"{name} — {item['title']}"),
            "DESCRIPTION:" + escape_ics(description),
            "STATUS:TENTATIVE",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
