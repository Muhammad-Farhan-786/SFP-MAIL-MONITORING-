"""Database leases reserve one task per domain/group; task tokens make redelivery harmless."""

import uuid
from datetime import timedelta
from sqlalchemy import select, update
from .models import ScanJob, now
from .db import insert_once
from .services import aware, preferences, serialize

BUSY = ("Pending", "Queued", "Running", "Waiting")


def reserve(db, domain_id, group, manual=False):
    prefs = preferences(db)
    if group not in prefs["intervals"]:
        raise ValueError("Unknown monitoring group")
    insert_once(
        db,
        ScanJob,
        {"domain_id": domain_id, "group": group, "state": "Never Checked"},
        ["domain_id", "group"],
    )
    job = db.scalar(
        select(ScanJob)
        .where(ScanJob.domain_id == domain_id, ScanJob.group == group)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    moment = now()
    if job.state in BUSY and job.lease_until and aware(job.lease_until) > moment:
        return None
    if not manual and job.next_due_at and aware(job.next_due_at) > moment:
        return None
    if job.state in BUSY:
        job.error = "Previous task lease expired; bounded rescheduling"
    job.task_id = uuid.uuid4().hex
    job.state = "Pending"
    job.queued_at = moment
    job.started_at = None
    job.finished_at = None
    job.lease_until = moment + timedelta(seconds=600)
    job.next_due_at = moment + timedelta(seconds=prefs["intervals"][group])
    db.flush()
    return job


def publish(db, job, task):
    token = job.task_id
    db.commit()  # Durable reservation before publishing.
    try:
        task.apply_async(
            args=[job.domain_id, job.group, token],
            task_id=token,
            expires=600,
            retry=False,
        )
        db.execute(
            update(ScanJob)
            .where(
                ScanJob.id == job.id,
                ScanJob.task_id == token,
                ScanJob.state == "Pending",
            )
            .values(state="Queued")
        )
        db.commit()
    except Exception as exc:
        # Retry this token on a later dispatcher tick, not a second scan reservation.
        db.rollback()
        job = db.get(ScanJob, job.id)
        job.error = type(exc).__name__
        db.commit()
    return token


def start(db, domain_id, group, token):
    job = db.scalar(
        select(ScanJob)
        .where(ScanJob.domain_id == domain_id, ScanJob.group == group)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not job or job.task_id != token or job.state not in ("Queued", "Pending"):
        return None
    if job.lease_until and aware(job.lease_until) < now():
        return None
    job.state = "Running"
    job.started_at = now()
    job.lease_until = now() + timedelta(seconds=480)
    job.error = None
    db.commit()
    return job


def finish(db, job, state="Completed", error=None):
    job.finished_at = now()
    job.state = state
    job.error = error
    job.duration_seconds = round(
        (now() - aware(job.started_at or job.queued_at)).total_seconds(), 3
    )
    if state == "Completed":
        job.last_success_at = now()
    job.lease_until = None
    # Never catch up with a burst after long-running or slow provider checks.
    if not job.next_due_at or aware(job.next_due_at) <= now():
        job.next_due_at = now() + timedelta(
            seconds=preferences(db)["intervals"][job.group]
        )
    db.commit()
