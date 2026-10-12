import json, logging
from datetime import timedelta
from celery import Celery
from sqlalchemy import select, text
from .config import config
from .db import Session, engine
from .models import *
from .services import *
from . import mail

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
        "dispatch": {"task": "app.worker.dispatch", "schedule": 60.0},
        "alerts": {"task": "app.worker.deliver_alerts", "schedule": 60.0},
    },
)


@celery.task
def monitor(domain_id, group):
    with engine.connect() as lock, Session() as db:
        if not lock.scalar(
            text("SELECT pg_try_advisory_lock(:key)"),
            {"key": domain_id * 100 + list(INTERVALS).index(group)},
        ):
            return
        try:
            if config().demo_mode:
                return
            domain = db.get(Domain, domain_id)
            if not domain or not domain.active:
                return
            if group == "placement":
                for ident in mail.start_placement(db, domain_id):
                    collect_placement.apply_async(
                        args=[ident], countdown=config().seed_wait_seconds
                    )
            elif group == "reports":
                generate_reports(db, domain)
            else:
                execute_group(db, domain, group)
            logger.info(
                json.dumps(
                    {
                        "event": "monitor_complete",
                        "domain_id": domain_id,
                        "group": group,
                    }
                )
            )
        finally:
            lock.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": domain_id * 100 + list(INTERVALS).index(group)},
            )
            db.commit()


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
    with Session() as db:
        issue = db.scalar(select(Issue).where(Issue.id == issue_id).with_for_update())
        if not issue or issue.status != "Retesting":
            return
        domain = db.get(Domain, issue.domain_id)
        group = CATEGORY_GROUP.get(issue.category)
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
            "Unknown"
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
                "summary": "No delivery events received."
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
        recipients = [
            a.strip() for a in config().alert_recipients.split(",") if a.strip()
        ]
        try:
            mail.send(
                f"NewHotMusic {period} email health summary",
                f"Health: {content['state']}\nScore: {content['score']}\nCoverage: {content['coverage']}%\n{content['summary']}\nOpen issues: {content['issues']['open']}\nDelivery: {content['delivery']}",
                recipients,
            )
        except Exception:
            logger.warning(
                json.dumps({"event": "summary_email_failed", "period": period})
            )


@celery.task
def dispatch():
    with engine.connect() as lock, Session() as db:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(987654)")):
            return
        try:
            if config().demo_mode:
                return
            cfg = preferences(db)
            for domain in db.scalars(select(Domain).where(Domain.active.is_(True))):
                for group, interval in cfg["intervals"].items():
                    key = f"last_dispatch:{domain.id}:{group}"
                    stamp = db.get(Setting, key)
                    if (
                        not stamp
                        or (
                            now() - datetime.fromisoformat(stamp.value["at"])
                        ).total_seconds()
                        >= interval
                    ):
                        monitor.delay(domain.id, group)
                        if stamp:
                            stamp.value = {"at": now().isoformat()}
                        else:
                            db.add(Setting(key=key, value={"at": now().isoformat()}))
                evaluate_delivery(db, domain.id)
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
    with Session() as db:
        for alert in db.scalars(
            select(Alert)
            .where(Alert.state.in_(["Pending", "Not Configured", "Retrying"]))
            .order_by(Alert.id)
            .with_for_update(skip_locked=True)
            .limit(50)
        ):
            issue = db.get(Issue, alert.issue_id)
            if not issue or issue.status in ("Closed", "Verified"):
                alert.state = "Cancelled"
                continue
            if alert.attempts >= 5:
                alert.state = "Failed"
                continue
            alert.attempts += 1
            try:
                sent = mail.send(
                    f"NewHotMusic: {issue.title}",
                    f"{issue.meaning}\n\n{issue.technical}\n\nRecommended action: {issue.action}",
                    [
                        x.strip()
                        for x in config().alert_recipients.split(",")
                        if x.strip()
                    ],
                )
                alert.state = "Sent" if sent else "Not Configured"
                if sent:
                    alert.sent_at = now()
                else:
                    alert.attempts -= 1
            except Exception as exc:
                alert.state = "Retrying"
                alert.error = type(exc).__name__
            audit(db, "worker", "Alert delivery", alert_id=alert.id, state=alert.state)
        db.commit()
