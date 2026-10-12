"""Change an existing administrator password without echoing or logging it."""

import getpass
from sqlalchemy import select
from app.db import Session
from app.models import User
from app.security import hasher
from app.services import audit

email = input("Administrator email: ").strip().lower()
password = getpass.getpass("New password (12+ characters): ")
if len(password) < 12 or password != getpass.getpass("Confirm password: "):
    raise SystemExit("Password requirements or confirmation failed")
with Session() as db:
    user = db.scalar(select(User).where(User.email == email, User.role == "admin"))
    if not user:
        raise SystemExit("Administrator not found")
    user.password_hash = hasher.hash(password)
    audit(db, "operator", "Administrator password reset", user_id=user.id)
    db.commit()
print("Password changed. Existing sessions expire within eight hours.")
