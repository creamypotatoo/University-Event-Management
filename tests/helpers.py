import re

from werkzeug.security import generate_password_hash

PASSWORD = "Test passphrase for 2026!"  # Test-only credentials, never an application default.
TEST_HASH = generate_password_hash(PASSWORD, method="scrypt")


def token(client, path="/auth/login"):
    response = client.get(path)
    match = re.search(rb'name="csrf_token" value="([a-f0-9]{64})"', response.data)
    assert match is not None
    return match.group(1).decode()


def login(client, email, password=PASSWORD, **extra):
    return client.post("/auth/login", data={"csrf_token": token(client), "email": email, "password": password, **extra})
