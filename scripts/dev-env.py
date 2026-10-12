"""Generate ignored local-only development secrets once; never prints values."""

from pathlib import Path
import secrets
from cryptography.fernet import Fernet

path = Path(__file__).resolve().parents[1] / ".env"
if path.exists():
    print("Existing .env preserved")
else:
    password = secrets.token_hex(24)
    text = (path.parent / ".env.example").read_text()
    text = text.replace(
        "POSTGRES_PASSWORD=", "POSTGRES_PASSWORD=" + password, 1
    ).replace("REPLACE_URL_ENCODED_PASSWORD", password)
    text = text.replace(
        "JWT_SECRET=", "JWT_SECRET=" + secrets.token_hex(32), 1
    ).replace("ENCRYPTION_KEY=", "ENCRYPTION_KEY=" + Fernet.generate_key().decode(), 1)
    text = (
        text.replace(
            "ADMIN_PASSWORD=", "ADMIN_PASSWORD=" + secrets.token_urlsafe(24), 1
        )
        .replace("COOKIE_SECURE=true", "COOKIE_SECURE=false")
        .replace("HTTP_PORT=80", "HTTP_PORT=8088")
    )
    path.write_text(text)
    path.chmod(0o600)
    print(
        "Local development .env generated. Set your administrator password securely before using the UI. Enable HTTPS and secure cookies before production."
    )
