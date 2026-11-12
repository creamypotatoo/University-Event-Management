from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.management.validation import text_fields

CAMPUS_TIMEZONE = ZoneInfo("Asia/Dhaka")
EVENT_FIELDS = [("title", "Title", 200), ("description", "Description", 5000)]


def event_input(form):
    display, errors = text_fields(form, EVENT_FIELDS)
    values = dict(display)
    for name in ("venue_id", "capacity"):
        raw = form.get(name, "").strip()
        display[name] = raw
        if not raw.isascii() or not raw.isdigit() or len(raw) > 10 or not 1 <= int(raw) <= 2147483647:
            errors[name] = "Choose a positive whole number within the supported range."
        else:
            values[name] = int(raw)
    for name in ("start_time", "end_time"):
        raw = form.get(name, "").strip()
        display[name] = raw
        try:
            if "T" not in raw or len(raw) > 40:
                raise ValueError
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=CAMPUS_TIMEZONE)
            values[name] = parsed.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            errors[name] = "Enter a valid date and time (campus time: Asia/Dhaka)."
    if not any(name in errors for name in ("start_time", "end_time")) and values["end_time"] <= values["start_time"]:
        errors["end_time"] = "End time must be later than start time."
    return values, display, errors
