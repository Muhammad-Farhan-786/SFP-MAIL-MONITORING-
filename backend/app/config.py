from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://emailhealth:emailhealth@db/emailhealth"
    redis_url: str = "redis://redis:6379/0"
    jwt_secret: str
    encryption_key: str
    admin_email: str = "admin@newhotmusic.com"
    admin_password: str = ""
    cookie_secure: bool = True
    domain: str = "newhotmusic.com"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    alert_recipients: str = ""
    alert_enabled: bool = True
    alert_reminder_seconds: int = 300
    auth_interval_seconds: int = 300
    smtp_interval_seconds: int = 300
    reputation_interval_seconds: int = 43200
    blacklist_interval_seconds: int = 43200
    placement_interval_seconds: int = 86400
    dashboard_url: str = "https://nhmdashboards.com/email-monitoring/"
    seed_smtp_host: str = ""
    seed_smtp_port: int = 587
    seed_smtp_user: str = ""
    seed_smtp_password: str = ""
    seed_smtp_from: str = ""
    seed_sending_source: str = (
        "Dedicated authorized seed SMTP; production equivalence not verified"
    )
    delivery_webhook_secret: str = ""
    abuseipdb_key: str = ""
    domain_reputation_url: str = ""
    domain_reputation_key: str = ""
    dnsbl_zones: str = ""
    domain_dnsbl_zones: str = ""
    demo_mode: bool = False
    seed_wait_seconds: int = 120
    seed_missing_after_seconds: int = 900

    def validate_secrets(self):
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters")
        from cryptography.fernet import Fernet

        Fernet(self.encryption_key.encode())


@lru_cache
def config():
    c = Config()
    c.validate_secrets()
    return c
