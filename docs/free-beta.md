# Free beta deployment rehearsal

Status: code is prepared locally. No hosting account, public URL, Brevo credentials or real email delivery has been verified. Budget is zero recurring cost; do not enable paid plans or attach a payment method as part of this workflow.

The owner has confirmed they do not have a PythonAnywhere account. Follow [the Vietnamese account setup handoff](free-account-start.vi.md) first. Account credentials and acceptance of the provider's terms belong to the owner; no account has been created by the assistant.

Use the existing Django application on a PythonAnywhere Free WSGI web app. Its [official deployment guide](https://help.pythonanywhere.com/pages/DeployExistingDjangoProject/) describes the virtualenv, WSGI file, static mappings and reload workflow. Use a Python version compatible with requirements.txt (Python 3.10+). Do not install the PostgreSQL/Gunicorn requirements for this single-worker profile. Check remaining disk after installing dependencies; the provider's storage allowance includes the virtualenv, app, DB, uploads and logs.

## Configuration and storage

Use deploy/free-beta.env.example as a list of settings. Public profiles ignore the development .env, force DEBUG off and use shared security from config.public_settings. PostgreSQL/SMTP and free-beta SQLite/HTTPS-email profiles remain distinct. No fake PostgreSQL or SMTP credential is required for the free beta.

Generate a fresh SECRET_KEY. Set actual allowed host and HTTPS CSRF origin. Inject settings into the WSGI process from a private file or the provider's supported environment mechanism; do not put credentials in the Git checkout, static directory, command arguments, screenshots or logs. If using a private JSON environment file, load it before get_wsgi_application; restrict access to its owner. Use the same environment for management commands. Never print the secret file contents as a diagnostic.

Create four absolute sibling directories for static files, public avatars, private evidence and SQLite data. The settings resolve paths and reject overlapping roots. Map only /static/ → STATIC_ROOT and /media/ → MEDIA_ROOT in the host web configuration. Do not map the project root, ROOMORA_DATA_ROOT or ROOMORA_PRIVATE_MEDIA_ROOT. Private images must use the existing authenticated Django routes. Verify unauthorized downloads fail after deployment.

New avatar uploads are resized to fit within 800 × 800; room/evidence images fit within 2048 × 2048. Both preserve aspect ratio, apply EXIF orientation and re-encode actual pixels without metadata or appended input bytes. JPEG/WebP use quality 85, PNG preserves transparency. Input/output limits remain 5 MiB, input pixels are capped at 20 million and animated images are rejected explicitly. Existing stored images are not rewritten. These bounds reduce storage/transfer; disk capacity and deletion/retention policy still need release checks. Image annotations use normalized coordinates and continue to work after proportional resizing.

The free-beta profile now caps combined public/private uploads at 64 MiB and requires at least 32 MiB of free filesystem space after each upload. Both storages share a nonblocking OS file lock under ROOMORA_DATA_ROOT, then count existing files and check disk space before writing. A busy/unavailable lock or capacity shortage rejects the upload with a generic retry message; other app routes remain available. This is a single-host local-filesystem guard, not a distributed/object-storage quota. Direct avatar upload uses the same byte validation/normalization as the profile form. Upload rejection leaves the previous avatar record intact; room upload rejection rolls back the mutation receipt and image record.

The file count includes unreferenced files and historical uploads. After a replacement or explicit avatar removal commits, the old local avatar is removed only if no Profile still references it and its path resolves inside the public avatars directory. Rollback cancels cleanup. Cleanup errors retain the file and emit a generic operator warning without failing the committed user action. Historical orphan files, failed database writes after file creation and simultaneous replacements can still leave unused uploads, so retention and private operator review are required. No historical bulk deletion is performed. Room/evidence images are not affected by avatar cleanup.

The free profile also limits each person to 20 room/evidence images and 8 MiB of normalized room-image files across all their rooms, including old/private workspaces. Current avatars remain covered by the 5 MiB individual file and shared app limits. The image form displays the personal limits. The personal check runs within the actor's serialized mutation; SQLite IMMEDIATE transactions are required by the free profile. A same-person eight-way concurrent fixture admitted exactly one image at a one-image test limit. Successful idempotent retries reuse the receipt without consuming capacity again. Missing referenced image files reject the new upload for operator review rather than undercounting usage. Existing images are retained even if they exceed a newly applied limit; there is no reset period or automatic evidence deletion. Rehearse this on the actual host, including inactive workspaces.

These guards are not the provider's account-wide usage meter. They exclude DB, virtualenv, logs, static files and backups; the free-space reserve does not guarantee these cannot later exhaust the disk. Replacement uploads temporarily require capacity for both old and new files; do not delete the current avatar first to make room. Inspect provider usage and measure upload latency as the file count grows (the shared guard scans local upload files). Do not delete user evidence automatically to make room. Rehearse the actual host's filesystem lock and disk reporting before enabling registration.

ROOMORA_DATA_ROOT contains roomora.sqlite3. The file must survive web-app reloads. Take consistent backups using SQLite's backup API rather than copying a live DB file, and rehearse restore into a separate directory. Keep downloaded encrypted/private backups away from the public host paths. Do not overwrite newly created user data during a restore test.

### Full local backup and isolated restore

Temporarily disable web traffic and stop other management writers before backing up. SQLite's backup API provides a consistent DB snapshot; matching media requires uploads/deletions to be stopped throughout. The confirmation flag is an operator assertion, not an automatic maintenance lock. On the host, verify the app is unavailable for writes before confirming.

```sh
python manage.py backup_free_beta --output-dir /home/OWNER/private-backups --maintenance-confirmed
python manage.py restore_free_beta --backup /home/OWNER/private-backups/roomora-SNAPSHOT_ID --destination /home/OWNER/restore-rehearsal-SNAPSHOT_ID
```

Replace OWNER and SNAPSHOT_ID with actual values; neither destination may overlap the checkout, DB directory, public/static or private upload roots. The snapshot contains database.sqlite3, media/, private_media/ and a SHA-256 inventory. Restore validates inventory, hashes and SQLite integrity before copying into a new directory. Existing destinations, symbolic links and unexpected files are rejected. This restores a rehearsal copy only; switching live settings and replacing production data require a separate reviewed recovery procedure.

Backups contain personal data and are not encrypted by these commands. POSIX owner permissions are set on the host; Windows permissions require the operator's private folder access controls. Hashes detect accidental changes, not a maliciously replaced manifest. Keep backups outside every web mapping, download through the owner's protected account, and use private encrypted storage for off-host retention. Disk must accommodate both uploads/DB and their backup, plus any rehearsal copy; inspect available space first. Do not retain unlimited snapshots on a free account. Code, environment secrets and provider configuration are excluded: preserve source revision and configuration securely as separate recovery prerequisites.

## Email

Configure the verified sender and BREVO_API_KEY. The backend uses [Brevo's transactional HTTPS API](https://developers.brevo.com/reference/send-transac-email), fixed endpoint, no redirects and a ten-second timeout. It sends text plus HTML, preserves recipient/CC/BCC/reply-to semantics, and rejects unsupported attachments/custom headers instead of silently discarding them. It does not automatically retry an ambiguous timeout: the provider might already have accepted the message. Daily counter attempts are capped at 250 per UTC fixed day in the shared DB, including failed attempts, leaving nominal margin below Brevo's 300/day tier. This is not an account-wide quota guarantee if the same Brevo account is used elsewhere.

A provider 201/messageId indicates acceptance, not inbox delivery. Verify account transactional access, allowed sender and Gmail/Outlook reception with owner-controlled recipient addresses. A domain-free sender is not a deliverability guarantee. The application never logs response bodies, request payloads, reset links or API keys. Django's reset form logs generic failures and keeps the same response for known/unknown emails. Avoid resetting a real user's password as a smoke test; request a test link for a dedicated test account.

## Rehearsal

With actual environment injected and DJANGO_SETTINGS_MODULE=config.free_beta_settings:

```sh
python -m pip install -r requirements.txt
python manage.py check --deploy --fail-level ERROR
python manage.py migrate --plan
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```

Review every deployment warning. The two expected warnings are security.W005 and W021: HSTS include-subdomains and preload are deliberately disabled because the provider subdomain is not an owned parent domain and no preload rollout has been validated. Do not enable them solely to make a check green. Local rehearsal asserts these are the only warnings; any additional warning requires investigation before release.

Review the migration plan and back up populated data before migration. Configure the host WSGI file to import config.wsgi.application after environment injection. Reload from the Web tab. Verify HTTPS redirection, secure session/CSRF cookies, readiness, login/registration/survey, synthetic-account exclusion, mutual chat, independent workspace consent, costs, direct media access and data persistence after another reload. Measure concurrency and response times on the actual host; local file-backed SQLite tests do not prove host capacity.

Verify the real client address seen by the app before enabling trusted proxy headers. Only enable ROOMORA_TRUST_PROXY_PROTO after confirming the host replaces forwarded-proto. Only use ROOMORA_AUTH_TRUSTED_PROXIES for exact verified proxy networks and an edge-overwritten X-Roomora-Client-IP header. Otherwise the limiter uses REMOTE_ADDR and may group clients behind the same proxy; measure this rather than trusting arbitrary forwarded headers.

## Operations within a free account

Public profiles now apply fixed-window actor limits to new journey mutations: ordinary writes 120/minute and 1,000/hour; messages 30/minute and 300/hour; discovery decisions/saves 60/minute and 600/hour; workspace invitations 10/hour; room saves 60/hour; image upload attempts 20/hour; reports 10/hour. These are initial beta thresholds, not measured host capacity. Counters use the existing indexed HMAC-key table without storing a raw actor identifier. Authenticated users do not share a journey quota merely because they use the same network.

An exact successful mutation receipt replays before budget consumption and does not repeat the operation. Admitted attempts that fail with an expected domain/storage error retain their counter while the operation's DB savepoint rolls back; files are not made transactional by this savepoint. Counter/transaction database failures return generic 503 with a 60-second Retry-After. Excess requests return uncacheable 429 with Retry-After and a JSON retry_after value, following [RFC 6585](https://www.rfc-editor.org/rfc/rfc6585.html#section-4). The UI does not automatically replay writes.

Block, disconnect, workspace leave, choice/agreement withdrawal and viewing cancellation bypass ordinary write budgets. Negative workspace/viewing/clause responses also bypass them, while positive consent remains limited and fully permission/version checked. Reports use their separate allowance even if ordinary writes are exhausted. Fixed-window boundaries can admit a larger burst across two adjacent windows. These guards do not cover all HTTP traffic, legacy core writes, malformed mutation keys or repeated cached receipts, and are not edge DDoS protection. Rehearse them on the actual host, measure false positives and prune expired counters with the existing operator command.

Free accounts created in 2026 lack scheduled tasks; no background worker is assumed. In-app events are persisted atomically and normally delivered on transaction commit. A failed delivery is retained with exponential backoff (30 seconds to one hour). Authenticated page reads retry at most ten due events addressed to that reader, once per request. A recipient index is backfilled from historical JSON recipient IDs; it prevents scanning unrelated users' queues. This path still requires rehearsal on the actual host. During rehearsal run these manually and inspect backlog/results:

```sh
python manage.py deliver_notifications
python manage.py prune_auth_limits
python manage.py clearsessions
```

The request-driven path avoids requiring a paid cron worker for the beta. Offline readers will see retained updates on return; no browser push or email notification is implied. An operator command can process up to 500 due events, continues after isolated delivery failures and returns a failure status if some remain queued. Workspace notification lists and unread counts use current membership, connection generation and block checks. Test revocation on the host, including legacy blocks. Do not add public unauthenticated maintenance endpoints or abuse free-host policies with keepalive pings.

Chat polling stops while hidden/offline and cancels in-flight work. Returning to the page or reconnecting schedules an immediate access-checked refresh. Polls never overlap; idle intervals grow to 30 seconds, new messages return to four seconds, and errors back off up to one minute. Each catch-up cycle reads at most three 50-message pages, then schedules a separate continuation. A 12-second deadline aborts a hung cycle. Login redirects, 401/403/404 responses stop automatic polling and disable send; the backend still checks current mutual consent on every request. Explicit sends retain their existing idempotent retry behavior and are not automatically replayed by the polling scheduler. This intentionally trades up to 30 seconds of idle incoming-message latency for fewer requests. Test real browser visibility, offline/resume, long backlog, session expiry and consent revocation on the host; Node scheduler/integration fixtures are not browser end-to-end evidence.

Assign monthly web-app renewal, disk inspection, private backups and cleanup to the operator. Set a small beta scope based on measured results. No SLA, unlimited scale or permanent free plan is promised. If capacity becomes insufficient, preserve schema/data and move to the PostgreSQL profile after a measured migration rehearsal; do not upgrade a plan automatically.

## Local discovery measurement

Authenticated navigation now includes Tìm trọ. Its dashboard separates private saved rooms from shared boards that pass current membership, connection generation and block checks. Cards show whole-room monthly/upfront entered costs, missing items and estimate badges. Unknown costs display as unknown, including deposit on detail/comparison pages; a confirmed zero remains zero. These are rooms saved by users, not an external listings feed. The local suite has 157 passing Django tests and 10 JavaScript tests; provider and full journey rehearsal remain required.

Discovery offers list and swipe views over the same ranked candidate pool. List is the initial default; explicit selection is remembered in the browser's Django session. Switching view preserves area/rent/room filters and the signed pagination cursor; changing filters starts at the first page. Listing shows budget, area and a short lifestyle reason; saving updates in place when JavaScript is available. Without JavaScript the normal POST form still saves and redirects to saved candidates. No view mode bypasses eligibility, private room access or mutual chat consent. The score formula is unchanged; percentages remain provisional estimates rather than validated probabilities.

`tools/benchmark_discovery.py --output /PRIVATE/PATH/results.json` builds its own temporary SQLite database and synthetic fixtures; it does not use the live user database. Run it with the project's Python environment. The discovery service ranks every eligible profile but expands card details only for the ten displayed on the page. A local 1,000-candidate measurement reduced peak Python allocations from about 9.01 MB to 4.35 MB; median service time remained about 102 ms in both modes. These seven samples per mode exclude HTTP rendering, concurrent requests and provider limits. They do not measure worker RSS, public capacity or recommendation quality. The full pool still has to be scored on each discovery request; host load tests remain required before setting beta capacity.
