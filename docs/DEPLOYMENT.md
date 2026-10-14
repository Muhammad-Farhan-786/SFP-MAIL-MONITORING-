# Ubuntu VPS deployment

Install Docker Engine and the Compose plugin from the official Docker repository. Point a dashboard hostname (for example email-health.your-domain) to the VPS. Permit HTTPS inbound and needed outbound DNS, SMTP 25/587/465, IMAP 993, and authorized API HTTPS destinations. Keep PostgreSQL/Redis private. Provide enough resources for PostgreSQL and two Celery processes; 2 vCPU / 4 GB RAM is a sensible starting point, adjusted to traffic.

```bash
cp .env.example .env
chmod 600 .env
# Edit with independently generated secrets and your sender settings.
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 migrate backend worker scheduler nginx
```

Set POSTGRES_PASSWORD and a matching URL-encoded password in DATABASE_URL; set JWT_SECRET (at least 32 random characters), ENCRYPTION_KEY, and initial ADMIN_PASSWORD (at least 12 characters). Generate a Fernet key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` in a trusted local terminal with cryptography installed. Initial bootstrap creates one admin and the configured domain; subsequent restarts preserve passwords and data.

## HTTPS

Put the included proxy behind your existing HTTPS reverse proxy, or use `nginx/https.conf.example`, replace the hostname, mount your valid fullchain/key under `/etc/nginx/certs:ro`, and publish `443:443`. Mount the HTTPS configuration as default.conf. Arrange certificate renewal externally and reload Nginx after renewal. COOKIE_SECURE=true is required for production. Without HTTPS, secure-cookie login will not persist; do not globally disable Secure to work around a missing production certificate.

## First use

Sign in with ADMIN_EMAIL and your initial password. Add DKIM selectors, public sending IPs, schedules, and seed mailboxes in Settings. Set SMTP_HOST/PORT/USER/PASSWORD/FROM and ALERT_RECIPIENTS on the backend environment; restart backend/worker/scheduler after changes. Configure the signed delivery adapter in your sending infrastructure. Add authorized AbuseIPDB/domain reputation/DNSBL integrations if desired. Run each monitoring group and inspect System Status. Unknown or Not Configured signals are expected until sources and connectivity work.

Store a permitted unmodified official logo as `frontend/public/branding/newhotmusic-logo.png` and rebuild frontend. This repository contains a text fallback; no fake company logo is supplied. The original site's visual identity could not be inspected because cloud egress denied access, so have the brand owner review provisional colors/typography.

## Backup and restore

Run `scripts/backup.sh` from the host; it writes a custom-format pg_dump and SHA256 checksum with restrictive permissions. Separately encrypt/back up `.env` and branding assets with your organization's secure backup tool. The database's encrypted mailbox secrets require the same ENCRYPTION_KEY to restore.

Test restoration on an isolated Compose project with different HTTP_PORT and volume names; do not test by deleting the production database. Copy the dump/checksum into that checkout's backups directory. Run `scripts/restore.sh backups/FILE.dump --confirm-replace`. This stops app writers, verifies the checksum, restores with --exit-on-error, applies migrations, and restarts services. If restore fails, writers remain stopped: investigate before restarting. Verify login, domain/check/issue counts, and seed decryption. Always make a fresh backup before replacing any database.

## Updates and troubleshooting

Back up first. Review release notes/migrations, build images, then `docker compose up -d --build`; startup gates on migration success. Pin tested image digests in your own release pipeline. Use `docker compose logs --tail=100 SERVICE` without dumping environments. If auth fails, verify HTTPS/Secure cookie and Redis availability. If workers are idle, inspect beat heartbeat and broker connectivity. If DNS fails, check resolver UDP/TCP 53. If SMTP fails, check VPS outbound port restrictions and remote certificate verification. If mailboxes return Unknown, verify provider authentication policy and folder names. If a reputation source returns errors, verify quota, licensing, and API credentials; never disable TLS checks.

## Local development

Create a venv, install backend requirements, and run `python scripts/dev-env.py` once. This creates ignored random development secrets, preserves existing configuration, chooses HTTP_PORT=8088, and disables secure cookies for local HTTP only. Use Docker Compose for PostgreSQL/Redis/API/workers/proxy. To work on the UI, `cd frontend && npm ci && npm run dev`; Vite proxies /api to a backend on port 8000, so run backend locally or explicitly bind backend to loopback in a development override. Never publish a development API binding on all interfaces.

Run `cd backend && python -m pytest -q` and `cd frontend && npm test && npm run build`. Browser E2E instructions and actual executed validation appear in VALIDATION.md. Each cloud task is already isolated; use the existing checkout and do not create a Git worktree unless requested.

## Optional demo environment

Use a fresh disposable Compose project/database, set DEMO_MODE=true before starting any worker, run migrations/bootstrap, then `docker compose run --rm backend python -m app.demo --confirm-demo-data`. The command refuses databases containing genuine checks/events and is idempotent by refusing duplicate sample insertion. In demo mode automatic monitoring dispatch is paused, queries select only flagged database demo records, and the dashboard displays a DEMO DATA banner. Production mode selects only genuine records. Never use a demo configuration for client monitoring, and never claim the illustrative seed data are observations.

To reset an administrator password from an interactive trusted VPS terminal, run `docker compose exec backend python -m app.password`. The helper prompts without echoing the password. Rotate JWT_SECRET/restart services if immediate session invalidation is required.

For PostgreSQL integration tests, create a dedicated database named `emailhealth_tests` with the test application's database role and set TEST_DATABASE_URL to that database while running pytest. The fixture rejects database names without the `_tests` suffix and resets the test schema between cases. Never point this fixture at a live application database.


For this release use [the in-place five-minute upgrade guide](UPGRADE.md). It supersedes earlier default auth/SMTP schedules and the earlier Outlook app-password limitation: Outlook now requires the implemented OAuth2 adapter. Notification policy is persisted per domain in the dashboard. Existing root URLs remain supported alongside /email-monitoring/.
