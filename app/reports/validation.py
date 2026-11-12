"""Exact money validation for the existing NUMERIC(12, 2) expense column."""

from datetime import date
from decimal import Decimal
import re

from app.management.validation import text_fields

EXPENSE_FIELDS = [("description", "Description", 255)]
AMOUNT = re.compile(r"[0-9]{1,10}(?:\.[0-9]{1,2})?", re.ASCII)


def expense_input(form):
    values, errors = text_fields(form, EXPENSE_FIELDS)
    display = dict(values)
    raw = form.get("amount", "").strip()
    display["amount"] = raw
    if len(raw) > 13 or AMOUNT.fullmatch(raw) is None:
        errors["amount"] = "Enter an amount from 0.00 to 9999999999.99 with at most two decimal places."
    else:
        values["amount"] = Decimal(raw).quantize(Decimal("0.01"))
    display["expense_date"] = form.get("expense_date", "").strip()
    try:
        values["expense_date"] = date.fromisoformat(display["expense_date"])
        if values["expense_date"].isoformat() != display["expense_date"]:
            raise ValueError
    except ValueError:
        errors["expense_date"] = "Enter a valid expense date."
    return values, display, errors
