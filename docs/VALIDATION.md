# Validation evidence

Validated in the cloud development instance on 2026-10-06. This is current-instance evidence, not proof of deployment on the client's VPS or publication/restoration of a cloud snapshot.

| Check | Result |
|---|---|
| Python unit/API/workflow suite, isolated SQLite | 47 passed |
| Same backend suite, dedicated PostgreSQL test database | 47 passed |
| Frontend API/display unit tests | 3 passed |
| TypeScript check and Vite production build | Passed |
| Chromium desktop/mobile E2E | 2 passed; all navigation pages, login, score details, mobile navigation, no horizontal overflow |
| Browser runtime and console errors after login | None in the passing E2E run |
| Backend, migrate, worker, scheduler, frontend Docker builds | Passed using cloud proxy, resolved proxy host and supplied CA; verification retained |
| PostgreSQL migrations | Revision 001 applied; 19 application tables plus alembic_version |
| Migration/bootstrap repeatability | Repeated startup preserves existing admin and domain |
| API and dashboard through Nginx | Database health response and dashboard document verified |
| Backend container replacement | Proxy recovers without manual reload using dynamic Docker DNS |
| Worker/scheduler | Healthy; heartbeat persisted; scheduled groups and report tasks executed |
| Backup script | Custom-format PostgreSQL dump and SHA256 file created |
| Restore script | Passed on separate Compose project/volumes, preserving expected user/check counts and migration revision |
| Dependency audits | npm audit and pip-audit on the locked requirements reported zero known advisories at validation time |
| Frozen/hash-verified installation | Python --require-hashes and npm ci repeated successfully |

The backend suite exercises SPF strict/soft/conflicting records and include cycles; DKIM real RSA key validation and revoked keys; DMARC enforcement/policy/percentage; MX results; SMTP STARTTLS/non-TLS and network-unknown outcomes; private target and IMAP input rejection; score coverage/staleness; authentication, CSRF and role enforcement; signed delivery ingestion and idempotency; issue creation/deduplication/recurrence; verification before closure; failed retests; alert cooldown and outbox delivery; encrypted seed secret non-disclosure; and database-backed demo isolation. DNS/SMTP/IMAP/provider responses are controlled test fixtures where external services are unavailable. They are not live deliverability observations.

Backend tests emit a Starlette/httpx TestClient deprecation warning; tests execute and pass. Production uses the ordinary HTTPX provider client, not TestClient. No tests were counted as passed from a zero-test run.

## External prerequisites still needed

* The cloud's native DNS resolver did not complete live domain queries. SPF/DMARC/MX and dependent SMTP live outcomes remain Unknown. Verify outbound DNS and TCP 25 on the VPS; do not interpret these cloud unknowns as a broken domain.
* No DKIM selectors, authorized seed accounts, SMTP sender/alert credentials, reputation API keys, licensed blocklist sources, or real delivery stream were supplied. Controlled tests validate logic; live checks and email receipt require those inputs.
* Outlook tenants requiring OAuth need a provider-specific OAuth adapter; the included adapter supports permitted IMAP app/password authentication.
* Official website access was denied by cloud egress. The text fallback is implemented; permitted official logo and visual identity review remain required. The cloud draft adds newhotmusic.com and www.newhotmusic.com for future review; saving the draft does not apply network changes to this instance.
* Production hostname/certificates and HTTPS were not supplied. The HTTPS-ready template is included but a valid public TLS deployment has not been verified.

Do not call this instance a fully configured production email monitoring service until these external operations are configured and verified. No fake data are presented as real monitoring measurements.

## Upgrade validation — 2026-10-14

This release was validated in the existing cloud development environment; **no live VPS was deployed or restarted**. Additive Alembic revision 002 applied successfully over revision 001. All 22,833 monitoring records present when local workers were paused and the existing user remained after migration. PostgreSQL and Redis volumes were retained; the local database was backed up first.

The current checkout suite includes the original tests and new coverage for five-minute schedule defaults, persistent leases, redelivery/expiry, broker failures, diagnostic guidance/evidence, grouped reminders at 300 seconds, deduplication, critical-only policies, pause/disable/resume suppression, recovery notices, preserved closure verification, bounded SMTP retries, partial SMTP acceptance, fresh policy reads across sessions, missing/stale measurements, Outlook OAuth requirements, token refresh/encryption, disabled seed accounts, webhook replay/conflicts/new event kinds, provider event normalization, malformed signature-header rejection, and newest-sample history caps.

* Backend: 72 tests executed on isolated SQLite and on a dedicated PostgreSQL `*_tests` database; all passed, no skips. Tests reset only the disposable test schema, never the application database.
* Frontend: 7 unit tests passed, including alert controls/recipient editing and prefixed API requests; TypeScript and Vite production build passed.
* Chromium: 2 desktop/mobile tests passed at root and the same 2 passed at `/email-monitoring/`; navigation/login/score details/console and overflow checks passed.
* All application Docker images built using the supplied verified cloud proxy/CA. Compose configuration validation and app Nginx syntax validation passed.
* Worker ping and scheduler heartbeat passed. Persisted real job metadata shows auth/SMTP/delivery reservations at 300 seconds, reputation/blacklist at 43200 seconds, placement/reports at 86400 seconds. Native DNS reachability remains inconclusive in this cloud; the UI records Degraded/Unknown instead of healthy claims.
* Signed delivery/OAuth/SMTP/IMAP tests use controlled fixtures. No live notification relay, production provider event stream, OAuth account, or seed inbox receipt was configured or claimed as verified. The existing Starlette TestClient deprecation warning remains non-failing.

See [UPGRADE.md](UPGRADE.md) for exact migration/rebuild/restart/verification/rollback commands, required SMTP/OAuth/provider configuration, and the boundary between a notification-relay test and production-sender placement. Database histories and suppression records remain auditable. SMTP acceptance is not proof of recipient inbox delivery; exactly-once SMTP across process/network failures requires receiver cooperation.
