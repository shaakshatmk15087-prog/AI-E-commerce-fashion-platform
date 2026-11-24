# Deployment guide

The repository ships a Docker-based production stack: **MySQL 8.4 + Redis + Flask API (gunicorn) + scheduler + nginx** (serves the built
React app and proxies `/api`). Any host that runs Docker works (a VM, ECS/Fargate, Cloud Run + managed MySQL, ...). Nothing here
assumes a particular cloud: pick one, then follow "Mapping to a managed cloud" below.

> **Verification status** (be honest with yourself before launch)
> * Verified: all 6 migrations apply on a real MySQL 8.4 and match the models (`flask db check` clean); the full 136-test suite passes on
>   MySQL 8.4, including the concurrent-spend and concurrent-booking race tests with real row locks; both Docker images build.
> * Verified end to end with Docker (staging-style, `ALLOW_INSECURE_MOCK_PAYMENTS=true`): the app refuses to boot with the mock provider
>   and no override; `docker compose up` brings db/redis/migrate/backend/scheduler/web healthy; through nginx: readiness, SPA deep links,
>   register/login/logout (revoked token -> 401), single (non-duplicated) security headers, Redis-backed rate limiting (429 after the
>   limit), no tokens/passwords in logs, scheduler `maintenance:` lines; `backup.sh`, `verify-restore.sh` (also proven to FAIL on a
>   deliberately corrupted wallet balance) and a destructive `restore.sh` drill (post-backup data gone, accounts/catalogue intact).
>   Still repeat the Backups drill on your real host, and copy backups off-host.
> * Known gap: gunicorn's access log lines do not include the request id (the application's own log lines and the `X-Request-ID`
>   response header do).
> * Not built: a real payment gateway (only the mock provider exists), email delivery (dev mode logs emails), automatic subscription billing.

## 1. First deployment

```bash
cp .env.production.example .env          # fill in every blank; generate each secret separately
docker compose up -d --build
docker compose ps                         # db, redis healthy; migrate exited 0; backend, scheduler, web running
curl -fsS http://localhost:8080/api/v1/health/ready      # {"status":"ready"}
```

* `migrate` is a one-shot service that runs `flask db upgrade`; `backend` and `scheduler` start only after it succeeds, so replicas never race
  on schema changes.
* Create the first admin: `docker compose exec backend python - <<'EOF'` … or run `seed.py` **only in staging** (it creates demo accounts with
  well-known passwords). In production create an admin with a one-off script and a strong password, and never run `seed.py`.
* **TLS:** terminate HTTPS in front of the `web` service (cloud load balancer, Caddy, Cloudflare). It must send `X-Forwarded-Proto: https`.
  The API then emits HSTS. If a load balancer sits in front, also add `set_real_ip_from` / `real_ip_header` to `frontend/nginx.conf` so the
  real client IP reaches rate limiting and the audit log.

### The app refuses to start insecurely
With `APP_ENV=production` the API validates its configuration at boot and exits listing every problem: default/short secrets, SQLite,
the mock payment provider, localhost or non-HTTPS CORS origins, a non-HTTPS `FRONTEND_URL`, or in-memory rate limiting. This is deliberate.
For a **staging** stack that still uses the mock provider, set `ALLOW_INSECURE_MOCK_PAYMENTS=true` (and never in production).

## 2. Configuration reference
All settings are environment variables (see `.env.production.example`, `backend/.env.example`). Secrets must never be in source control or the
frontend bundle. Business rules (credit allowance, costs, cancellation/refund percentages, reward rates) are **not** env vars: they are
admin-editable at `/admin/credits` and `/admin/stylists` and every change is audited.

## 3. Operations

| Task | How |
|---|---|
| Logs | `docker compose logs -f backend scheduler web` (every line carries a request id; the same id is returned in the `X-Request-ID` header and in error bodies) |
| Liveness / readiness | `/api/v1/health` (process) and `/api/v1/health/ready` (database) |
| Scheduler | the `scheduler` service runs `flask run-jobs` every `SCHEDULER_SECONDS` (credit expiry/grants, subscription + consultation upkeep, data retention, unpaid-order release). Jobs are idempotent; correctness never depends on them |
| Error tracking | set `SENTRY_DSN`; request bodies, headers, cookies and user data are stripped before sending |
| Upgrade | `git pull && docker compose up -d --build` (migrations run first). Take a backup beforehand |
| Rollback | restore the pre-upgrade backup and redeploy the previous image tag. Migrations are not guaranteed reversible once data is written |
| Scale out | run more `backend` replicas behind the load balancer (rate limits are in Redis). Run exactly **one** `scheduler` |

### Alerts worth setting up
Readiness failing; `scheduler` container restarting or `maintenance:` log lines missing for 15 min; 5xx rate; payment webhook failures
(`Invalid signature` / `amount_mismatch` in logs); dashboard "fallback" share of AI replies > 20% (AI service down or key invalid).

## 4. Backups (verify these on your host)

```bash
./scripts/backup.sh                 # consistent mysqldump (no downtime), gzip, sha256, prunes files older than 14 days
./scripts/verify-restore.sh         # restores the newest backup into a scratch DB, compares tables/row counts, checks every wallet
                                    #   balance against its ledger, then drops the scratch DB   <- schedule this weekly
./scripts/restore.sh backups/aifp-<timestamp>.sql.gz    # DESTRUCTIVE restore into the live DB (stop the app first)
```

* Schedule `backup.sh` at least hourly (cron / Task Scheduler) and **copy the files off the host** to object storage in another
  region. A backup on the database's own disk is not a backup.
* Managed MySQL (RDS, Cloud SQL, ...)? Prefer the provider's automated backups + point-in-time recovery, and still keep `verify-restore`-style
  drills. Recovery targets to decide: RPO (how much data you can lose; hourly backups = up to 1 h) and RTO (how long to be back up).
* Restore drill, in order: stop `backend scheduler web` → `restore.sh <file>` → `docker compose up -d` → check `/health/ready` → run
  `verify-restore.sh` logic or the admin "ledger mismatch" indicator on a few wallets.

## 5. Payments go-live (blocking)
Only the mock provider is implemented. Before real money: implement the gateway provider in `backend/app/services/payment_service.py`
(`create_order`, signature verification, `refund` with an idempotency key), configure its **webhook URL** and secret, run the gateway's
test mode through checkout, a failed payment, a duplicate webhook and an admin refund, then set `PAYMENT_PROVIDER` and
`MOCK_PAYMENTS_ENABLED=false`. The webhook handler already verifies signatures, ignores replays and checks amounts; the refund path
writes its Refund row before calling the provider so a crash cannot cause a double refund.

## 6. Mapping to a managed cloud (example)
* Database: managed MySQL 8 (set `DATABASE_URL` to it and delete the `db` service). Enable automated backups + PITR, deletion protection, TLS.
* Redis: managed Redis (set `RATELIMIT_STORAGE_URI`). It only holds rate-limit counters.
* Containers: push the `backend` and `web` images; run `migrate` as a pre-deploy task; run `scheduler` as a single-instance service.
* Secrets: from the cloud secret manager into the container environment, not baked into images.
* Edge: managed TLS certificate + load balancer to `web:8080`; optional WAF/CDN in front.

## 7. Local development
```bash
cd backend && python -m venv .venv && .venv/Scripts/activate && pip install -r requirements.txt
copy .env.example .env && flask db upgrade && python seed.py && python run.py      # API on :5000
cd frontend && npm install && npm run dev                                          # app on :5173 (proxies /api)
pytest                                                                             # SQLite by default
TEST_DATABASE_URL=mysql+pymysql://user:pw@127.0.0.1:3306/aifp_test pytest           # same suite on MySQL
python scripts/gen_docs.py                                                         # regenerate docs/API.md and docs/DATABASE.md
```
