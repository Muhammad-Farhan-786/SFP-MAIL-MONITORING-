from datetime import datetime, timezone
from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    Float,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="admin")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Domain(Base):
    __tablename__ = "domains"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(253), unique=True)
    selectors: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SendingIP(Base):
    __tablename__ = "sending_ips"
    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id"))
    address: Mapped[str] = mapped_column(String(45), unique=True)


class Check(Base):
    __tablename__ = "monitoring_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id"), index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    state: Mapped[str] = mapped_column(String(30))
    summary: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, index=True
    )
    demo: Mapped[bool] = mapped_column(Boolean, default=False)


class DNSResult(Base):
    __tablename__ = "dns_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_checks.id"), unique=True
    )
    records: Mapped[dict] = mapped_column(JSON)


class AuthenticationResult(Base):
    __tablename__ = "authentication_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_checks.id"), unique=True
    )
    mechanism: Mapped[str] = mapped_column(String(20))
    alignment: Mapped[str] = mapped_column(String(30), default="Unknown")


class SMTPResult(Base):
    __tablename__ = "smtp_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_checks.id"), unique=True
    )
    hosts: Mapped[list] = mapped_column(JSON)


class DeliveryEvent(Base):
    __tablename__ = "delivery_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(200), unique=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id"), index=True)
    message_id: Mapped[str | None] = mapped_column(String(250))
    recipient_domain: Mapped[str] = mapped_column(String(253))
    kind: Mapped[str] = mapped_column(String(30))
    smtp_code: Mapped[str | None] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)
    spf_pass: Mapped[bool | None] = mapped_column(Boolean)
    dkim_pass: Mapped[bool | None] = mapped_column(Boolean)
    spf_aligned: Mapped[bool | None] = mapped_column(Boolean)
    dkim_aligned: Mapped[bool | None] = mapped_column(Boolean)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)


class Bounce(Base):
    __tablename__ = "bounces"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("delivery_events.id"), unique=True)
    kind: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)


class SeedMailbox(Base):
    __tablename__ = "seed_mailboxes"
    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id"))
    provider: Mapped[str] = mapped_column(String(40))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    imap_host: Mapped[str] = mapped_column(String(253))
    inbox_folder: Mapped[str] = mapped_column(String(100), default="INBOX")
    spam_folder: Mapped[str] = mapped_column(String(100), default="[Gmail]/Spam")
    encrypted_password: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class PlacementTest(Base):
    __tablename__ = "placement_tests"
    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id"))
    seed_id: Mapped[int] = mapped_column(ForeignKey("seed_mailboxes.id"))
    token: Mapped[str] = mapped_column(String(100), unique=True)
    state: Mapped[str] = mapped_column(String(30), default="Pending")
    detail: Mapped[str] = mapped_column(Text, default="Waiting for delivery")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReputationResult(Base):
    __tablename__ = "reputation_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_checks.id"), unique=True
    )
    source: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(253))
    value: Mapped[dict] = mapped_column(JSON)


class BlacklistResult(Base):
    __tablename__ = "blacklist_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("monitoring_checks.id"))
    source: Mapped[str] = mapped_column(String(253))
    target: Mapped[str] = mapped_column(String(253))
    state: Mapped[str] = mapped_column(String(30))
    evidence: Mapped[dict] = mapped_column(JSON)


class Issue(Base):
    __tablename__ = "issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id"))
    fingerprint: Mapped[str] = mapped_column(String(150), unique=True)
    title: Mapped[str] = mapped_column(String(250))
    category: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="Open")
    technical: Mapped[str] = mapped_column(Text)
    meaning: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    impact: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON)
    owner: Mapped[str | None] = mapped_column(String(254))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    verified_by: Mapped[str | None] = mapped_column(String(254))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retest_result: Mapped[str | None] = mapped_column(Text)


class IssueHistory(Base):
    __tablename__ = "issue_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"))
    status: Mapped[str] = mapped_column(String(30))
    actor: Mapped[str] = mapped_column(String(254))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    note: Mapped[str] = mapped_column(Text, default="")


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int | None] = mapped_column(ForeignKey("issues.id"))
    channel: Mapped[str] = mapped_column(String(30), default="email")
    state: Mapped[str] = mapped_column(String(30), default="Pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(254))
    action: Mapped[str] = mapped_column(String(100))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, index=True
    )


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("domain_id", "period", "period_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id"))
    period: Mapped[str] = mapped_column(String(20))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    content: Mapped[dict] = mapped_column(JSON)


class Setting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
