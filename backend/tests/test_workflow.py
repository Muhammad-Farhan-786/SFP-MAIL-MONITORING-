from datetime import timedelta
from sqlalchemy import select, func
import pytest
from app.models import *
from app.services import *
from app.security import encrypt, decrypt


def test_unknown_not_healthy():
    assert health_score({})["score"] is None and health_score({})["coverage"] == 0


def test_score():
    score = health_score(
        {"SPF": {"state": "Healthy"}, "DKIM": {"state": "Critical"}}, 1
    )
    assert score["score"] == 45 and score["penalty"] == 5 and score["provisional"]


def failure(db, category="SPF"):
    record(db, 1, category, {"state": "Critical", "summary": "Missing", "evidence": {}})
    db.commit()
    return db.scalar(select(Issue))


def test_dedup_and_alert_cooldown(db):
    failure(db)
    failure(db)
    assert (
        db.scalar(select(func.count(Issue.id))) == 1
        and db.scalar(select(func.count(Alert.id))) == 1
        and db.scalar(select(func.count(Check.id))) == 2
    )


def test_cannot_close_open(db):
    with pytest.raises(ValueError):
        transition(db, failure(db), "Closed", "admin")


def test_verified_retest_required(db):
    issue = failure(db)
    for status in ("Fixing", "Ready for Retest", "Retesting"):
        transition(db, issue, status, "admin")
    check = record(
        db, 1, "SPF", {"state": "Healthy", "summary": "Fixed", "evidence": {}}
    )
    assert verify_retest(db, issue, check, "admin")
    transition(db, issue, "Closed", "admin")
    db.commit()
    assert issue.verified_by == "admin" and issue.closed_at and issue.status == "Closed"


def test_failed_retest(db):
    issue = failure(db)
    for status in ("Fixing", "Ready for Retest", "Retesting"):
        transition(db, issue, status, "admin")
    assert not verify_retest(db, issue, None, "admin") and issue.status == "Fixing"


def test_recurrence(db):
    issue = failure(db)
    issue.status = "Closed"
    issue.verified_at = now()
    db.commit()
    failure(db)
    assert issue.status == "Open" and issue.verified_at is None


def test_stale_not_scored(db):
    db.add(
        Check(
            domain_id=1,
            category="SPF",
            state="Healthy",
            summary="old",
            evidence={},
            checked_at=now() - timedelta(days=5),
        )
    )
    db.commit()
    value = snapshot(db, 1)
    assert value["score"] is None and value["cards"][0]["state"] == "Unknown"


def test_encryption():
    value = encrypt("test-secret")
    assert "test-secret" not in value and decrypt(value) == "test-secret"


def test_owner_required_for_assignment(db):
    with pytest.raises(ValueError):
        transition(db, failure(db), "Assigned", "admin")


def test_email_outbox_delivery(db, monkeypatch):
    from app.worker import deliver_alerts
    import app.worker as worker

    issue = failure(db)
    from contextlib import nullcontext

    monkeypatch.setattr(worker, "Session", lambda: nullcontext(db))
    monkeypatch.setattr(worker.mail, "send", lambda *args: True)
    deliver_alerts.run()
    alert = db.scalar(select(Alert))
    assert alert.state == "Sent" and alert.sent_at


def test_demo_seeder_database_backed_and_guarded(db, monkeypatch):
    from contextlib import nullcontext
    from app.config import config
    import app.demo as demo
    import sys

    monkeypatch.setattr(config(), "demo_mode", True)
    monkeypatch.setattr(demo, "Session", lambda: nullcontext(db))
    monkeypatch.setattr(sys, "argv", ["demo", "--confirm-demo-data"])
    demo.main()
    assert (
        db.scalar(
            select(func.count(DeliveryEvent.id)).where(DeliveryEvent.demo.is_(True))
        )
        == 900
    )
    value = snapshot(db, 1, 30)
    assert value["score"] is not None and value["delivery"]["total"] == 900
    with pytest.raises(SystemExit):
        demo.main()
