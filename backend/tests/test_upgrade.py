from datetime import timedelta
from unittest.mock import patch, MagicMock
from sqlalchemy import select, func
import pytest
from app.models import *
from app.services import record, snapshot, preferences, health_score, aware, WEIGHTS
from app import alerts, scheduling, mail
from app.config import config
from app.schemas import SeedInput
from app.security import encrypt, decrypt


@pytest.fixture
def clock(monkeypatch):
    time = {"now": now()}
    for module in (alerts, scheduling):
        monkeypatch.setattr(module, "now", lambda: time["now"])
    return time


def fail(db, category="SPF", state="Critical"):
    record(
        db,
        1,
        category,
        {
            "state": state,
            "summary": "Observed SPF problem",
            "evidence": {"records": ["v=spf1 +all"]},
        },
    )
    db.commit()
    return db.scalar(select(Issue).where(Issue.category == category))


def test_five_minute_defaults_and_provider_quota_intervals(db):
    p = preferences(db)["intervals"]
    assert p["auth"] == p["smtp"] == p["delivery"] == 300
    assert p["reputation"] == p["blacklist"] == 43200 and p["placement"] == 86400


def test_schedule_reservation_overlap_redelivery_and_expiry(db, clock):
    job = scheduling.reserve(db, 1, "auth")
    db.commit()
    token = job.task_id
    assert aware(job.next_due_at) == clock["now"] + timedelta(seconds=300)
    assert scheduling.reserve(db, 1, "auth", manual=True) is None
    job = scheduling.start(db, 1, "auth", token)
    assert job.state == "Running"
    assert scheduling.start(db, 1, "auth", token) is None
    scheduling.finish(db, job)
    assert job.last_success_at and job.duration_seconds is not None
    assert scheduling.reserve(db, 1, "auth") is None
    clock["now"] += timedelta(seconds=300)
    nextjob = scheduling.reserve(db, 1, "auth")
    assert nextjob.task_id != token
    db.commit()
    clock["now"] += timedelta(seconds=601)
    expired = scheduling.reserve(db, 1, "auth")
    assert expired and expired.error


def test_failed_publish_retains_same_durable_token(db):
    job = scheduling.reserve(db, 1, "auth")
    db.commit()
    token = job.task_id
    task = MagicMock()
    task.apply_async.side_effect = ConnectionError()
    scheduling.publish(db, job, task)
    assert job.state == "Pending" and job.task_id == token
    task.apply_async.side_effect = None
    scheduling.publish(db, job, task)
    assert (
        job.state == "Queued" and task.apply_async.call_args.kwargs["task_id"] == token
    )


def test_observation_error_is_degraded_not_success(db):
    job = scheduling.reserve(db, 1, "smtp")
    db.commit()
    job = scheduling.start(db, 1, "smtp", job.task_id)
    scheduling.finish(db, job, "Degraded", "TimeoutError")
    assert job.last_success_at is None and job.finished_at
    assert snapshot(db, 1)["scans"][1]["state"] == "Degraded"


def test_diagnosis_is_specific_and_does_not_guess_dns(db):
    issue = fail(db)
    assert "Authoritative DNS" in issue.diagnosis["required_access"]
    assert (
        "lookup" in issue.action and issue.diagnosis["automatic_remediation"] is False
    )
    assert "YOUR_PROVIDER" not in issue.action
    body = db.scalar(select(Alert)).payload["body"]
    assert (
        "v=spf1 +all" in body
        and "Monitoring Coverage" in body
        and "Required access" in body
    )


def test_grouped_digest_and_five_minute_reminders(db, clock, monkeypatch):
    fail(db)
    fail(db, "DMARC")
    assert db.scalar(select(func.count(Alert.id))) == 1
    sent = []
    monkeypatch.setattr(mail, "send", lambda *args: sent.append(args) or True)
    alerts.send_outbox(db)
    assert len(sent) == 1 and "DMARC" in sent[0][1]
    clock["now"] += timedelta(seconds=299)
    assert alerts.enqueue_digest(db, 1) is None
    clock["now"] += timedelta(seconds=1)
    alerts.enqueue_digest(db, 1)
    db.commit()
    alerts.enqueue_digest(db, 1)
    db.commit()
    alerts.send_outbox(db)
    assert len(sent) == 2 and db.scalar(select(func.count(Alert.id))) == 2


def test_paused_disabled_queue_history_and_resume(db, clock, monkeypatch):
    fail(db)
    row = alerts.settings_row(db, 1)
    row.value = {**row.value, "paused": True}
    alerts.suppress_queued(db, 1, row.value)
    db.commit()
    sent = []
    monkeypatch.setattr(mail, "send", lambda *a: sent.append(a) or True)
    alerts.send_outbox(db)
    assert not sent and db.scalar(select(Alert)).state == "Suppressed"
    assert "paused" in db.scalar(select(Alert)).suppression_reason
    row.value = {**row.value, "paused": False, "revision": 1}
    db.commit()
    alerts.enqueue_digest(db, 1)
    db.commit()
    alerts.send_outbox(db)
    assert len(sent) == 1
    clock["now"] += timedelta(seconds=301)
    alerts.enqueue_digest(db, 1)
    db.commit()
    row.value = {**row.value, "enabled": False, "revision": 2}
    db.commit()
    alerts.send_outbox(db)
    assert len(sent) == 1
    assert db.scalars(select(Alert).where(Alert.state == "Suppressed")).all()
    record(
        db,
        1,
        "SPF",
        {
            "state": "Warning",
            "summary": "Still checked with alerts disabled",
            "evidence": {},
        },
    )
    db.commit()
    assert db.scalar(select(func.count(Check.id))) >= 2


def test_recovery_grouped_and_manual_closure_remains_required(db, monkeypatch):
    a = fail(db)
    b = fail(db, "DMARC")
    for cat in ("SPF", "DMARC"):
        record(
            db,
            1,
            cat,
            {"state": "Healthy", "summary": "Observed healthy", "evidence": {}},
        )
    db.commit()
    recoveries = db.scalars(select(Alert).where(Alert.kind == "Recovery")).all()
    assert len(recoveries) == 1 and len(recoveries[0].payload["observations"]) == 2
    assert (
        a.observed_state == "Healthy" and a.status == "Open" and a.verified_at is None
    )
    messages = []
    monkeypatch.setattr(mail, "send", lambda *x: messages.append(x) or True)
    alerts.send_outbox(db)
    assert any("RECOVERY" in m[0] for m in messages)
    record(
        db, 1, "SPF", {"state": "Healthy", "summary": "Still healthy", "evidence": {}}
    )
    db.commit()
    assert db.scalar(select(func.count(Alert.id)).where(Alert.kind == "Recovery")) == 1


def test_no_problem_reminders_after_complete_verified_recovery(db, monkeypatch):
    fail(db)
    for category in WEIGHTS:
        record(
            db,
            1,
            category,
            {"state": "Healthy", "summary": "Verified check", "evidence": {}},
        )
    db.commit()
    assert snapshot(db, 1)["score"] == 100
    assert alerts.enqueue_digest(db, 1) is None
    monkeypatch.setattr(mail, "send", lambda *x: True)
    alerts.send_outbox(db)
    diagnostic = db.scalar(select(Alert).where(Alert.kind == "Diagnostic"))
    assert diagnostic.state == "Suppressed"


def test_retry_backoff_and_failure_circuit(db, clock, monkeypatch):
    fail(db)

    def broken(*args):
        raise TimeoutError("Never disclose this sensitive detail")

    monkeypatch.setattr(mail, "send", broken)
    alerts.send_outbox(db)
    alert = db.scalar(select(Alert))
    assert alert.attempts == 1 and alert.error == "TimeoutError"
    alerts.send_outbox(db)
    assert alert.attempts == 1
    for i in range(4):
        clock["now"] = aware(alert.next_attempt_at) + timedelta(seconds=1)
        alerts.send_outbox(db)
    assert alert.state == "Failed" and alert.attempts == 5
    assert alerts.enqueue_digest(db, 1) is None
    assert "sensitive" not in (alert.error or "")


def test_critical_only_and_settings_survive_new_session(db):
    row = alerts.settings_row(db, 1)
    row.value = {**row.value, "critical_only": True}
    db.commit()
    fail(db, state="Warning")
    assert db.scalar(select(func.count(Alert.id))) == 0
    fail(db, state="Critical")
    assert db.scalar(select(func.count(Alert.id))) == 1
    db.expire_all()
    assert alerts.alert_preferences(db, 1)["critical_only"]


def test_missing_delivery_and_placement_are_not_zero_success(db, signed):
    data = signed.get("/api/overview/1").json()
    assert data["delivery"]["measurement_state"] == "Not Measured"
    assert (
        data["delivery"]["delivered"] is None
        and data["delivery"]["delivery_rate"] is None
    )
    fail(db)
    point = signed.get("/api/history/1").json()["series"][0]
    assert (
        point["inbox"] is None and point["spam"] is None and point["failures"] is None
    )


def test_score_reduction_and_stale_coverage(db):
    data = health_score({"SPF": {"state": "Warning"}, "DKIM": {"state": "Healthy"}})
    assert data["score"] == 75 and data["factors"][0]["reduction"] == 25
    db.add(
        Check(
            domain_id=1,
            category="SPF",
            state="Healthy",
            summary="Old",
            evidence={},
            checked_at=now() - timedelta(seconds=601),
        )
    )
    db.commit()
    card = snapshot(db, 1)["cards"][0]
    assert card["availability"] == "Stale" and card["state"] == "Unknown"


def test_outlook_rejects_password(signed):
    payload = {
        "provider": "Outlook",
        "email": "seed@example.com",
        "imap_host": "outlook.office365.com",
        "spam_folder": "Junk",
        "password": "test-only",
    }
    assert signed.post("/api/seeds/1", json=payload).status_code == 422


def test_oauth_token_refresh_and_secret_non_disclosure(signed, db, monkeypatch):
    payload = {
        "provider": "Outlook",
        "email": "seed@example.com",
        "imap_host": "outlook.office365.com",
        "spam_folder": "Junk",
        "auth_method": "oauth2",
        "oauth_client_id": "test-client",
        "oauth_client_secret": "test-client-secret",
        "oauth_refresh_token": "test-refresh-token",
        "oauth_tenant": "common",
    }
    r = signed.post("/api/seeds/1", json=payload)
    assert r.status_code == 200
    assert "test-refresh-token" not in r.text and "test-client-secret" not in r.text
    seed = db.scalar(select(SeedMailbox))
    response = MagicMock()
    response.json.return_value = {
        "access_token": "test-access",
        "refresh_token": "rotated-test-refresh",
    }
    monkeypatch.setattr(mail.httpx, "post", lambda *a, **kw: response)
    assert mail.oauth_access_token(seed) == "test-access"
    assert "rotated-test-refresh" in decrypt(seed.encrypted_password)


def test_mailbox_failure_unknown_and_sender_scope(db, monkeypatch):
    seed = SeedMailbox(
        domain_id=1,
        provider="Gmail",
        email="seed@example.com",
        imap_host="imap.gmail.com",
        spam_folder="Spam",
        encrypted_password=encrypt("test-password"),
    )
    db.add(seed)
    db.commit()
    monkeypatch.setattr(mail, "send", lambda *a, **kw: True)
    ids = mail.start_placement(db, 1)
    test = db.get(PlacementTest, ids[0])
    assert "does not verify production" in test.sender_scope

    def fail_auth(*args):
        raise ValueError("Credentials must not be shown")

    monkeypatch.setattr(mail.PROVIDERS["Gmail"], "locate", fail_auth)
    assert (
        mail.finish_placement(db, test)
        and test.state == "Unknown"
        and test.detail == "ValueError"
    )
    mail.placement_summary(db, 1)
    assert snapshot(db, 1)["cards"][-1]["state"] == "Unknown"


def test_alert_api_admin_csrf_input_validation(signed, client):
    payload = {
        "enabled": True,
        "paused": False,
        "recipients": ["team@example.com"],
        "reminder_seconds": 300,
        "critical_only": False,
    }
    assert signed.put("/api/alerts/1/settings", json=payload).status_code == 200
    assert signed.get("/api/alerts/1").json()["settings"]["recipients"] == [
        "team@example.com"
    ]
    assert (
        signed.put(
            "/api/alerts/1/settings", json={**payload, "recipients": ["bad-address"]}
        ).status_code
        == 422
    )
    signed.headers.pop("X-CSRF-Token")
    assert signed.put("/api/alerts/1/settings", json=payload).status_code == 403
    r = client.post(
        "/api/auth/login",
        json={"email": "viewer@newhotmusic.com", "password": "Test-password-123"},
    )
    client.headers["X-CSRF-Token"] = r.json()["csrf"]
    assert client.put("/api/alerts/1/settings", json=payload).status_code == 403
    assert "settings" not in client.get("/api/alerts/1").json()


def test_signed_event_replay_conflict_and_new_kinds(signed, db):
    from test_api import signed_event

    payload = {
        "event_id": "evt-defer",
        "domain": "newhotmusic.com",
        "recipient_domain": "gmail.com",
        "kind": "deferred",
        "occurred_at": now().isoformat(),
    }
    assert signed_event(signed, payload).status_code == 200
    assert signed_event(signed, payload).json()["duplicate"]
    assert signed_event(signed, {**payload, "kind": "delivered"}).status_code == 409
    assert (
        signed_event(
            signed, {**payload, "event_id": "evt-complaint", "kind": "complaint"}
        ).status_code
        == 200
    )
    assert signed.get("/api/overview/1").json()["delivery"]["complaints"] == 1


def test_partial_smtp_does_not_retry_accepted_recipients(db, monkeypatch):
    fail(db)

    def partial(*args):
        raise mail.PartialDelivery()

    monkeypatch.setattr(mail, "send", partial)
    alerts.send_outbox(db)
    row = db.scalar(select(Alert))
    assert row.state == "Partial" and row.attempts == 1
    alerts.send_outbox(db)
    assert row.attempts == 1


def test_provider_normalizers_preserve_observed_events():
    from app.provider_events import normalize

    event = normalize(
        "postmark",
        {
            "RecordType": "Delivery",
            "MessageID": "observed-id",
            "Recipient": "seed@example.com",
            "DeliveredAt": now().isoformat(),
        },
        "newhotmusic.com",
    )
    assert (
        event["kind"] == "delivered"
        and event["recipient_domain"] == "example.com"
        and "seed@" not in str(event)
    )
    event = normalize(
        "sendgrid",
        {
            "sg_event_id": "provider-event",
            "event": "spamreport",
            "email": "seed@example.com",
            "timestamp": int(now().timestamp()),
        },
        "newhotmusic.com",
    )
    assert (
        event["kind"] == "complaint" and event["event_id"] == "sendgrid:provider-event"
    )


def test_disconnected_telemetry_is_not_a_success(db, monkeypatch):
    from app.worker import evaluate_delivery

    monkeypatch.setattr(config(), "delivery_webhook_secret", "")
    evaluate_delivery(db, 1)
    latest = db.scalar(
        select(Check).where(Check.category == "Delivery Rate").order_by(Check.id.desc())
    )
    assert latest.state == "Not Configured" and latest.evidence["delivery_rate"] is None


def test_disabled_seed_is_not_accessed(db, monkeypatch):
    seed = SeedMailbox(
        domain_id=1,
        provider="Gmail",
        email="disabled@example.com",
        imap_host="imap.gmail.com",
        spam_folder="Spam",
        encrypted_password=encrypt("test-password"),
        active=False,
    )
    db.add(seed)
    db.flush()
    test = PlacementTest(domain_id=1, seed_id=seed.id, token="disabled-test-token")
    db.add(test)
    db.commit()

    def prohibited(*args):
        raise AssertionError("Disabled mailbox was accessed")

    monkeypatch.setattr(mail.PROVIDERS["Gmail"], "locate", prohibited)
    assert (
        mail.finish_placement(db, test)
        and test.state == "Unknown"
        and "disabled" in test.detail
    )


def test_sender_refreshes_policy_after_another_session_disables(db):
    from sqlalchemy.orm import Session as OtherSession

    row = alerts.settings_row(db, 1)
    db.commit()
    assert row.value["enabled"]
    with OtherSession(bind=db.get_bind()) as other:
        setting = other.get(Setting, "alerts:1")
        setting.value = {**setting.value, "enabled": False}
        other.commit()
    assert alerts.settings_row(db, 1).value["enabled"] is False


def test_history_cap_keeps_latest_samples_and_marks_incomplete(signed, db):
    from sqlalchemy import insert

    at = now() - timedelta(hours=1)
    db.execute(
        insert(Check),
        [
            {
                "domain_id": 1,
                "category": "SPF",
                "state": "Unknown",
                "summary": f"sample-{i}",
                "evidence": {},
                "checked_at": at + timedelta(microseconds=i),
                "demo": False,
            }
            for i in range(10001)
        ],
    )
    db.commit()
    data = signed.get("/api/history/1").json()
    assert data["truncated"] is True and data["checks"][0]["summary"] == "sample-10000"


def test_malformed_signature_headers_rejected_not_server_error(client):
    timestamp = str(int(now().timestamp())).encode()
    assert (
        client.post(
            "/api/events/delivery",
            content=b"{}",
            headers=[
                (b"X-Event-Timestamp", timestamp),
                (b"X-Event-Signature", b"\xff"),
            ],
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/events/delivery",
            content=b"{}",
            headers={"X-Event-Timestamp": "9" * 100, "X-Event-Signature": "a" * 64},
        ).status_code
        == 401
    )
