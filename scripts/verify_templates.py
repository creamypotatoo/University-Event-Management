"""Compile every Jinja template and check source POST forms for CSRF fields.

This is a static audit, not JavaScript execution or visual/browser testing.
"""

from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app

app = create_app()
names = app.jinja_env.list_templates()
forms = 0
for name in names:
    app.jinja_env.get_template(name)
    source = app.jinja_env.loader.get_source(app.jinja_env, name)[0]
    for match in re.finditer(r"<form\b([^>]*)>(.*?)</form>", source, re.IGNORECASE | re.DOTALL):
        if re.search(r"method\s*=\s*['\"]post['\"]", match[1], re.IGNORECASE):
            forms += 1
            assert re.search(r"name\s*=\s*['\"]csrf_token['\"]", match[2]), f"POST form missing CSRF field: {name}"
print(f"PASS: {len(names)} Jinja templates compiled; {forms} source POST forms contain CSRF fields.")
print("This does not verify browser layout, JavaScript behavior, or assistive-technology compatibility.")
