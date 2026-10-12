# Architecture

A same-origin React/TypeScript application calls a FastAPI API behind Nginx. HTTP-only signed cookies authenticate users; write requests require the session's CSRF token. PostgreSQL is the system of record. Celery workers execute bounded monitoring jobs; Redis provides queues, task results, and login/run rate limits. One Celery beat service dispatches every minute, consulting configurable intervals in PostgreSQL.

The API and workers share an image but run independently, as non-root users. A one-shot migration/bootstrap container gates their startup. Database and Redis ports are not published. Persistent volumes retain database and queue state. Session advisory locks use a dedicated database connection to serialize a domain's monitoring group; dispatch uses its own lock. The default worker concurrency is two, preventing uncontrolled fan-out.

Models cover users, domains, sending IPs, monitoring checks, DNS results, authentication results, SMTP results, delivery events, bounces, encrypted seed mailboxes, placement tests, reputation results, blacklist results, issues, issue history, alerts, audit logs, reports, and settings. Evidence fields are PostgreSQL JSON columns, inside relational records, not file storage.

Issue fingerprints are unique per domain/category. Recurrence reopens the existing issue and clears verification. A failure updates last-seen/evidence and queues an alert when the cooldown allows. A healthy ordinary check does not automatically close an issue. Only worker-run verification can set Verified. The API enforces every workflow transition.

## Extension points

* DNS/SMTP/reputation adapters: `backend/app/monitoring.py` return state, human-readable summary, and evidence.
* Seed providers: `backend/app/mail.py`, registry `PROVIDERS`; implement `locate(seed, token)`.
* Alerts: the persisted outbox separates detection from SMTP delivery. Additional channel workers can consume channel-specific outbox rows.
* Authorized domain reputation adapter: `DOMAIN_REPUTATION_URL` HTTPS endpoint accepts `?domain=...` and returns `{"state":"Healthy|Warning|Critical|Unknown","summary":"...","metrics":{}}`. `DOMAIN_REPUTATION_KEY` is an optional bearer token. No service is scraped. Do not use arbitrary user-controlled endpoints.
* Delivery adapters normalize provider events to the signed ingestion contract; secrets are backend-only.

## Limits and operation

One beat instance is supported. Failed worker tasks are recorded by Celery; next scheduled dispatch retries monitoring. Ingestion uses globally unique event IDs. Rates are event-based, so adapters must emit one normalized terminal delivery event per recipient attempt when message-level rates are desired. Do not mix retry attempts and final delivery outcomes without deliberate normalization.

Retention is operator-managed; add an audited archival policy before high-volume operation. History requests cap at 10,000 checks and 100,000 events and return a truncation flag. SMTP checks probe up to five MX hosts, not arbitrary recipients. IMAP currently supports app-password authentication; OAuth-only tenants need an OAuth provider adapter. No claims are made about placement for non-seed recipients.
