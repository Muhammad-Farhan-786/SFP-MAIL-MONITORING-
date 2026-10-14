# Email monitoring

## Authentication

SPF checks locate exactly one `v=spf1` record, validate supported mechanism syntax and IP networks, follow includes/redirects, detect cycles, and count DNS mechanisms against the ten-lookup limit. Strict `-all` is healthy; soft/incomplete policy warns; unrestricted or conflicting records are critical. This is a configuration validator, not a full RFC 7208 message evaluator: macros and PTR require deeper review, and nested MX address/void-lookup expansion is not fully evaluated. Always verify proposed SPF changes with the sending provider. An example is `v=spf1 include:YOUR_PROVIDER -all`; never publish that placeholder.

DKIM selectors must come from your sender. The app does not guess them. Published RSA/Ed25519 public keys are decoded and validated; RSA under 1024 bits is critical and 1024-bit RSA warns. Use 2048-bit keys where supported. A published key is not proof that mail is being signed.

DMARC checks exactly one explicit `_dmarc.DOMAIN` policy, policy tags, enforcement percentage, and alignment mode. `p=none` or partial enforcement warns; full quarantine/reject is healthy. Organizational-domain policy inheritance and aggregate XML report ingestion are not implemented. Begin with monitored `p=none`, analyze legitimate senders, then move deliberately toward enforcement with provider guidance. Do not tighten policy blindly.

SPF and DKIM alignment cannot be measured from DNS alone. Signed delivery events may include `spf_pass`, `dkim_pass`, `spf_aligned`, and `dkim_aligned`; unknown values remain null. Authentication history is SPF-or-DKIM pass percentage across events with known authentication values. Alignment percentages have their own known-event denominators.

MX checks require usable records resolving only to public IPs. PTR checks configured sending IPs for forward-confirmed reverse DNS. SMTP opens a read-only EHLO session to up to five priority-ordered MX hosts. STARTTLS requires certificate/hostname verification. It does not send email, probe recipients, or verify your outbound relay. Cloud/VPS providers may block outbound TCP 25; failures require checking egress before attributing them to a remote server.

## Signed delivery and bounce ingestion

POST `/api/events/delivery` with exact UTF-8 JSON bytes. Headers:

* `X-Event-Timestamp`: current Unix seconds, within five minutes.
* `X-Event-Signature`: hex HMAC-SHA256 of `timestamp + "." + raw_body`, using `DELIVERY_WEBHOOK_SECRET`.

Example body (replace the timestamp):

```json
{"event_id":"provider-unique-event-id","domain":"newhotmusic.com","message_id":"provider-message-id","recipient_domain":"gmail.com","kind":"delivered","smtp_code":"250","occurred_at":"2026-10-06T12:00:00Z","spf_pass":true,"dkim_pass":true,"spf_aligned":true,"dkim_aligned":true}
```

Supported kinds: delivered, temporary_failure, permanent_failure, hard_bounce, soft_bounce, rejected. Never store full recipient addresses here. Retries with the same event ID are idempotent. Delivery rate = delivered/total events; bounce rate = (hard + soft bounce)/total; failure rate = all non-delivered/total. Last-24-hour thresholds create issues; historical dashboard ranges use received events in that range. There is no automatic ESP-specific webhook translation: configure an adapter in your sending system. Treat events as untrusted until signature verification succeeds.

## Placement

Configure an SMTP sender and authorized test mailboxes in Settings. Credentials are encrypted with Fernet; never returned through the API. Enable IMAP on the mailbox and configure the exact Inbox and Spam/Junk folders. Gmail commonly supports an app password with 2-step verification; Outlook organization policy may require the implemented OAuth2 adapter and approved tenant consent. The included IMAP adapter works where authorized password/app-password IMAP is supported.

The worker sends a unique controlled subject to each seed, waits 120 seconds, then searches folders read-only. A missing message remains Pending until the 900-second delivery window ends. Results are Inbox, Spam, Missing, or Unknown. Authentication/connection errors never become Inbox. Extend `PROVIDERS` to add OAuth or provider API support.

## Reputation and blocklists

AbuseIPDB requires a key and reports an IP abuse confidence indicator, not email-provider reputation. Confidence 0 is healthy, 1–49 warns, 50+ is critical. The domain adapter requires your authorized HTTPS provider endpoint. Sources without credentials stay Not Configured.

DNSBL sources are disabled by default. Supply only zones whose operator licenses your VPS/resolver usage and honors negative-response semantics. The generic adapter supports reversed IPv4 queries, treats provider error codes as Unknown, and stores source/target/results. DOMAIN_DNSBL_ZONES enables licensed domain-query sources using DOMAIN.ZONE A lookups. Each configured zone must support those exact semantics. The generic adapters do not implement proprietary access keys, IPv6 zones, or source-specific response interpretations. Add a source-specific adapter for those protocols; do not assume a generic zone can be queried safely without checking its contract. NXDOMAIN means not listed only for a correctly configured, authorized source.

## Score

Weights: SPF 12, DKIM 12, DMARC 12, MX 6, SMTP 8, TLS 8, Delivery 10, Bounce 8, Blacklist 8, IP reputation 5, Domain reputation 3, Placement 8 (plus PTR 4; sum 114). Healthy earns 100% weight; Warning 50%; Critical 0. Unknown/Not Configured/Never Checked are excluded from the measured denominator. Score = round(100 × earned / measured weight) − min(20, 5 × active unverified critical issues), clamped at zero. Without measured weight the score is null. Coverage always displays measured weight / 114; partial scores are labeled provisional. Measurements older than twice their schedule are stale and excluded. A provisional 100 is not complete health assurance.

Excellent defaults to 95+, Healthy 80+, Needs Attention 50+, Critical below 50. Thresholds are editable. Fix a signal, then complete the real retest workflow. Daily/weekly reports retain the snapshot, rates, new/resolved issues, and verified fixes. Email summaries require configured SMTP and alert recipients.


This release adds deferred/complaint events, sender scope, five-minute public scans, persisted diagnostic alert policies, and Gmail/Outlook OAuth2. See UPGRADE.md for the authoritative current configuration and provider adapter contract.
