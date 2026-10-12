import ipaddress, re
from datetime import datetime, timezone, timedelta
from typing import Literal
from pydantic import BaseModel, EmailStr, Field, field_validator


def hostname(value):
    value = value.lower().strip().rstrip(".")
    if (
        len(value) > 253
        or "." not in value
        or not all(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", s)
            for s in value.split(".")
        )
    ):
        raise ValueError("Enter a public DNS hostname")
    try:
        ipaddress.ip_address(value)
        raise ValueError("Use a hostname, not an IP")
    except ValueError as exc:
        if str(exc) == "Use a hostname, not an IP":
            raise
    if value.endswith((".local", ".internal", ".localhost", ".test", ".invalid")):
        raise ValueError("Public domains only")
    return value


class Login(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=512)


class DomainInput(BaseModel):
    name: str
    selectors: list[str] = Field(default_factory=list, max_length=20)
    sending_ips: list[str] = Field(default_factory=list, max_length=20)
    _host = field_validator("name")(hostname)

    @field_validator("selectors")
    @classmethod
    def selector(cls, values):
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,63}", v) for v in values):
            raise ValueError("Invalid selector")
        return list(dict.fromkeys(values))

    @field_validator("sending_ips")
    @classmethod
    def ips(cls, values):
        if any(not ipaddress.ip_address(v).is_global for v in values):
            raise ValueError("Only public sending IPs are allowed")
        return list(dict.fromkeys(values))


class SettingsInput(BaseModel):
    intervals: dict[str, int]
    bounce_threshold: float = Field(ge=0.1, le=100)
    failure_threshold: float = Field(ge=0.1, le=100)
    alert_cooldown: int = Field(ge=300, le=86400 * 7)
    health_healthy: int = Field(ge=50, le=95)
    health_excellent: int = Field(ge=80, le=100)

    @field_validator("intervals")
    @classmethod
    def intervals_valid(cls, values):
        expected = {"auth", "smtp", "reputation", "blacklist", "placement", "reports"}
        if set(values) != expected or any(
            not 300 <= v <= 86400 * 30 for v in values.values()
        ):
            raise ValueError("Provide all schedule groups, from 300 to 2592000 seconds")
        return values


class SeedInput(BaseModel):
    provider: Literal["Gmail", "Outlook", "IMAP"]
    email: EmailStr
    imap_host: str
    inbox_folder: str = Field(default="INBOX", max_length=100, pattern=r'^[^\r\n"]+$')
    spam_folder: str = Field(max_length=100, pattern=r'^[^\r\n"]+$')
    password: str = Field(min_length=1, max_length=512)
    _host = field_validator("imap_host")(hostname)


class IssueUpdate(BaseModel):
    status: Literal["Assigned", "Fixing", "Ready for Retest", "Retesting", "Closed"]
    owner: EmailStr | None = None


class DeliveryInput(BaseModel):
    event_id: str = Field(min_length=1, max_length=200)
    domain: str
    message_id: str | None = Field(default=None, max_length=250)
    recipient_domain: str
    kind: Literal[
        "delivered",
        "temporary_failure",
        "permanent_failure",
        "hard_bounce",
        "soft_bounce",
        "rejected",
    ]
    smtp_code: str | None = Field(default=None, max_length=20, pattern=r"^[0-9. ]+$")
    reason: str | None = Field(default=None, max_length=2000)
    spf_pass: bool | None = None
    dkim_pass: bool | None = None
    spf_aligned: bool | None = None
    dkim_aligned: bool | None = None
    occurred_at: datetime
    _domain = field_validator("domain", "recipient_domain")(hostname)

    @field_validator("occurred_at")
    @classmethod
    def date_valid(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timestamp must include timezone")
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("Timestamp cannot be in the future")
        return value


class UserInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=512)
    role: Literal["admin", "viewer"] = "viewer"
