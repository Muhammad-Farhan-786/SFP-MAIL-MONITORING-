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
