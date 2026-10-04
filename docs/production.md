# Production configuration and release rehearsal

Status: local implementation; no public hosting configured or verified. The full SaaS acceptance gates are maintained in the workspace assessment document. Passing these configuration tests alone does not authorize or prove a public release.

## Environment

Use Linux with a production WSGI server, PostgreSQL over TLS and authenticated SMTP with STARTTLS. Install `requirements-production.txt` in a separate environment. Pins were checked against [Psycopg PyPI](https://pypi.org/project/psycopg/) and [Gunicorn PyPI](https://pypi.org/project/gunicorn/) on 2026-10-04; installation, dependency vulnerability review and staging integration remain required.

Inject settings from `deploy/production.env.example` through the host's secret manager. Do not copy credentials into source control, browser code, screenshots, logs or command arguments. Generate a fresh random secret; placeholders intentionally fail startup. Production ignores the development `.env`; ordinary development `.env` values now only fill environment variables which are not already set.

Configure explicit domains and matching HTTPS CSRF origins. Provision three absolute storage roots with application write permissions: collected static assets, public avatars and private evidence. The edge serves static and avatars as non-executable content; it must never expose private evidence. Evidence continues through authenticated Django routes. Storage must persist across releases and be backed up.

TLS must terminate at a trusted edge. Set `ROOMORA_TRUST_PROXY_PROTO=1` only if it replaces inbound forwarded-proto headers and the application port is not accessible directly from the Internet. Otherwise terminate TLS directly. HSTS initially uses one hour, without subdomain/preload expansion; increase only after verifying the domain deployment.

## Rehearsal commands

With actual environment values injected and `DJANGO_SETTINGS_MODULE=config.production_settings`:

```sh
python -m pip install -r requirements-production.txt
python manage.py check --deploy --fail-level ERROR
python manage.py migrate --plan
python manage.py collectstatic --noinput
```

Back up and verify restore before applying migrations to a populated database. Apply migrations in a controlled release job after reviewing the plan, then start the app on a private bind address:

Review deployment warnings individually. W005/W021 are expected while HSTS include-subdomains/preload remain deliberately disabled; do not ignore other warnings or enable preload before domain-wide TLS has been verified.

```sh
python manage.py migrate --noinput
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 2 --timeout 30
```

Worker count is a starting point, not a measured capacity claim. Set it from actual memory and load tests. Run the public integration tests against a separate PostgreSQL test database; never aim destructive test database setup at production. Existing `config.test_settings` tests SQLite and does not prove PostgreSQL parity.

Configure HTTPS checks of `/health/live/` and `/health/ready/`. Live reports process availability; ready runs SELECT 1 and returns 503 on a database failure, without exception details. Neither checks SMTP, migrations, storage, worker delivery or all product functions. Use additional end-to-end checks for those dependencies. Probes are GET-only and return no-store responses. Do not exempt the public health route from TLS just to pass a probe.

Schedule `python manage.py deliver_notifications` using the same environment if needed. Delivery is idempotent; the command processes a bounded due batch, continues after isolated failures and returns a nonzero status when some events remain queued. Normal events deliver on commit; authenticated readers also retry their own due events in bounded batches. Monitor backlog/failures and verify actual worker scheduling separately. Clear expired sessions on a schedule.

Before release, verify real password-reset email, signup/survey/consent/chat/workspace/media, cache and rate limits, alerts, backup/restore, error pages, dependency review and load targets. Capture evidence without credentials or message bodies. No provider/domain has been chosen and no application has been exposed publicly in this task.

## Authentication request limits

Login (including admin), registration and password-reset POSTs now use shared database fixed-window counters before password hashing, account creation or sending email. Default login limits are 30 requests per IP / 15 minutes and 8 per IP + normalized identity / 15 minutes; registration is 10 per IP / hour; reset is 10 per IP and 3 per IP + email / hour. All attempts count, including successful ones. These are initial guardrails, not measured optimal thresholds. HTTP 429 includes Retry-After and no-store; counter DB failure denies the POST with generic HTTP 503.

Keys contain keyed hashes rather than raw addresses/emails. Run `python manage.py prune_auth_limits` regularly to remove expired counters. No Redis or extra paid service is required. A fixed window can admit bursts around its boundary; it does not stop distributed attacks. Add provider edge controls and tune from observed abuse/false positives before a wider launch.

By default only REMOTE_ADDR is used; arbitrary forwarded headers are ignored. If behind a proxy, configure exact ROOMORA_AUTH_TRUSTED_PROXIES CIDRs only after confirming the edge overwrites X-Roomora-Client-IP with a single verified client address. Keep the origin inaccessible to untrusted direct clients. If the edge cannot guarantee this, leave header trust disabled and account for shared-IP limits. Rehearse with the real provider: the local concurrency tests prove SQLite behavior, not PostgreSQL or proxy correctness.

## Rollback procedure

Keep the previous app build and additive schema compatibility. Disable the affected capability server-side if needed, restore the prior compatible application version, and recheck health plus core flows. Do not reverse migrations or overwrite DB/media from a backup automatically: assess newly written data and consent history first. Record restore point, operator and outcome during the rehearsal.
