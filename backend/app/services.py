from datetime import timedelta, timezone
from collections import Counter
from sqlalchemy import select, func
from .models import *
from . import monitoring
from .config import config
from .diagnostics import diagnose

WEIGHTS = {
    "SPF": 12,
    "DKIM": 12,
    "DMARC": 12,
    "MX": 6,
    "PTR": 4,
    "SMTP": 8,
    "TLS": 8,
    "Delivery Rate": 10,
    "Bounce Rate": 8,
    "Blacklist": 8,
    "IP Reputation": 5,
    "Domain Reputation": 3,
    "Inbox Placement": 8,
}
INTERVALS = {
    "auth": 300,
    "smtp": 300,
    "reputation": 43200,
    "blacklist": 43200,
    "placement": 86400,
    "reports": 86400,
    "delivery": 300,
}
CATEGORY_GROUP = {
    "SPF": "auth",
    "DKIM": "auth",
    "DMARC": "auth",
    "MX": "auth",
    "PTR": "auth",
    "SMTP": "smtp",
    "TLS": "smtp",
    "Blacklist": "blacklist",
    "IP Reputation": "reputation",
    "Domain Reputation": "reputation",
    "Inbox Placement": "placement",
    "Delivery Rate": "delivery",
    "Bounce Rate": "delivery",
}


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def audit(db, actor, action, **detail):
    db.add(AuditLog(actor=actor, action=action, detail=detail))


def preferences(db):
    obj = db.get(Setting, "monitoring")
    result = {
        "intervals": {
            **INTERVALS,
            **{
                k: getattr(config(), k + "_interval_seconds", v)
                for k, v in INTERVALS.items()
            },
        },
        "bounce_threshold": 5,
        "failure_threshold": 5,
        "alert_cooldown": 3600,
        "health_healthy": 80,
        "health_excellent": 95,
        **(obj.value if obj else {}),
    }
    result["intervals"] = {**INTERVALS, **result["intervals"]}
    return result


def latest_checks(db, domain_id):
    ranked = (
        select(
            Check.id,
            func.row_number()
            .over(
                partition_by=Check.category,
                order_by=(Check.checked_at.desc(), Check.id.desc()),
            )
            .label("position"),
        )
        .where(
            Check.domain_id == domain_id,
            Check.demo.is_(config().demo_mode),
            Check.category != "Health Score",
        )
        .subquery()
    )
    query = (
        select(Check)
        .join(ranked, Check.id == ranked.c.id)
        .where(ranked.c.position == 1)
    )
    return {check.category: check for check in db.scalars(query)}


def alignment(events, field):
    known = [getattr(e, field) for e in events if getattr(e, field) is not None]
    return round(sum(known) / len(known) * 100, 2) if known else None


def delivery_stats(events):
    total = len(events)
    counts = Counter(e.kind for e in events)

    def pct(n):
        return round(n / total * 100, 2) if total else None

    return {
        "total": total,
        "delivered": counts["delivered"] if total else None,
        "measurement_state": "Measured" if total else "Not Measured",
        "complaints": counts["complaint"] if total else None,
        "deferred": counts["deferred"] + counts["temporary_failure"] if total else None,
        "delivery_rate": pct(counts["delivered"]),
        "bounce_rate": pct(counts["hard_bounce"] + counts["soft_bounce"]),
        "hard_bounce_rate": pct(counts["hard_bounce"]),
        "soft_bounce_rate": pct(counts["soft_bounce"]),
        "failure_rate": pct(total - counts["delivered"]),
        "spf_alignment_rate": alignment(events, "spf_aligned"),
        "dkim_alignment_rate": alignment(events, "dkim_aligned"),
    }


def health_score(checks, critical_issues=0):
    factors = []
    for category, weight in WEIGHTS.items():
        item = checks.get(category)
        state = (
            item["state"]
            if isinstance(item, dict)
            else item.state
            if item
            else "Never Checked"
        )
        if state not in ("Healthy", "Warning", "Critical"):
            factors.append(
                {"category": category, "weight": weight, "state": state, "earned": None}
            )
        else:
            factors.append(
                {
                    "category": category,
                    "weight": weight,
                    "state": state,
                    "earned": weight
                    * {"Healthy": 1, "Warning": 0.5, "Critical": 0}[state],
                }
            )
    known = sum(f["weight"] for f in factors if f["earned"] is not None)
    earned = sum(f["earned"] or 0 for f in factors)
    penalty = min(20, critical_issues * 5)
    score = max(0, round(earned / known * 100) - penalty) if known else None
    for factor in factors:
        factor["reduction"] = (
            round(100 * (factor["weight"] - factor["earned"]) / known, 2)
            if factor["earned"] is not None and known
            else None
        )
    return {
        "score": score,
        "coverage": round(known / sum(WEIGHTS.values()) * 100),
        "penalty": penalty,
        "factors": factors,
        "provisional": known < sum(WEIGHTS.values()),
    }


def snapshot(db, domain_id, days=7):
    prefs = preferences(db)
    latest = latest_checks(db, domain_id)
    cards = []
    for category in WEIGHTS:
        check = latest.get(category)
        state = check.state if check else "Never Checked"
        summary = check.summary if check else "No measurements yet."
        availability = (
            "Missing"
            if not check
            else "Not Configured"
            if state == "Not Configured"
            else "Unsupported"
            if state == "Unsupported"
            else "Unknown"
            if state == "Unknown"
            else "Measured"
        )
        if check and now() - aware(check.checked_at) > timedelta(
            seconds=prefs["intervals"].get(CATEGORY_GROUP.get(category, ""), 86400) * 2
        ):
            state = "Unknown"
            availability = "Stale"
            summary = "This measurement is stale. Run a new check."
        cards.append(
            {
                "category": category,
                "availability": availability,
                "state": state,
                "summary": summary,
                "checked_at": check.checked_at if check else None,
                "evidence": check.evidence if check else {},
            }
        )
    active = list(
        db.scalars(
            select(Issue).where(Issue.domain_id == domain_id, Issue.status != "Closed")
        )
    )
    score = health_score(
        {c["category"]: c for c in cards},
        sum(
            i.severity == "Critical"
            and i.status != "Verified"
            and i.observed_state != "Healthy"
            for i in active
        ),
    )
    state = (
        "Unknown"
        if score["score"] is None
        else "Excellent"
        if score["score"] >= prefs["health_excellent"]
        else "Healthy"
        if score["score"] >= prefs["health_healthy"]
        else "Warning"
        if score["score"] >= 50
        else "Critical"
    )
    events = list(
        db.scalars(
            select(DeliveryEvent).where(
                DeliveryEvent.domain_id == domain_id,
                DeliveryEvent.demo.is_(config().demo_mode),
                DeliveryEvent.occurred_at >= now() - timedelta(days=days),
            )
        )
    )
    summary = (
        "Connect your monitoring sources to understand email health."
        if score["score"] is None
        else "The measured signals are healthy."
        if state in ("Excellent", "Healthy")
        else "Email monitoring has found signals that need attention."
    )
    if score["provisional"] and score["score"] is not None:
        summary += " Some signals are unmeasured; this score is provisional."
    placements = list(
        db.scalars(
            select(PlacementTest)
            .where(PlacementTest.domain_id == domain_id)
            .order_by(PlacementTest.created_at.desc())
            .limit(30)
        )
    )
    return {
        **score,
        "state": state,
        "summary": summary,
        "cards": cards,
        "delivery": delivery_stats(events),
        "issues": {
            "open": len(active),
            "critical": sum(
                i.severity == "Critical" and i.status != "Verified" for i in active
            ),
            "verified": sum(i.status == "Verified" for i in active),
        },
        "scans": scan_status(db, domain_id, prefs),
        "placements": [
            {**serialize(p), "provider": db.get(SeedMailbox, p.seed_id).provider}
            for p in placements
        ],
    }


def serialize(obj):
    return {
        c.name: getattr(obj, c.name)
        for c in obj.__table__.columns
        if c.name not in ("password_hash", "encrypted_password")
    }


def record(db, domain_id, category, data):
    previous = latest_checks(db, domain_id).get(category)
    check = Check(domain_id=domain_id, category=category, **data)
    db.add(check)
    db.flush()
    if category in ("SPF", "DKIM", "DMARC", "MX", "PTR"):
        db.add(DNSResult(check_id=check.id, records=data["evidence"]))
        if category in ("SPF", "DKIM", "DMARC"):
            db.add(
                AuthenticationResult(
                    check_id=check.id, mechanism=category, alignment="Unknown"
                )
            )
    if category in ("SMTP", "TLS"):
        db.add(SMTPResult(check_id=check.id, hosts=data["evidence"].get("hosts", [])))
    if category == "Blacklist":
        for item in data["evidence"].get("sources", []):
            db.add(
                BlacklistResult(
                    check_id=check.id,
                    source=item["source"],
                    target=item["target"],
                    state=item["state"],
                    evidence=item,
                )
            )
    if category in ("IP Reputation", "Domain Reputation"):
        db.add(
            ReputationResult(
                check_id=check.id,
                source=data["evidence"].get("source", "Not Configured"),
                target=str(domain_id),
                value=data["evidence"],
            )
        )
    audit(
        db,
        "monitor",
        f"{category} check: {check.state}",
        domain_id=domain_id,
        check_id=check.id,
    )
    failed = check.state in (
        "Critical",
        "Warning",
        "Unknown",
        "Not Configured",
        "Not Measured",
    )
    changed = (
        previous is not None
        and category in ("SPF", "DKIM", "DMARC", "MX")
        and {k: v for k, v in previous.evidence.items() if k != "message_alignment"}
        != {k: v for k, v in check.evidence.items() if k != "message_alignment"}
        and previous.state == "Healthy"
    )
    fingerprint = f"{domain_id}:{category}"
    issue = db.scalar(
        select(Issue).where(Issue.fingerprint == fingerprint).with_for_update()
    )
    if failed or changed:
        if not issue:
            issue = Issue(
                domain_id=domain_id,
                fingerprint=fingerprint,
                title=f"{category} requires attention",
                category=category,
                severity="Critical" if check.state == "Critical" else "Medium",
                technical=check.summary,
                meaning="This signal may affect whether customers receive your email reliably.",
                action="\n".join(
                    diagnose(category, check.state, check.summary, check.evidence)[
                        "solution_steps"
                    ]
                ),
                impact="Messages may be delayed, rejected, or placed in spam.",
                evidence=check.evidence,
            )
            db.add(issue)
            db.flush()
            db.add(
                IssueHistory(
                    issue_id=issue.id,
                    status="Open",
                    actor="monitor",
                    note="Detected by a monitoring check",
                )
            )
        else:
            if issue.status in ("Closed", "Verified"):
                issue.status = "Open"
                issue.verified_at = None
                issue.verified_by = None
                issue.closed_at = None
                db.add(
                    IssueHistory(
                        issue_id=issue.id,
                        status="Open",
                        actor="monitor",
                        note="Failure recurred or configuration changed",
                    )
                )
            issue.last_seen = now()
            issue.technical = check.summary
            issue.evidence = check.evidence
            issue.severity = "Critical" if check.state == "Critical" else "Medium"
        issue.observed_state = check.state
        issue.recovered_at = None
        issue.diagnosis = diagnose(category, check.state, check.summary, check.evidence)
        issue.action = "\n".join(issue.diagnosis["solution_steps"])
        issue.meaning = check.summary
        issue.severity = (
            "Critical"
            if check.state == "Critical"
            else "Medium"
            if check.state == "Warning"
            else "Low"
        )
    elif issue and check.state == "Healthy" and issue.observed_state != "Healthy":
        from .alerts import queue_recovery

        issue.observed_state = "Healthy"
        issue.recovered_at = check.checked_at
        db.add(
            IssueHistory(
                issue_id=issue.id,
                status=issue.status,
                actor="monitor",
                note="Healthy recovery observed; retest verification still required before closure",
            )
        )
        queue_recovery(db, issue, check)
    from .alerts import enqueue_digest

    enqueue_digest(db, domain_id)
    return check


def execute_group(db, domain, group):
    addresses = list(
        db.scalars(select(SendingIP.address).where(SendingIP.domain_id == domain.id))
    )
    checks = monitoring.run(domain.name, domain.selectors, addresses, group)
    for category, data in checks.items():
        record(db, domain.id, category, data)
    db.flush()
    snap = snapshot(db, domain.id)
    db.add(
        Check(
            domain_id=domain.id,
            category="Health Score",
            state=snap["state"],
            summary=snap["summary"],
            evidence={
                k: snap[k] for k in ("score", "coverage", "penalty", "provisional")
            },
        )
    )
    from .alerts import enqueue_digest

    enqueue_digest(db, domain.id)
    db.commit()
    return checks


TRANSITIONS = {
    "Open": {"Assigned", "Fixing"},
    "Assigned": {"Fixing"},
    "Fixing": {"Ready for Retest"},
    "Ready for Retest": {"Retesting"},
    "Retesting": set(),
    "Verified": {"Closed"},
    "Closed": set(),
}


def transition(db, issue, status, actor, owner=None):
    if status not in TRANSITIONS.get(issue.status, set()):
        raise ValueError(
            f"Cannot move {issue.status} to {status}. A successful retest is required before closure."
        )
    if status == "Assigned" and not (owner or issue.owner):
        raise ValueError("Choose an owner before assigning the issue")
    if status == "Closed" and not issue.verified_at:
        raise ValueError("Verification required")
    issue.status = status
    if owner is not None:
        issue.owner = owner
    if status == "Closed":
        issue.closed_at = now()
    db.add(IssueHistory(issue_id=issue.id, status=status, actor=actor))
    audit(db, actor, "Issue status changed", issue_id=issue.id, status=status)


def verify_retest(db, issue, check, actor):
    if issue.status != "Retesting":
        raise ValueError("Issue is not retesting")
    success = (
        check
        and check.state == "Healthy"
        and aware(check.checked_at) >= aware(issue.last_seen)
    )
    issue.status = "Verified" if success else "Fixing"
    issue.retest_result = check.summary if check else "No verifiable result available"
    if success:
        issue.verified_by = actor
        issue.verified_at = now()
    db.add(
        IssueHistory(
            issue_id=issue.id,
            status=issue.status,
            actor=actor,
            note=issue.retest_result,
        )
    )
    audit(db, actor, "Issue retest completed", issue_id=issue.id, success=bool(success))
    return bool(success)


def scan_status(db, domain_id, prefs=None):
    prefs = prefs or preferences(db)
    jobs = {
        j.group: j
        for j in db.scalars(select(ScanJob).where(ScanJob.domain_id == domain_id))
    }
    return [
        {
            "group": group,
            "interval_seconds": seconds,
            **(
                serialize(jobs[group])
                if group in jobs
                else {
                    "state": "Never Checked",
                    "last_success_at": None,
                    "next_due_at": None,
                    "duration_seconds": None,
                }
            ),
        }
        for group, seconds in prefs["intervals"].items()
    ]
