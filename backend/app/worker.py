import json, logging
from datetime import timedelta
from celery import Celery
from sqlalchemy import select, text
from .config import config
from .db import Session, engine
from .models import *
from .services import *
from . import mail
from . import scheduling
from .alerts import enqueue_digest, send_outbox

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("email-health")
celery = Celery("email-health", broker=config().redis_url, backend=config().redis_url)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    task_soft_time_limit=270,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "dispatch": {
            "task": "app.worker.dispatch",
            "schedule": 30.0,
            "options": {"expires": 25},
        },
        "alerts": {
            "task": "app.worker.deliver_alerts",
            "schedule": 30.0,
            "options": {"expires": 25},
        },
    },
)


@celery.task
def monitor(domain_id, group, token=None):
    with engine.connect() as lock, Session() as db:
        key = domain_id * 100 + list(INTERVALS).index(group)
        if not lock.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}):
            return
        job = None
        try:
            if config().demo_mode:
                return
            domain = db.get(Domain, domain_id)
            if not domain or not domain.active:
                return
            if token:
                job = scheduling.start(db, domain_id, group, token)
                if not job:
                    return
            else:
                job = scheduling.reserve(db, domain_id, group, manual=True)
                if not job:
                    return
                db.commit()
                job = scheduling.start(db, domain_id, group, job.task_id)
            if group == "placement":
                pending = mail.start_placement(db, domain_id)
                for ident in pending:
                    collect_placement.apply_async(
                        args=[ident], countdown=config().seed_wait_seconds
                    )
                if pending:
                    job.state = "Waiting"
                    job.lease_until = now() + timedelta(
                        seconds=config().seed_missing_after_seconds + 300
                    )
                    db.commit()
                    finish_placement_scan.apply_async(
                        args=[job.id, job.task_id, pending],
                        countdown=config().seed_missing_after_seconds + 30,
                    )
                    return
                mail.placement_summary(db, domain_id)
            elif group == "reports":
                generate_reports(db, domain)
            elif group == "delivery":
                evaluate_delivery(db, domain_id)
            else:
                execute_group(db, domain, group)
            categories = [c for c, g in CATEGORY_GROUP.items() if g == group]
            values = [
                c.state
                for name, c in latest_checks(db, domain_id).items()
                if name in categories
            ]
            state = (
                "Not Configured"
                if values
                and all(v in ("Not Configured", "Not Measured") for v in values)
                else "Degraded"
                if any(v == "Unknown" for v in values)
                else "Completed"
            )
            scheduling.finish(db, job, state)
            logger.info(
                json.dumps(
                    {
                        "event": "monitor_complete",
                        "domain_id": domain_id,
                        "group": group,
                        "state": state,
                        "duration_seconds": job.duration_seconds,
                    }
                )
            )
        except Exception as exc:
            db.rollback()
            if job:
                scheduling.finish(
                    db, db.get(ScanJob, job.id), "Failed", type(exc).__name__
                )
            logger.error(
                json.dumps(
                    {
                        "event": "monitor_failed",
                        "domain_id": domain_id,
                        "group": group,
                        "error": type(exc).__name__,
                    }
                )
            )
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            lock.commit()


@celery.task
def finish_placement_scan(job_id, token, ids):
    with Session() as db:
        job = db.scalar(select(ScanJob).where(ScanJob.id == job_id).with_for_update())
        if not job or job.task_id != token or job.state != "Waiting":
            return
        for ident in ids:
            test = db.get(PlacementTest, ident)
            if test and test.state == "Pending":
                mail.finish_placement(db, test)
        mail.placement_summary(db, job.domain_id)
        latest = latest_checks(db, job.domain_id).get("Inbox Placement")
        scheduling.finish(
            db, job, "Degraded" if latest and latest.state == "Unknown" else "Completed"
        )


@celery.task
def collect_placement(test_id):
    with Session() as db:
        test = db.get(PlacementTest, test_id)
        if test and test.state == "Pending":
            if not mail.finish_placement(db, test):
                collect_placement.apply_async(args=[test_id], countdown=60)
            else:
                mail.placement_summary(db, test.domain_id)


@celery.task
def retest(issue_id, actor):
    with engine.connect() as lock, Session() as db:
        issue = db.scalar(select(Issue).where(Issue.id == issue_id).with_for_update())
        if not issue or issue.status != "Retesting":
            return
        domain = db.get(Domain, issue.domain_id)
        group = CATEGORY_GROUP.get(issue.category)
        active = db.scalar(
            select(ScanJob).where(
                ScanJob.domain_id == issue.domain_id, ScanJob.group == group
            )
        )
        if (
            active
            and active.state in scheduling.BUSY
            and active.lease_until
            and aware(active.lease_until) > now()
        ):
            issue.status = "Ready for Retest"
            issue.retest_result = "A category scan is already queued or running; retry after it completes."
            db.add(
                IssueHistory(
                    issue_id=issue_id,
                    status=issue.status,
                    actor=actor,
                    note=issue.retest_result,
                )
            )
            db.commit()
            return
        key = (
            issue.domain_id * 100 + list(INTERVALS).index(group)
            if group in INTERVALS
            else None
        )
        if key is None or not lock.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
        ):
            issue.status = "Ready for Retest"
            issue.retest_result = (
                "A category scan is already running; retry after it completes."
            )
            db.add(
                IssueHistory(
                    issue_id=issue_id,
                    status=issue.status,
                    actor=actor,
                    note=issue.retest_result,
                )
            )
            db.commit()
            return
        try:
            if group == "delivery":
                evaluate_delivery(db, domain.id)
            elif group == "placement":
                ids = mail.start_placement(db, domain.id)
                if ids:
                    for ident in ids:
                        collect_placement.apply_async(
                            args=[ident], countdown=config().seed_wait_seconds
                        )
                    finish_placement_retest.apply_async(
                        args=[issue_id, actor, ids],
                        countdown=config().seed_missing_after_seconds + 120,
                    )
                    return
                mail.placement_summary(db, domain.id)
            elif group in INTERVALS:
                execute_group(db, domain, group)
            check = latest_checks(db, domain.id).get(issue.category)
            verify_retest(db, issue, check, actor)
            db.commit()
        except Exception as exc:
            db.rollback()
            issue = db.get(Issue, issue_id)
            issue.status = "Fixing"
            issue.retest_result = type(exc).__name__
            db.add(
                IssueHistory(
                    issue_id=issue_id,
                    status="Fixing",
                    actor=actor,
                    note="Retest could not complete",
                )
            )
            db.commit()
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            lock.commit()


@celery.task
def finish_placement_retest(issue_id, actor, test_ids):
    with Session() as db:
        issue = db.get(Issue, issue_id)
        if not issue or issue.status != "Retesting":
            return
        for ident in test_ids:
            test = db.get(PlacementTest, ident)
            if test.state == "Pending":
                mail.finish_placement(db, test)
        mail.placement_summary(db, issue.domain_id)
        verify_retest(
            db, issue, latest_checks(db, issue.domain_id).get("Inbox Placement"), actor
        )
        db.commit()


def evaluate_delivery(db, domain_id):
    events = list(
        db.scalars(
            select(DeliveryEvent).where(
                DeliveryEvent.domain_id == domain_id,
                DeliveryEvent.demo.is_(False),
                DeliveryEvent.occurred_at >= now() - timedelta(hours=24),
            )
        )
    )
    stats = delivery_stats(events)
    prefs = preferences(db)
    for category, value, limit in [
        ("Bounce Rate", stats["bounce_rate"], prefs["bounce_threshold"]),
        ("Delivery Rate", stats["failure_rate"], prefs["failure_threshold"]),
    ]:
        state = (
            ("Not Measured" if config().delivery_webhook_secret else "Not Configured")
            if value is None
            else "Critical"
            if value > limit * 2
            else "Warning"
            if value > limit
            else "Healthy"
        )
        record(
            db,
            domain_id,
            category,
            {
                "state": state,
                "summary": "Delivery provider telemetry is Not Measured; no events received."
                if value is None
                else "Delivery telemetry evaluated over the past 24 hours.",
                "evidence": stats,
            },
        )
    db.commit()


def generate_reports(db, domain):
    for period, days in [("daily", 1), ("weekly", 7)]:
        start = now().replace(hour=0, minute=0, second=0, microsecond=0)
        if period == "weekly":
            start -= timedelta(days=start.weekday())
        if db.scalar(
            select(Report).where(
                Report.domain_id == domain.id,
                Report.period == period,
                Report.period_start == start,
            )
        ):
            continue
        content = snapshot(db, domain.id, days)
        content["new_issues"] = db.scalar(
            select(func.count(Issue.id)).where(
                Issue.domain_id == domain.id,
                Issue.detected_at >= now() - timedelta(days=days),
            )
        )
        content["resolved_issues"] = db.scalar(
            select(func.count(Issue.id)).where(
                Issue.domain_id == domain.id,
                Issue.closed_at >= now() - timedelta(days=days),
            )
        )
        content["verified_fixes"] = db.scalar(
            select(func.count(Issue.id)).where(
                Issue.domain_id == domain.id,
                Issue.verified_at >= now() - timedelta(days=days),
            )
        )
        # Serialize datetimes before JSON persistence.
        content = json.loads(json.dumps(content, default=str))
        db.add(
            Report(
                domain_id=domain.id, period=period, period_start=start, content=content
            )
        )
        db.commit()
        key = f"summary:{domain.id}:{period}:{start.isoformat()}"
        if not db.scalar(select(Alert.id).where(Alert.dedup_key == key)):
            db.add(
                Alert(
                    domain_id=domain.id,
                    kind="Summary",
                    dedup_key=key,
                    next_attempt_at=now(),
                    payload={
                        "critical": False,
                        "subject": f"NewHotMusic {period} email health summary",
                        "body": f"Health: {content['state']}\nScore: {content['score']} (provisional: {content['provisional']})\nCoverage: {content['coverage']}%\n{content['summary']}\nOpen issues: {content['issues']['open']}\nDelivery: {content['delivery']}",
                    },
                )
            )
            db.commit()


@celery.task
def dispatch():
    with engine.connect() as lock, Session() as db:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(987654)")):
            return
        try:
            if config().demo_mode:
                return
            for domain in db.scalars(select(Domain).where(Domain.active.is_(True))):
                for group in preferences(db)["intervals"]:
                    job = db.scalar(
                        select(ScanJob).where(
                            ScanJob.domain_id == domain.id, ScanJob.group == group
                        )
                    )
                    if (
                        job
                        and job.state == "Pending"
                        and job.lease_until
                        and aware(job.lease_until) > now()
                    ):
                        scheduling.publish(db, job, monitor)
                        continue
                    job = scheduling.reserve(db, domain.id, group)
                    if job:
                        scheduling.publish(db, job, monitor)
            heartbeat = db.get(Setting, "scheduler_heartbeat")
            if heartbeat:
                heartbeat.value = {"at": now().isoformat()}
            else:
                db.add(
                    Setting(key="scheduler_heartbeat", value={"at": now().isoformat()})
                )
            db.commit()
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(987654)"))
            lock.commit()


@celery.task
def deliver_alerts():
    with engine.connect() as lock, Session() as db:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(987655)")):
            return
        try:
            if config().demo_mode:
                return
            for domain_id in db.scalars(
                select(Domain.id).where(Domain.active.is_(True))
            ):
                enqueue_digest(db, domain_id)
            db.commit()
            send_outbox(db)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(987655)"))
            lock.commit()
