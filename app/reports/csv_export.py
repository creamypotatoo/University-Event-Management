"""UTF-8 CSV with spreadsheet-formula neutralization on text cells."""

import csv
from decimal import Decimal
from io import StringIO

from flask import Response


def safe_cell(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    if not isinstance(value, str):
        return str(value)
    # Formula controls may follow whitespace; also neutralize leading tab/newlines.
    stripped = value
    while stripped and (stripped[0].isspace() or stripped[0] == "\ufeff"):
        stripped = stripped[1:]
    if value.startswith(("\t", "\r", "\n")) or stripped.startswith(("=", "+", "-", "@", "＝", "＋", "－", "＠")):
        return "'" + value
    return value


def csv_response(filename, headers, rows):
    output = StringIO(newline="")
    writer = csv.writer(output, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([safe_cell(value) for value in row])
    response = Response(output.getvalue().encode("utf-8"), content_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Cache-Control"] = "no-store"
    return response
