"""Per-domain diagnostic outbox, suppression, bounded retries and observed recovery."""

import hashlib, json
from datetime import timedelta
from sqlalchemy import select, or_
from .config import config
from .db import insert_once
from .models import Alert, Domain, Issue, Setting, now
from .services import snapshot, latest_checks, aware, audit
from .diagnostics import diagnose

ACTIVE = ("Pending", "Retrying", "Not Configured")


def alert_preferences(db, domain_id):
    saved = db.get(Setting, f"alerts:{domain_id}")
    cfg = config()
    return {
        "enabled": cfg.alert_enabled,
        "paused": False,
        "recipients": [x.strip() for x in cfg.alert_recipients.split(",") if x.strip()],
        "reminder_seconds": max(300, cfg.alert_reminder_seconds),
        "critical_only": False,
        "revision": 0,
        **(saved.value if saved else {}),
    }


def settings_row(db, domain_id):
    key = f"alerts:{domain_id}"
    insert_once(
        db, Setting, {"key": key, "value": alert_preferences(db, domain_id)}, ["key"]
    )
    row = db.scalar(
        select(Setting)
        .where(Setting.key == key)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return row


def suppression(prefs, alert):
    if alert.kind == "Test":
        return None
    if not prefs["enabled"]:
        return "Email alerts disabled by administrator"
    if prefs["paused"]:
        return "Email alerts paused by administrator"
    if prefs["critical_only"] and not alert.payload.get("critical"):
        return "Critical-only alert policy"
    return None


def queue_recovery(db, issue, check):
    key = f"recovery:{issue.id}:{check.id}"
    pending = db.scalar(
        select(Alert).where(
            Alert.domain_id == issue.domain_id,
            Alert.kind == "Recovery",
            Alert.state == "Pending",
        )
    )
    observation = {
        "category": issue.category,
        "check_id": check.id,
        "at": check.checked_at.isoformat(),
        "critical": issue.severity == "Critical",
    }
    if pending:
        observations = {
            **pending.payload.get("observations", {}),
            str(issue.id): observation,
        }
        pending.payload = {
            **pending.payload,
            "observations": observations,
            "critical": any(x["critical"] for x in observations.values()),
        }
    elif not db.scalar(select(Alert.id).where(Alert.dedup_key == key)):
        db.add(
            Alert(
                domain_id=issue.domain_id,
                kind="Recovery",
                dedup_key=key,
                payload={
                    "critical": observation["critical"],
                    "observations": {str(issue.id): observation},
                },
                next_attempt_at=now(),
            )
        )


def enqueue_digest(db, domain_id):
    prefs = alert_preferences(db, domain_id)
    if config().demo_mode or not prefs["enabled"] or prefs["paused"]:
        return None
    checks = latest_checks(db, domain_id)
    if not checks:
        return None
    snap = snapshot(db, domain_id)
    findings = [c for c in snap["cards"] if c["state"] != "Healthy"]
    if not findings and snap["score"] == 100:
        return None
    critical = any(c["state"] == "Critical" for c in findings)
    if prefs["critical_only"] and not critical:
        return None
    outstanding = db.scalar(
        select(Alert).where(
            Alert.domain_id == domain_id,
            Alert.kind == "Diagnostic",
            Alert.state.in_(ACTIVE),
        )
    )
    if outstanding:
        outstanding.payload = diagnostic_payload(db, domain_id, snap)
        return outstanding
    recent = db.scalar(
        select(Alert)
        .where(
            Alert.domain_id == domain_id,
            Alert.kind == "Diagnostic",
            Alert.state != "Suppressed",
        )
        .order_by(Alert.created_at.desc())
    )
    if recent and (
        (now() - aware(recent.sent_at or recent.created_at)).total_seconds()
        < prefs["reminder_seconds"]
        or recent.state == "Failed"
        and recent.next_attempt_at
        and aware(recent.next_attempt_at) > now()
    ):
        return None
    cycle = int(now().timestamp()) // prefs["reminder_seconds"]
    key = f"diagnostic:{domain_id}:{prefs['revision']}:{cycle}"
    if db.scalar(select(Alert.id).where(Alert.dedup_key == key)):
        return None
    payload = diagnostic_payload(db, domain_id, snap)
    alert = Alert(
        created_at=now(),
        domain_id=domain_id,
        kind="Diagnostic",
        dedup_key=key,
        payload=payload,
        next_attempt_at=now(),
    )
    db.add(alert)
    audit(db, "monitor", "Diagnostic digest queued", domain_id=domain_id, cycle=cycle)
    return alert


def suppress_queued(db, domain_id, prefs):
    for alert in db.scalars(
        select(Alert)
        .where(Alert.domain_id == domain_id, Alert.state.in_(ACTIVE))
        .with_for_update()
        .execution_options(populate_existing=True)
    ):
        reason = suppression(prefs, alert)
        if reason:
            alert.state = "Suppressed"
            alert.suppression_reason = reason


def send_outbox(db):
    from .mail import send, PartialDelivery

    candidates = list(
        db.scalars(
            select(Alert.id)
            .where(
                Alert.state.in_(ACTIVE),
                or_(Alert.next_attempt_at.is_(None), Alert.next_attempt_at <= now()),
            )
            .order_by(Alert.id)
            .limit(10)
        )
    )
    for ident in candidates:
        preview = db.get(Alert, ident)
        if preview.domain_id is not None:
            settings_row(db, preview.domain_id)
        alert = db.scalar(
            select(Alert)
            .where(Alert.id == ident, Alert.state.in_(ACTIVE))
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        if not alert:
            db.commit()
            continue
        if alert.next_attempt_at and aware(alert.next_attempt_at) > now():
            db.commit()
            continue
        if alert.domain_id is None and alert.issue_id:
            issue = db.get(Issue, alert.issue_id)
            if issue:
                alert.domain_id = issue.domain_id
        if alert.kind == "Legacy":
            alert.state = "Suppressed"
            alert.suppression_reason = "Replaced by grouped domain diagnostic digest"
            db.commit()
            continue
        # Hold the policy row until SMTP finishes: once Disable/Pause returns, queued reminders cannot slip through.
        prefs = settings_row(db, alert.domain_id).value
        if alert.kind == "Diagnostic":
            alert.payload = diagnostic_payload(db, alert.domain_id)
        if alert.kind == "Recovery":
            observations = {
                k: v
                for k, v in alert.payload.get("observations", {}).items()
                if db.get(Issue, int(k))
                and db.get(Issue, int(k)).observed_state == "Healthy"
            }
            if not observations:
                alert.state = "Suppressed"
                alert.suppression_reason = "Recovery is no longer current"
                db.commit()
                continue
            domain = db.get(Domain, alert.domain_id)
            snap = snapshot(db, alert.domain_id)
            alert.payload = {
                **alert.payload,
                "subject": f"[SFP EMAIL HEALTH RECOVERY] {domain.name}",
                "body": f"Domain: {domain.name}\nHealth Score: {snap['score']} (provisional: {snap['provisional']})\nCoverage: {snap['coverage']}%\nObserved recovery: "
                + json.dumps(observations, default=str)
                + f"\nThese signals were observed Healthy. Issue closure still requires verification.\nDashboard: {config().dashboard_url}",
            }
        reason = suppression(prefs, alert)
        if reason:
            alert.state = "Suppressed"
            alert.suppression_reason = reason
            db.commit()
            continue
        if alert.kind == "Diagnostic":
            snap = snapshot(db, alert.domain_id)
            current = [c for c in snap["cards"] if c["state"] != "Healthy"]
            if not current and snap["score"] == 100:
                alert.state = "Suppressed"
                alert.suppression_reason = "All measured signals recovered"
                db.commit()
                continue
        try:
            if not send(
                alert.payload["subject"],
                alert.payload["body"],
                prefs["recipients"],
                False,
                "<"
                + hashlib.sha256(alert.dedup_key.encode()).hexdigest()
                + "@email-health.local>",
            ):
                alert.state = "Not Configured"
                alert.error = "SMTP sender or recipients not configured"
                alert.next_attempt_at = now() + timedelta(seconds=300)
            else:
                alert.attempts += 1
                alert.state = "Sent"
                alert.sent_at = now()
                alert.error = None
        except PartialDelivery:
            alert.attempts += 1
            alert.state = "Partial"
            alert.error = "Some recipients rejected; automatic full-list retry suppressed to avoid duplicate accepted mail"
        except Exception as exc:
            alert.attempts += 1
            alert.error = type(exc).__name__
            alert.state = "Failed" if alert.attempts >= 5 else "Retrying"
            delay = (
                1800
                if alert.state == "Failed"
                else min(300, 60 * 2 ** (alert.attempts - 1))
            )
            alert.next_attempt_at = now() + timedelta(seconds=delay)
        audit(
            db,
            "worker",
            "Alert delivery",
            alert_id=alert.id,
            state=alert.state,
            attempts=alert.attempts,
        )
        db.commit()
    db.commit()


def diagnostic_payload(db, domain_id, snap=None):
    snap = snap or snapshot(db, domain_id)
    findings = [c for c in snap["cards"] if c["state"] != "Healthy"]
    critical = any(c["state"] == "Critical" for c in findings)
    domain = db.get(Domain, domain_id)
    score = (
        "Unknown"
        if snap["score"] is None
        else str(snap["score"])
        + "/100"
        + (" (provisional)" if snap["provisional"] else "")
    )
    lines = [
        f"Domain: {domain.name}",
        f"Health Score: {score}",
        f"Monitoring Coverage: {snap['coverage']}%",
        f"Status: {snap['state']}",
        f"Generated: {now().isoformat()}",
        "Diagnostic findings (no automatic changes):",
    ]
    for card in findings:
        d = diagnose(card["category"], card["state"], card["summary"], card["evidence"])
        lines += (
            [
                "",
                f"{card['category']}: {card['state']}",
                f"Problem: {card['summary']}",
                f"Last checked: {card['checked_at'] or 'Never checked — no observation'}",
                f"Evidence: {json.dumps(card['evidence'], default=str)}",
                f"Likely cause: {d['likely_cause']}",
                f"Required access: {d['required_access']}",
                "Recommended solution:",
            ]
            + [f"{i + 1}. {step}" for i, step in enumerate(d["solution_steps"])]
            + [f"Verification: {d['verification']}"]
        )
    lines += [
        "",
        f"Dashboard: {config().dashboard_url}",
        "Unmeasured signals are not failures or proof of poor inbox placement. No exact DNS values are guessed.",
    ]
    return {
        "critical": critical,
        "subject": f"[SFP EMAIL HEALTH ALERT] {domain.name} — Health Score {score}",
        "body": "\n".join(lines),
    }
