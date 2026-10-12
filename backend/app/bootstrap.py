"""Idempotent first-admin bootstrap; never overwrites an existing password."""

from sqlalchemy import select
from .config import config
from .db import Session
from .models import User, Domain
from .security import hasher


def main():
    cfg = config()
    with Session() as db:
        if not db.scalar(select(User.id)):
            if len(cfg.admin_password) < 12:
                raise ValueError(
                    "ADMIN_PASSWORD must contain at least 12 characters for first startup"
                )
            db.add(
                User(
                    email=cfg.admin_email.lower(),
                    password_hash=hasher.hash(cfg.admin_password),
                    role="admin",
                )
            )
        if not db.scalar(select(Domain).where(Domain.name == cfg.domain)):
            db.add(Domain(name=cfg.domain, selectors=[]))
        db.commit()


if __name__ == "__main__":
    main()
