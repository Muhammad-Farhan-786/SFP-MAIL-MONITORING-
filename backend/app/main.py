import json, hmac, hashlib, time, secrets, logging, re
from collections import defaultdict
from datetime import timedelta
from contextlib import asynccontextmanager
import dns.resolver
import redis
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select, text, func
from sqlalchemy.exc import IntegrityError
from .config import config
from .db import get_db, Session
from .models import *
from .schemas import *
from .security import current_user, admin, password_ok, hasher, create_token, encrypt
from .services import snapshot, serialize, preferences, transition, audit, aware
from .worker import monitor, retest, celery
from . import scheduling
from .alerts import alert_preferences, settings_row, suppress_queued, enqueue_digest

log = logging.getLogger("email-health")
cache = redis.Redis.from_url(config().redis_url)


@asynccontextmanager
async def lifespan(app):
    with Session() as db:
        db.execute(text("SELECT 1"))
    yield


app = FastAPI(title="NewHotMusic Email Health", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def safety(request, call_next):
    try:
        size = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        return JSONResponse({"detail": "Invalid content length"}, status_code=400)
    if size > 65536:
        return JSONResponse({"detail": "Request is too large"}, status_code=413)
    response = await call_next(request)
    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "same-origin",
            "Cache-Control": "no-store",
        }
    )
    return response


def limit(key, maximum, seconds):
    try:
        with cache.pipeline() as pipe:
            pipe.incr(key)
            pipe.expire(key, seconds, nx=True)
            count, _ = pipe.execute()
        if count > maximum:
            raise HTTPException(429, "Too many requests. Try again later.")
    except redis.RedisError:
        raise HTTPException(503, "Rate limit service unavailable")


@app.get("/api/health")
def health(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(data: Login, request: Request, response: Response, db=Depends(get_db)):
    limit("login:" + request.client.host, 10, 900)
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    # Always hash-check, including unknown email addresses.
    valid = password_ok(user.password_hash if user else DUMMY_HASH, data.password)
    if not user or not user.active or not valid:
        audit(db, "anonymous", "Login failed")
        db.commit()
        raise HTTPException(401, "Invalid email or password")
    token, csrf = create_token(user)
    response.set_cookie(
        "session",
        token,
        httponly=True,
        secure=config().cookie_secure,
        samesite="strict",
        max_age=28800,
        path="/",
    )
    response.set_cookie(
        "csrf",
        csrf,
        secure=config().cookie_secure,
        samesite="strict",
        max_age=28800,
        path="/",
    )
    audit(db, user.email, "Login successful")
    db.commit()
    return {"email": user.email, "role": user.role, "csrf": csrf}


DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return {"email": user.email, "role": user.role, "demo_mode": config().demo_mode}


@app.post("/api/auth/logout")
def logout(response: Response, user=Depends(current_user)):
    response.delete_cookie("session")
    response.delete_cookie("csrf")
    return {"ok": True}


@app.get("/api/domains")
def domains(db=Depends(get_db), user=Depends(current_user)):
    return [serialize(d) for d in db.scalars(select(Domain).order_by(Domain.id))]


@app.post("/api/domains")
def add_domain(data: DomainInput, db=Depends(get_db), user=Depends(admin)):
    if db.scalar(select(Domain).where(Domain.name == data.name)):
        raise HTTPException(409, "Domain already exists")
    d = Domain(name=data.name, selectors=data.selectors)
    db.add(d)
    db.flush()
    for address in data.sending_ips:
        db.add(SendingIP(domain_id=d.id, address=address))
    audit(db, user.email, "Domain added", domain=data.name)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Sending IP already exists")
    return serialize(d)


@app.put("/api/domains/{domain_id}")
def edit_domain(
    domain_id: int, data: DomainInput, db=Depends(get_db), user=Depends(admin)
):
    domain = db.get(Domain, domain_id)
    if not domain:
        raise HTTPException(404, "Domain not found")
    domain.name = data.name
    domain.selectors = data.selectors
    for old in db.scalars(select(SendingIP).where(SendingIP.domain_id == domain_id)):
        db.delete(old)
    db.flush()
    for address in data.sending_ips:
        db.add(SendingIP(domain_id=domain_id, address=address))
    audit(db, user.email, "Domain updated", domain_id=domain_id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Domain or sending IP already exists")
    return serialize(domain)


@app.get("/api/overview/{domain_id}")
def overview(
    domain_id: int, days: int = 7, db=Depends(get_db), user=Depends(current_user)
):
    if days not in (1, 7, 30, 90):
        raise HTTPException(422, "Unsupported date range")
    if not db.get(Domain, domain_id):
        raise HTTPException(404, "Domain not found")
    return snapshot(db, domain_id, days)


@app.post("/api/monitor/{domain_id}/{group}")
def launch(domain_id: int, group: str, db=Depends(get_db), user=Depends(admin)):
    if group not in (
        "auth",
        "smtp",
        "reputation",
        "blacklist",
        "placement",
        "reports",
        "delivery",
    ):
        raise HTTPException(422, "Unknown monitor group")
    if not db.get(Domain, domain_id):
        raise HTTPException(404, "Domain not found")
    limit(f"monitor:{domain_id}:{group}", 2, 300)
    job = scheduling.reserve(db, domain_id, group, manual=True)
    if not job:
        raise HTTPException(
            409, "A scan for this category is already queued or running"
        )
    task_id = scheduling.publish(db, job, monitor)
    audit(db, user.email, "Monitoring requested", domain_id=domain_id, group=group)
    db.commit()
    return {"task_id": task_id, "state": job.state}


@app.get("/api/history/{domain_id}")
def history(
    domain_id: int, days: int = 7, db=Depends(get_db), user=Depends(current_user)
):
    if days not in (1, 7, 30, 90):
        raise HTTPException(422, "Unsupported date range")
    since = now() - timedelta(days=days)
    checks = list(
        db.scalars(
            select(Check)
            .where(
                Check.domain_id == domain_id,
                Check.demo.is_(config().demo_mode),
                Check.checked_at >= since,
            )
            .order_by(Check.checked_at.desc(), Check.id.desc())
            .limit(10000)
        )
    )
    events = list(
        db.scalars(
            select(DeliveryEvent)
            .where(
                DeliveryEvent.domain_id == domain_id,
                DeliveryEvent.demo.is_(config().demo_mode),
                DeliveryEvent.occurred_at >= since,
            )
            .order_by(DeliveryEvent.occurred_at.desc(), DeliveryEvent.id.desc())
            .limit(100000)
        )
    )
    checks.reverse()
    events.reverse()
    issues = list(
        db.scalars(
            select(Issue).where(
                Issue.domain_id == domain_id, Issue.detected_at >= since
            )
        )
    )
    placements = list(
        db.scalars(
            select(PlacementTest).where(
                PlacementTest.domain_id == domain_id, PlacementTest.created_at >= since
            )
        )
    )
    buckets = defaultdict(
        lambda: {
            "health": None,
            "delivery": [],
            "checks": [],
            "placement": [],
            "issues": 0,
            "reputation": None,
        }
    )

    def bucket(t):
        return aware(t).strftime(
            "%Y-%m-%dT%H:00:00Z" if days == 1 else "%Y-%m-%dT00:00:00Z"
        )

    for check in checks:
        b = buckets[bucket(check.checked_at)]
        b["checks"].append(check)
        if check.category == "Health Score":
            b["health"] = check.evidence.get("score")
        if check.category == "IP Reputation":
            values = check.evidence.get("targets", [])
            if values:
                b["reputation"] = 100 - max(v["abuse_confidence"] for v in values)
    for event in events:
        buckets[bucket(event.occurred_at)]["delivery"].append(event)
    for p in placements:
        buckets[bucket(p.created_at)]["placement"].append(p)
    for i in issues:
        buckets[bucket(i.detected_at)]["issues"] += 1
    data = []
    from .services import delivery_stats

    for key, b in sorted(buckets.items()):
        stats = delivery_stats(b["delivery"])
        auth = [
            e
            for e in b["delivery"]
            if e.spf_pass is not None or e.dkim_pass is not None
        ]
        data.append(
            {
                "time": key,
                "health": b["health"],
                "delivery_rate": stats["delivery_rate"],
                "bounce_rate": stats["bounce_rate"],
                "failures": stats["total"] - stats["delivered"]
                if stats["total"]
                else None,
                "authentication": round(
                    sum(e.spf_pass is True or e.dkim_pass is True for e in auth)
                    / len(auth)
                    * 100,
                    2,
                )
                if auth
                else None,
                "inbox": sum(p.state == "Inbox" for p in b["placement"])
                if b["placement"]
                else None,
                "spam": sum(p.state == "Spam" for p in b["placement"])
                if b["placement"]
                else None,
                "reputation": b["reputation"],
                "issues": b["issues"],
            }
        )
    return {
        "series": data,
        "checks": [serialize(c) for c in reversed(checks[-250:])],
        "truncated": len(events) == 100000 or len(checks) == 10000,
    }


@app.get("/api/issues/{domain_id}")
def issues(domain_id: int, db=Depends(get_db), user=Depends(current_user)):
    return [
        serialize(i)
        for i in db.scalars(
            select(Issue)
            .where(Issue.domain_id == domain_id)
            .order_by(Issue.last_seen.desc())
        )
    ]


@app.get("/api/issue/{issue_id}/history")
def issue_history(issue_id: int, db=Depends(get_db), user=Depends(current_user)):
    return [
        serialize(h)
        for h in db.scalars(
            select(IssueHistory)
            .where(IssueHistory.issue_id == issue_id)
            .order_by(IssueHistory.at)
        )
    ]


@app.patch("/api/issue/{issue_id}")
def update_issue(
    issue_id: int, data: IssueUpdate, db=Depends(get_db), user=Depends(admin)
):
    issue = db.scalar(select(Issue).where(Issue.id == issue_id).with_for_update())
    if not issue:
        raise HTTPException(404, "Issue not found")
    try:
        transition(db, issue, data.status, user.email, data.owner)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    db.commit()
    if data.status == "Retesting":
        try:
            retest.delay(issue.id, user.email)
        except Exception:
            issue.status = "Ready for Retest"
            db.add(
                IssueHistory(
                    issue_id=issue.id,
                    status=issue.status,
                    actor="system",
                    note="Queue unavailable",
                )
            )
            db.commit()
            raise HTTPException(503, "Retest queue unavailable; please retry")
    return serialize(issue)


@app.get("/api/activity")
def activity(db=Depends(get_db), user=Depends(current_user)):
    return [
        serialize(a)
        for a in db.scalars(select(AuditLog).order_by(AuditLog.at.desc()).limit(50))
    ]


@app.get("/api/reports/{domain_id}")
def reports(domain_id: int, db=Depends(get_db), user=Depends(current_user)):
    return [
        serialize(r)
        for r in db.scalars(
            select(Report)
            .where(Report.domain_id == domain_id)
            .order_by(Report.generated_at.desc())
            .limit(90)
        )
    ]


@app.get("/api/settings/{domain_id}")
def settings(domain_id: int, db=Depends(get_db), user=Depends(admin)):
    cfg = config()
    return {
        "monitoring": preferences(db),
        "alerts": alert_preferences(db, domain_id),
        "domain": serialize(db.get(Domain, domain_id))
        if db.get(Domain, domain_id)
        else None,
        "sending_ips": list(
            db.scalars(
                select(SendingIP.address).where(SendingIP.domain_id == domain_id)
            )
        ),
        "seeds": [
            serialize(s)
            for s in db.scalars(
                select(SeedMailbox).where(SeedMailbox.domain_id == domain_id)
            )
        ],
        "integrations": {
            "SMTP": bool(cfg.smtp_host and cfg.smtp_from),
            "Email alerts": bool(
                cfg.smtp_host and alert_preferences(db, domain_id)["recipients"]
            ),
            "AbuseIPDB": bool(cfg.abuseipdb_key),
            "DNSBL": bool(cfg.dnsbl_zones or cfg.domain_dnsbl_zones),
            "Domain reputation": bool(cfg.domain_reputation_url),
            "Delivery webhook": bool(cfg.delivery_webhook_secret),
        },
        "demo_mode": cfg.demo_mode,
    }


@app.put("/api/settings")
def update_settings(data: SettingsInput, db=Depends(get_db), user=Depends(admin)):
    if data.health_excellent < data.health_healthy:
        raise HTTPException(422, "Excellent threshold must exceed healthy threshold")
    setting = db.get(Setting, "monitoring")
    if setting:
        setting.value = data.model_dump()
    else:
        db.add(Setting(key="monitoring", value=data.model_dump()))
    audit(db, user.email, "Monitoring settings updated")
    db.commit()
    return {"ok": True}


@app.post("/api/seeds/{domain_id}")
def add_seed(domain_id: int, data: SeedInput, db=Depends(get_db), user=Depends(admin)):
    if not db.get(Domain, domain_id):
        raise HTTPException(404, "Domain not found")
    seed = SeedMailbox(
        domain_id=domain_id,
        **data.model_dump(
            exclude={
                "password",
                "oauth_client_id",
                "oauth_client_secret",
                "oauth_refresh_token",
                "oauth_tenant",
            }
        ),
        encrypted_password=encrypt(
            data.password
            if data.auth_method == "password"
            else json.dumps(
                {
                    "client_id": data.oauth_client_id,
                    "client_secret": data.oauth_client_secret,
                    "refresh_token": data.oauth_refresh_token,
                    "tenant": data.oauth_tenant,
                }
            )
        ),
    )
    db.add(seed)
    audit(db, user.email, "Seed mailbox added", provider=data.provider)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Mailbox already exists")
    return serialize(seed)


@app.delete("/api/seeds/{seed_id}")
def disable_seed(seed_id: int, db=Depends(get_db), user=Depends(admin)):
    seed = db.get(SeedMailbox, seed_id)
    if not seed:
        raise HTTPException(404, "Mailbox not found")
    seed.active = False
    audit(db, user.email, "Seed mailbox disabled", seed_id=seed_id)
    db.commit()
    return {"ok": True}


@app.post("/api/users")
def add_user(data: UserInput, db=Depends(get_db), user=Depends(admin)):
    obj = User(
        email=data.email.lower(),
        password_hash=hasher.hash(data.password),
        role=data.role,
    )
    db.add(obj)
    audit(db, user.email, "User created", email=data.email, role=data.role)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "User already exists")
    return serialize(obj)


@app.post("/api/events/delivery")
async def delivery(request: Request, db=Depends(get_db)):
    cfg = config()
    if not cfg.delivery_webhook_secret:
        raise HTTPException(503, "Delivery webhook is not configured")
    raw = await request.body()
    if len(raw) > 65536:
        raise HTTPException(413, "Request too large")
    stamp = request.headers.get("X-Event-Timestamp", "")
    signature = request.headers.get("X-Event-Signature", "")
    if not re.fullmatch(r"[0-9a-f]{64}", signature) or not re.fullmatch(
        r"[0-9]{1,12}", stamp
    ):
        raise HTTPException(401, "Invalid signature headers")
    try:
        if abs(time.time() - int(stamp)) > 300:
            raise ValueError()
    except ValueError:
        raise HTTPException(401, "Invalid signature timestamp")
    expected = hmac.new(
        cfg.delivery_webhook_secret.encode(),
        stamp.encode() + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "Invalid signature")
    try:
        data = DeliveryInput.model_validate_json(raw)
    except ValueError:
        raise HTTPException(422, "Invalid delivery event")
    domain = db.scalar(select(Domain).where(Domain.name == data.domain))
    if not domain:
        raise HTTPException(404, "Domain is not monitored")
    payload_hash = hashlib.sha256(data.model_dump_json().encode()).hexdigest()
    existing = db.scalar(
        select(DeliveryEvent).where(DeliveryEvent.event_id == data.event_id)
    )
    if existing:
        if (
            existing.domain_id != domain.id
            or existing.payload_hash
            and existing.payload_hash != payload_hash
        ):
            raise HTTPException(409, "Event ID already used with a different payload")
        return {"id": existing.id, "duplicate": True}
    obj = DeliveryEvent(
        domain_id=domain.id,
        payload_hash=payload_hash,
        **data.model_dump(exclude={"domain"}),
    )
    db.add(obj)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(DeliveryEvent).where(DeliveryEvent.event_id == data.event_id)
        )
        if (
            existing
            and existing.domain_id == domain.id
            and existing.payload_hash == payload_hash
        ):
            return {"id": existing.id, "duplicate": True}
        raise HTTPException(409, "Conflicting delivery event")
    if data.kind in ("hard_bounce", "soft_bounce"):
        db.add(Bounce(event_id=obj.id, kind=data.kind, reason=data.reason))
    audit(db, "webhook", "Delivery event received", kind=data.kind, domain_id=domain.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"duplicate": True}
    return {"id": obj.id, "duplicate": False}


@app.get("/api/system")
def system(db=Depends(get_db), user=Depends(current_user)):
    db.execute(text("SELECT 1"))
    cfg = config()
    heartbeat = db.get(Setting, "scheduler_heartbeat")
    scheduler = "Unavailable"
    if heartbeat:
        scheduler = (
            "Operational"
            if (now() - datetime.fromisoformat(heartbeat.value["at"])).total_seconds()
            < 180
            else "Degraded"
        )
    try:
        cache.ping()
        queue = "Operational"
    except redis.RedisError:
        queue = "Unavailable"
    try:
        workers = celery.control.inspect(timeout=1).ping()
        worker = "Operational" if workers else "Unavailable"
    except Exception:
        worker = "Unavailable"
    last = db.scalar(
        select(Check)
        .where(Check.demo.is_(config().demo_mode), Check.state == "Healthy")
        .order_by(Check.checked_at.desc())
    )
    try:
        dns.resolver.resolve(cfg.domain, "NS", lifetime=2)
        resolver = "Operational"
    except Exception:
        resolver = "Degraded"
    return {
        "services": {
            "Database": "Operational",
            "Job queue": queue,
            "Monitoring Engine": worker,
            "Scheduler": scheduler,
            "DNS Resolver": resolver,
            "SMTP Tester": worker,
            "Inbox Placement Worker": worker
            if db.scalar(select(SeedMailbox).where(SeedMailbox.active.is_(True)))
            else "Not Configured",
            "Reputation Integrations": "Configured"
            if cfg.abuseipdb_key
            else "Not Configured",
            "Email alerts": "Configured"
            if cfg.smtp_host and cfg.alert_recipients
            else "Not Configured",
        },
        "last_successful_check": last.checked_at if last else None,
        "scheduler_heartbeat": heartbeat.value["at"] if heartbeat else None,
        "alerts": [
            serialize(a)
            for a in db.scalars(
                select(Alert).order_by(Alert.created_at.desc()).limit(30)
            )
        ],
    }


@app.get("/api/alerts/{domain_id}")
def alerts_status(domain_id: int, db=Depends(get_db), user=Depends(current_user)):
    if not db.get(Domain, domain_id):
        raise HTTPException(404, "Domain not found")
    rows = list(
        db.scalars(
            select(Alert)
            .where(Alert.domain_id == domain_id)
            .order_by(Alert.created_at.desc())
            .limit(100)
        )
    )
    result = {
        "history": [serialize(a) for a in rows],
        "last_sent": next((a.sent_at for a in rows if a.sent_at), None),
        "last_delivery_status": rows[0].state if rows else "Never Sent",
    }
    if user.role == "admin":
        result["settings"] = alert_preferences(db, domain_id)
    return result


@app.put("/api/alerts/{domain_id}/settings")
def save_alerts(
    domain_id: int, data: AlertSettingsInput, db=Depends(get_db), user=Depends(admin)
):
    if not db.get(Domain, domain_id):
        raise HTTPException(404, "Domain not found")
    row = settings_row(db, domain_id)
    prefs = {**data.model_dump(), "revision": row.value.get("revision", 0) + 1}
    row.value = prefs
    suppress_queued(db, domain_id, prefs)
    audit(
        db,
        user.email,
        "Alert policy changed",
        domain_id=domain_id,
        enabled=data.enabled,
        paused=data.paused,
    )
    db.commit()
    return prefs


@app.post("/api/alerts/{domain_id}/test")
def test_alert(domain_id: int, db=Depends(get_db), user=Depends(admin)):
    domain = db.get(Domain, domain_id)
    if not domain:
        raise HTTPException(404, "Domain not found")
    limit(f"alert-test:{domain_id}", 2, 300)
    prefs = alert_preferences(db, domain_id)
    if not prefs["recipients"]:
        raise HTTPException(422, "Configure alert recipients first")
    if not config().smtp_host or not config().smtp_from:
        raise HTTPException(422, "Configure notification SMTP first")
    import uuid

    obj = Alert(
        domain_id=domain_id,
        kind="Test",
        dedup_key="test:" + uuid.uuid4().hex,
        next_attempt_at=now(),
        payload={
            "critical": False,
            "subject": f"[SFP EMAIL HEALTH TEST] {domain.name}",
            "body": f"This is an explicitly requested notification delivery test, not an email health measurement.\nGenerated: {now().isoformat()}\nDashboard: {config().dashboard_url}",
        },
    )
    db.add(obj)
    db.flush()
    audit(db, user.email, "Alert test requested", domain_id=domain_id, alert_id=obj.id)
    db.commit()
    return {"id": obj.id, "state": obj.state}
