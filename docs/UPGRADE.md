# Five-minute monitoring upgrade

This release upgrades the existing service and PostgreSQL data in place. It does not change DNS records, modify a mail server, remediate automatically, access the production sender, or manage Wazuh/Apache/other VPS services. Deployment requires an authorized operator; the development task does not deploy to the live VPS.

## Changes and operator settings

Public authentication/DNS and inbound SMTP/STARTTLS scans default to 300 seconds. Connected delivery telemetry is evaluated every 300 seconds. Reputation/blocklist defaults remain 12 hours and seed tests daily to respect provider quotas and test volume. The database Settings page is authoritative after preferences are saved. Environment interval values initialize defaults; retain provider-safe intervals. Add actual DKIM selector names and sending IPs obtained from the production owner—there is no reliable public enumeration of all DKIM selectors.

Revision 002 adds `scan_jobs`, diagnostic issue fields, OAuth metadata, sender scope, payload fingerprints, and alert outbox metadata without replacing or deleting history. It changes saved **legacy default** auth=21600/smtp=3600 values to 300; custom intervals are retained. The scheduler reserves a durable task token, uses per-category execution locks, ignores duplicate/redelivered tokens, bounds lost-task leases, and avoids catch-up bursts. Dispatcher ticks every 30 seconds; actual job timestamps/duration/next due are displayed in Overview. Completed means the scan executed; domain health remains a separate measurement. Inconclusive scans are Degraded, not successful health evidence.

## Notification configuration

Configure a separate notification relay with `SMTP_HOST`, `SMTP_PORT` (587 STARTTLS or 465 TLS), `SMTP_USER`, `SMTP_PASSWORD`, and `SMTP_FROM`. Credentials remain backend environment values. `ALERT_RECIPIENTS` supplies comma-separated initial defaults. In Settings → Email alert settings, save recipients, enabled/paused state, reminder interval (minimum/default 300 seconds), and critical-only filtering. All controls persist in PostgreSQL. Configure `DASHBOARD_URL=https://nhmdashboards.com/email-monitoring/` or your verified deployment URL.

The outbox groups findings into one domain diagnostic digest per reminder cycle. Missing/stale data and actual evidence are labeled; it never guesses exact SPF/DKIM values. First notification is picked up on a worker alert tick (normally within 30 seconds). Reminders follow the saved interval after delivery; pending failures do not create a new digest each cycle. Actual healthy recovery stops that category's problem description and groups recovery observations into a recovery notice. Ordinary recovery does not bypass the issue-verification/closure workflow.

Disable/Pause suppresses pending automatic messages with a stored reason; monitoring continues. An explicitly requested **Send test email** is allowed while automatic alerts are disabled/paused. Test messages are labeled tests and are not measurements. Daily/weekly summary emails use the same outbox/policy. Legacy unsent individual issue alerts are preserved with a suppression reason and replaced by grouped diagnostics; previously sent history is retained.

SMTP errors store exception types, not credential-bearing messages. Partial recipient acceptance is retained as Partial and is not retried for the full recipient list within that cycle, preventing duplicate mail to accepted recipients. Retries back off at 60/120/240/300 seconds, stop after five failed attempts, and defer new diagnostic digests for 30 minutes after exhaustion. Missing sender/recipients is Not Configured, not Sent. Status Sent means SMTP accepted the message, not verified recipient inbox delivery. Queue deduplication, row/advisory locks and stable Message-ID prevent ordinary duplicate cycles. SMTP does not provide transactional exactly-once delivery: a process/network failure after remote acceptance but before local acknowledgement can cause uncertainty; receiver-side Message-ID deduplication is recommended. Do not interpret retry status as verified receipt.

## Delivery providers

`POST /email-monitoring/api/events/delivery` (root `/api/events/delivery` also works) accepts HMAC-signed normalized events. Existing signatures/timestamp window remain enforced. Unique event IDs are idempotent; reusing an ID with a changed signed payload is rejected. Kinds include delivered, deferred, temporary_failure, permanent_failure, rejected, hard_bounce, soft_bounce and complaint. Complaint/deferred counts are separate signals; event rates describe received events, not guaranteed inbox placement. No events means Not Measured, not zero failures or 100% delivery.

`integrations/delivery_forwarder.py` provides working Postmark and SendGrid normalizers/forwarding. Native provider payloads must first be authenticated by your authorized receiver (Postmark configured webhook HTTP credentials, or SendGrid signed Event Webhook verification). The helper does **not** replace that native verification and is not an unauthenticated public receiver. After native verification, forward through the helper or import `normalize()` in your authorized event adapter:

```bash
# Run in a trusted receiver environment with DELIVERY_WEBHOOK_SECRET injected securely.
python integrations/delivery_forwarder.py --provider postmark --domain newhotmusic.com \
  --input /secure/path/authenticated-event.json \
  --url https://nhmdashboards.com/email-monitoring/api/events/delivery
```

SendGrid batches are supported. Postmark Delivery/Bounce/SpamComplaint and SendGrid delivered/deferred/bounce/dropped/spamreport are mapped. Open/click events are deliberately not delivery outcomes. Review event semantics with the provider; normalize retry/final-outcome streams consistently. Use provider globally unique IDs and real timestamps. Full recipient addresses are reduced to recipient domains before ingestion.

## Seed mailboxes and OAuth

Gmail supports approved OAuth2 or an authorized app password where enabled. Outlook requires OAuth2; legacy password-mode Outlook seeds return Unknown until upgraded. Obtain consent/client configuration from the mailbox owner/tenant administrator. For Gmail authorize the documented IMAP/mail scope; for Outlook authorize delegated `https://outlook.office.com/IMAP.AccessAsUser.All` and `offline_access`. Supply client ID, authorized refresh token, tenant (common/organizations/tenant UUID), and client secret where your application type requires it through the protected Settings form over HTTPS. Secrets are Fernet-encrypted; APIs return only authentication mode, never credentials. Refresh-token rotation is retained. Ensure egress to oauth2.googleapis.com/login.microsoftonline.com and authorized IMAP hosts on TLS port 993. The app never assumes consent or invents a token.

Use `SEED_SMTP_*` for a separately authorized test sender if available. When blank, the notification SMTP relay is used and the UI explicitly says this does **not** test production sending infrastructure. `SEED_SENDING_SOURCE` labels the authorized sender; it is a declaration, not proof of production equivalence. Confirm relay/domain/signing behavior with the production provider before claiming a production placement test. Seed outcomes are actual folder observations: Inbox, Spam, Missing after the delivery window, or Unknown on errors.

## Authorized VPS deployment

From the existing application checkout only (leave Apache/Wazuh/other services unchanged):

```bash
# Capture the currently running release for rollback before pulling.
git rev-parse HEAD
scripts/backup.sh
# Retain .env and its encryption key securely. Add new optional settings to your existing .env.
git pull --ff-only
# Validate before starting new services.
docker compose config --quiet
docker compose build
docker compose stop worker scheduler
docker compose run --rm migrate
# This applies additive revision 002; do not reset volumes or the database.
docker compose up -d backend worker scheduler frontend nginx
# If an existing Nginx container retains its loaded configuration, reload this app's Nginx only.
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload
docker compose ps
docker compose logs --since=5m --tail=100 migrate backend worker scheduler nginx
```

Verify using your configured HTTPS URL and credentials:

```bash
curl --fail https://nhmdashboards.com/email-monitoring/api/health
curl --fail https://nhmdashboards.com/email-monitoring/openapi.json -o /tmp/email-health-openapi.json
docker compose exec backend alembic current
docker compose exec scheduler python -m app.scheduler_health
docker compose exec worker celery -A app.worker.celery inspect ping --timeout=5
```

Sign in at `/email-monitoring/`, confirm coverage/source status, next scan and actual scan duration, inspect diagnostics, save recipients, send a test email, and verify SMTP status **and actual receipt**. Test pause/resume and observe suppression history. Configure the production provider's authenticated telemetry adapter and approved seeds; do not treat controlled unit fixtures as live-provider proof. Root routes still work. The shipped Nginx configuration handles the app prefix without requiring changes to the separate Apache reverse proxy.

## Rollback

Retain the backup checksum and encryption key. Stop this app's worker/scheduler before rollback. Revision 002 is additive: the previous code can normally run against it while the new columns remain, preserving new data; rebuild/restart the captured previous Git commit and reload only this app's Nginx as needed. Prefer forward correction over dropping columns. A schema downgrade removes new diagnostic/outbox metadata and must only be considered after a fresh backup during maintenance. For full restoration, restore the verified pre-upgrade dump in an isolated instance first, verify counts/login, then follow the documented explicit database restore procedure. Never use `docker compose down -v`, database resets, or force-push as an upgrade/rollback shortcut.

## Troubleshooting

A stale heartbeat indicates scheduler/worker/broker trouble, not proof that email infrastructure failed. Unknown DNS/SMTP means resolver/egress/certificate/connectivity must be investigated from the monitoring VPS. A completed check can still find Critical signals. Pending scan leases prevent overlap; expired leases are safely rescheduled with a new token. A paused/disabled notification has a suppression reason, not a deleted record. Retry errors never print raw SMTP/OAuth secrets. IMAP OAuth errors require provider consent/scope/client checks. Reputation APIs and DNSBL queries require credentials, licenses, and quota appropriate to the configured interval.
