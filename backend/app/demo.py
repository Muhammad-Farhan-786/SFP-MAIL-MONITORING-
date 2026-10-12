"""Optional database-backed demo data. Never runs during production bootstrap."""

import argparse
from datetime import timedelta
from sqlalchemy import select, func
from .config import config
from .db import Session
from .models import Check, DeliveryEvent, Domain, now
from .services import health_score, WEIGHTS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-demo-data", action="store_true")
    args = parser.parse_args()
    if not config().demo_mode or not args.confirm_demo_data:
        raise SystemExit(
            "Requires DEMO_MODE=true and --confirm-demo-data in a disposable demo environment"
        )
    with Session() as db:
        if db.scalar(
            select(func.count(Check.id)).where(Check.demo.is_(False))
        ) or db.scalar(
            select(func.count(DeliveryEvent.id)).where(DeliveryEvent.demo.is_(False))
        ):
            raise SystemExit(
                "Refusing to mix samples with genuine monitoring data. Use a fresh demo database."
            )
        domain = db.scalar(select(Domain).where(Domain.name == config().domain))
        if not domain:
            raise SystemExit("Run migrations and bootstrap first")
        if db.scalar(select(Check.id).where(Check.demo.is_(True))):
            raise SystemExit("Demo data already exists")
        for day in range(29, -1, -1):
            at = now() - timedelta(days=day)
            factors = {
                name: {
                    "state": "Warning"
                    if day % 7 == 0 and name == "Bounce Rate"
                    else "Healthy"
                }
                for name in WEIGHTS
            }
            for name, data in factors.items():
                db.add(
                    Check(
                        domain_id=domain.id,
                        category=name,
                        state=data["state"],
                        summary="DEMO: illustrative monitoring result, not a real observation.",
                        evidence={"demo": True},
                        checked_at=at,
                        demo=True,
                    )
                )
            score = health_score(factors)
            db.add(
                Check(
                    domain_id=domain.id,
                    category="Health Score",
                    state="Healthy",
                    summary="DEMO: sample score from illustrative signals.",
                    evidence={
                        k: score[k]
                        for k in ("score", "coverage", "penalty", "provisional")
                    },
                    checked_at=at,
                    demo=True,
                )
            )
            for attempt in range(30):
                db.add(
                    DeliveryEvent(
                        event_id=f"demo-{day}-{attempt}",
                        domain_id=domain.id,
                        message_id=f"demo-message-{day}-{attempt}",
                        recipient_domain="example.com",
                        kind="hard_bounce"
                        if attempt == 0 and day % 7 == 0
                        else "delivered",
                        occurred_at=at,
                        spf_pass=True,
                        dkim_pass=True,
                        spf_aligned=True,
                        dkim_aligned=True,
                        demo=True,
                    )
                )
        db.commit()
    print("DEMO-only records created; dashboard must display its demo banner.")


if __name__ == "__main__":
    main()
