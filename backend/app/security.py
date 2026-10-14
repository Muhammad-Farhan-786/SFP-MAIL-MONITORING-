import secrets, socket, ipaddress
from datetime import timedelta
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from .config import config
from .db import get_db
from .models import User, now

hasher = PasswordHasher()


def encrypt(value):
    return Fernet(config().encryption_key.encode()).encrypt(value.encode()).decode()


def decrypt(value):
    return Fernet(config().encryption_key.encode()).decrypt(value.encode()).decode()


def password_ok(hash_value, value):
    try:
        return hasher.verify(hash_value, value)
    except (VerifyMismatchError, InvalidHashError):
        return False


def current_user(request: Request, db=Depends(get_db)):
    try:
        payload = jwt.decode(
            request.cookies.get("session", ""),
            config().jwt_secret,
            algorithms=["HS256"],
            audience="email-health",
            issuer="email-health",
        )
        user = db.get(User, int(payload["sub"]))
        if not user or not user.active:
            raise ValueError()
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            token = request.headers.get("X-CSRF-Token", "")
            if (
                not token
                or not token.isascii()
                or not secrets.compare_digest(token, payload.get("csrf", ""))
            ):
                raise HTTPException(403, "Invalid CSRF token")
        return user
    except HTTPException:
        raise
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "Please sign in")


def admin(user=Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return user


def create_token(user):
    csrf = secrets.token_urlsafe(32)
    return jwt.encode(
        {
            "sub": str(user.id),
            "csrf": csrf,
            "iat": now(),
            "exp": now() + timedelta(hours=8),
            "aud": "email-health",
            "iss": "email-health",
        },
        config().jwt_secret,
        algorithm="HS256",
    ), csrf


def public_addresses(host):
    addresses = {
        item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    }
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError("Monitoring targets must resolve only to public IP addresses")
    return sorted(addresses)
