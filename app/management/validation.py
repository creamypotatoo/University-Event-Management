"""Whitelisted management inputs matching existing database limits."""

from app.auth.validation import valid_text


def text_fields(form, fields):
    values = {name: form.get(name, "").strip() for name, label, maximum in fields}
    errors = {}
    for name, label, maximum in fields:
        valid = valid_text(values[name], maximum)
        if name == "description":
            valid = 1 <= len(values[name]) <= maximum and all(c.isprintable() or c in "\n\r\t" for c in values[name])
        if not valid:
            errors[name] = f"{label} must contain 1–{maximum} printable characters."
    return values, errors


PROFILE_FIELDS = [("full_name", "Full name", 150), ("department", "Department", 100), ("batch", "Batch", 30)]
CLUB_FIELDS = [("club_name", "Club name", 150), ("description", "Description", 5000)]
VENUE_FIELDS = [("venue_name", "Venue name", 150), ("location", "Location", 255), ("capacity", "Capacity", 10)]


def venue_input(form):
    values, errors = text_fields(form, VENUE_FIELDS)
    raw = values["capacity"]
    if not raw.isascii() or not raw.isdigit() or len(raw) > 10 or not 1 <= int(raw) <= 2147483647:
        errors["capacity"] = "Capacity must be a whole number between 1 and 2147483647."
    return values, errors
