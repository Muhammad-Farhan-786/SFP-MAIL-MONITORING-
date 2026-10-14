import json, hmac, hashlib, time
from sqlalchemy import select, func
from app.models import Issue, DeliveryEvent, SeedMailbox, now
from app.services import record


def test_protected(client):
    assert (
        client.get("/api/domains").status_code == 401
        and client.get("/api/overview/1").status_code == 401
    )


def test_bad_login(client):
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "admin@newhotmusic.com", "password": "wrong"},
        ).status_code
        == 401
    )


def test_cookie_csrf(signed):
    assert signed.get("/api/auth/me").json()["role"] == "admin" and signed.cookies.get(
        "session"
    )
    signed.headers.pop("X-CSRF-Token")
    assert signed.put("/api/domains/1", json={"name": "example.com"}).status_code == 403


def test_viewer(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "viewer@newhotmusic.com", "password": "Test-password-123"},
    )
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    assert (
        client.post("/api/domains", json={"name": "example.com"}).status_code == 403
        and client.get("/api/settings/1").status_code == 403
    )


def test_no_fake_data(signed):
    data = signed.get("/api/overview/1").json()
    assert data["score"] is None and data["delivery"]["delivery_rate"] is None
    assert all(c["state"] == "Never Checked" for c in data["cards"])


def test_history_and_issues(signed, db):
    record(
        db,
        1,
        "SPF",
        {"state": "Critical", "summary": "Missing SPF", "evidence": {"records": []}},
    )
    db.commit()
    assert (
        len(signed.get("/api/issues/1").json()) == 1
        and signed.get("/api/history/1").json()["checks"][0]["category"] == "SPF"
    )
    issue = db.scalar(select(Issue))
    assert (
        signed.patch(f"/api/issue/{issue.id}", json={"status": "Closed"}).status_code
        == 409
    )


def test_secrets_not_returned(signed, db):
    data = {
        "provider": "Gmail",
        "email": "seed@example.com",
        "imap_host": "imap.gmail.com",
        "spam_folder": "[Gmail]/Spam",
        "password": "test-app-password",
    }
    r = signed.post("/api/seeds/1", json=data)
    assert (
        r.status_code == 200
        and "password" not in r.json()
        and "test-app-password" not in r.text
    )
    assert db.scalar(select(SeedMailbox)).encrypted_password != "test-app-password"


def signed_event(client, payload, stamp=None):
    raw = json.dumps(payload).encode()
    stamp = str(stamp or int(time.time()))
    sig = hmac.new(
        b"test-webhook-secret", stamp.encode() + b"." + raw, hashlib.sha256
    ).hexdigest()
    return client.post(
        "/api/events/delivery",
        content=raw,
        headers={
            "X-Event-Timestamp": stamp,
            "X-Event-Signature": sig,
            "Content-Type": "application/json",
        },
    )


def test_events_idempotent(signed, db):
    data = {
        "event_id": "evt-1",
        "domain": "newhotmusic.com",
        "recipient_domain": "gmail.com",
        "kind": "hard_bounce",
        "occurred_at": now().isoformat(),
        "reason": "Mailbox does not exist",
    }
    assert (
        signed_event(signed, data).status_code == 200
        and signed_event(signed, data).json()["duplicate"]
    )
    assert db.scalar(select(func.count(DeliveryEvent.id))) == 1
    assert (
        signed.get("/api/overview/1").json()["delivery"]["bounce_rate"] == 100
        and signed.get("/api/history/1").json()["series"][0]["bounce_rate"] == 100
    )


def test_bad_signature(client):
    assert client.post("/api/events/delivery", json={}).status_code == 401


def test_expired_signature(client):
    assert signed_event(client, {}, int(time.time()) - 600).status_code == 401


def test_demo_data_excluded_in_production(signed, db):
    from app.models import Check

    db.add(
        Check(
            domain_id=1,
            category="SPF",
            state="Healthy",
            summary="DEMO sample",
            evidence={"demo": True},
            demo=True,
        )
    )
    db.commit()
    assert signed.get("/api/overview/1").json()["score"] is None
    assert signed.get("/api/history/1").json()["checks"] == []


def test_demo_requires_visible_flag_and_selects_only_demo(signed, db, monkeypatch):
    from app.config import config
    from app.models import Check

    monkeypatch.setattr(config(), "demo_mode", True)
    db.add(
        Check(
            domain_id=1,
            category="SPF",
            state="Critical",
            summary="Genuine",
            evidence={},
            demo=False,
        )
    )
    db.add(
        Check(
            domain_id=1,
            category="SPF",
            state="Healthy",
            summary="DEMO",
            evidence={"demo": True},
            demo=True,
        )
    )
    db.commit()
    assert signed.get("/api/auth/me").json()["demo_mode"] is True
    assert signed.get("/api/overview/1").json()["cards"][0]["summary"] == "DEMO"
