# API reference

The machine-readable OpenAPI 3.1 reference is available at `/openapi.json` through Nginx. All application data endpoints require a valid session except health checks and signed event ingestion. The schema contains no credential values. FastAPI's internal Swagger UI uses external assets and is not exposed by the production proxy; import the schema into your preferred local API documentation/client tool.

| Endpoint | Purpose | Access |
|---|---|---|
| POST /api/auth/login | Set HttpOnly session and CSRF cookies | Rate-limited login |
| GET /api/auth/me, POST /api/auth/logout | Current user / end session | Signed-in user |
| GET /api/domains | List monitored domains | Signed-in user |
| POST /api/domains, PUT /api/domains/{id} | Domain, selectors, sending IPs | Administrator + CSRF |
| GET /api/overview/{id}?days=7 | Score, coverage, signals, metrics, placements | Signed-in user |
| GET /api/history/{id}?days=7 | Database-backed charts and check evidence | Signed-in user |
| POST /api/monitor/{id}/{group} | Queue auth/smtp/reputation/blacklist/placement/reports | Administrator + CSRF |
| GET /api/issues/{domain_id} | Issue list | Signed-in user |
| GET /api/issue/{id}/history | Workflow timeline | Signed-in user |
| PATCH /api/issue/{id} | Enforced status transition and owner | Administrator + CSRF |
| GET /api/reports/{domain_id} | Daily/weekly retained report snapshots | Signed-in user |
| GET /api/activity, GET /api/system | Audit activity / component status | Signed-in user |
| GET /api/settings/{domain_id}, PUT /api/settings | Configuration metadata and monitoring preferences | Administrator; writes require CSRF |
| POST /api/seeds/{domain_id}, DELETE /api/seeds/{id} | Authorized encrypted mailbox / disable | Administrator + CSRF |
| POST /api/users | Create administrator/viewer | Administrator + CSRF |
| POST /api/events/delivery | Normalized delivery and bounce event | HMAC signature; see EMAIL-MONITORING.md |
| GET /api/health | Database connectivity health | Public, no sensitive configuration |

For writes after login, echo the readable `csrf` cookie into `X-CSRF-Token`; the server binds it to the signed HttpOnly session. Never send session or API secrets through URLs. History ranges accept 1, 7, 30, or 90 days. The schema supplies field-level constraints and request/response details. Provider/SMTP credentials are environment-only; encrypted seed credentials are accepted once and never returned.


Upgrade endpoints: GET `/api/alerts/{domain_id}` returns delivery history (administrator settings only); PUT `/api/alerts/{domain_id}/settings` persists enable/pause/recipients/reminder/critical-only policy; POST `/api/alerts/{domain_id}/test` queues an explicitly requested notification test. Writes require admin + CSRF. All endpoints also work behind `/email-monitoring/`. Overview includes `scans`, measurement `availability`, and score `reduction` per factor. Seed creation accepts protected OAuth fields, never returns credential values, and rejects Outlook basic authentication.
