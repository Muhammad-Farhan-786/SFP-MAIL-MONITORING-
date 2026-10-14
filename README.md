# NewHotMusic Email Health

A self-hosted email monitoring workspace for NewHotMusic.com. The responsive executive dashboard explains health, delivery, inbox placement, reputation, open issues, and verified fixes. Technical evidence is available through drill-downs. Unconfigured sources and unknown results stay visible; production never substitutes demo measurements.

## Automated monitoring upgrade

Public DNS and SMTP checks now default to five minutes. Persistent scan status, evidence-based diagnostics, grouped recurring/recovery email alerts, pause/resume controls, OAuth seed mailboxes, and signed delivery events are integrated into the existing dashboard. Both root routes and `/email-monitoring/` deployment paths work. See [upgrade/deployment instructions](docs/UPGRADE.md) for additive migration 002, exact operator commands, credential requirements, verification, and rollback. No live VPS deployment or automatic remediation is performed.

## Included

FastAPI + PostgreSQL, React + TypeScript, Celery + Redis, and Nginx deployed through Docker Compose. Authentication/DNS monitoring, inbound SMTP/TLS probes, signed delivery/bounce ingestion, authorized IMAP seed placement, modular reputation/DNSBL integrations, deduplicated issues and email alerts, configurable schedules, transparent scoring, historical charts, daily/weekly reports, audit logs, migrations, and backup/restore tooling.

```bash
cp .env.example .env
# Set database password/URL, JWT secret, Fernet key, and initial admin password.
# Configure HTTPS using your proxy or the supplied HTTPS template.
docker compose up -d --build
```

No real credentials are included. The first-start administrator uses ADMIN_EMAIL and ADMIN_PASSWORD. Unknown measurements remain unknown until monitoring runs and configured integrations provide evidence. See [Deployment](docs/DEPLOYMENT.md) before putting the dashboard on the Internet.

## Documentation

* [Architecture and extension points](docs/ARCHITECTURE.md)
* [Installation, configuration, updates, backup/restore, troubleshooting](docs/DEPLOYMENT.md)
* [SPF, DKIM, DMARC, SMTP, bounce ingestion, placement, reputation, alerts, and scoring](docs/EMAIL-MONITORING.md)
* [Security and operational boundaries](docs/SECURITY.md)
* [Validation evidence and remaining prerequisites](docs/VALIDATION.md)
* [API reference](docs/API.md)
* [Dependency license notices](LICENSE-NOTICES.md)

## Dashboard usage

Overview answers whether measured signals are healthy and shows score coverage. Authentication separates record validity from message authentication/alignment. Deliverability uses signed events from your sending platform. Inbox Placement shows authorized seed observations. Reputation only reflects configured sources. Issues explain business impact and recommended actions; a real verification retest is required before closure. Reports retain historical daily/weekly summaries and export to JSON. Monitoring History provides evidence and an activity timeline. Settings configures domain, selectors, sending IPs, seeds, thresholds, schedules, and team roles. System Status reports queue/worker/database/scheduler availability and alert delivery.

Place the permitted official logo in `frontend/public/branding/newhotmusic-logo.png`. The app automatically uses it on login and sidebar; absent assets use the company name as text. Website access was blocked during implementation, so the visual styling requires official brand review.

## Development and tests

Python 3.12+, Node 22.12+ (or Node 24), Docker Engine, Compose v2. Create a Python venv, install `backend/requirements.txt`, and `npm ci` in frontend. Backend tests use isolated SQLite for functional/unit tests; deployment validation uses PostgreSQL. Frontend tests run with Vitest; the type-checked production build is `npm run build`. No code generation or API keys are needed to run those tests.

This system is intended for infrastructure you control. Provider quotas/licenses, OAuth-only mailboxes, message-level SPF evaluation, DMARC aggregate ingestion, and production TLS/credentials require explicit operator configuration or the documented integration extensions. See validation for exactly what has been exercised.
