"""Input rules shared by public registration and the administrator CLI."""

import re

EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+", re.ASCII)
STUDENT_NUMBER = re.compile(r"[A-Za-z0-9][A-Za-z0-9/_-]{2,39}", re.ASCII)


def valid_text(value, maximum):
    return isinstance(value, str) and 1 <= len(value.strip()) <= maximum and all(c.isprintable() for c in value)


def normalize_email(value):
    return value.strip().lower()


def valid_email(value):
    if len(value) > 254 or EMAIL.fullmatch(value) is None:
        return False
    local, domain = value.rsplit("@", 1)
    return (len(local) <= 64 and not local.startswith(".") and not local.endswith(".")
            and ".." not in local and all(len(label) <= 63 for label in domain.split(".")))


def valid_password(value):
    # Long passphrases are supported without arbitrary composition requirements.
    return 12 <= len(value) <= 128 and not value.isspace() and all(c.isprintable() for c in value)


def registration_input(form):
    data = {key: form.get(key, "").strip() for key in ("full_name", "email", "student_number", "department", "batch")}
    data["email"] = normalize_email(data["email"])
    errors = {}
    for name, limit in [("full_name", 150), ("department", 100), ("batch", 30)]:
        if not valid_text(data[name], limit):
            errors[name] = f"Enter 1–{limit} printable characters."
    if not valid_email(data["email"]):
        errors["email"] = "Enter a valid email address (maximum 254 characters)."
    if STUDENT_NUMBER.fullmatch(data["student_number"]) is None:
        errors["student_number"] = "Use 3–40 letters, numbers, hyphens, underscores, or slashes; begin with a letter or number."
    password = form.get("password", "")
    if not valid_password(password):
        errors["password"] = "Use 12–128 printable characters. Spaces are allowed in a passphrase."
    if password != form.get("confirm_password", ""):
        errors["confirm_password"] = "Passwords must match."
    # Passwords and arbitrary supplied role/ID fields are never returned to templates.
    return data, errors
