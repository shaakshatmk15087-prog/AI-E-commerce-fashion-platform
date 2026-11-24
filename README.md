# AI Fashion Platform

React + Vite + Tailwind frontend, Flask + SQLAlchemy backend, MySQL (SQLite fallback for local dev).
Spec: ../AI_Fashion_Platform.md

## Backend
    cd backend
    python -m venv .venv && .venv/Scripts/activate   # Windows
    pip install -r requirements.txt
    copy .env.example .env      # set DATABASE_URL for MySQL, real secrets
    flask --app run db upgrade     # migrations are committed in backend/migrations
    python run.py               # http://localhost:5000
    python seed.py              # dev data: admin@example.com / AdminPass123 + 12 sample products
    pytest

## Frontend
    cd frontend
    npm install
    npm run dev                 # http://localhost:5173 (proxies /api to :5000)

## Payments (Phase 2)
`PAYMENT_PROVIDER=mock` simulates a gateway. Orders are confirmed only by a signed (HMAC-SHA256) payment
event processed idempotently by `POST /api/v1/payments/webhook`; the dev "pay" button feeds the same path.
Set `MOCK_PAYMENTS_ENABLED=false` in production. To add Razorpay, implement a provider in
`app/services/payment_service.py` (create_order + signature verification).
Stock is reserved at checkout and released on cancel/expiry; call `order_service.release_expired_orders()`
from the scheduler (Phase 4).

## AI stylist (Phase 3)
Set `ANTHROPIC_API_KEY` in `backend/.env` (never in the frontend). Flow per message: Claude turns the request into a
structured search -> the backend retrieves/ranks real in-stock products (rules + profile + text match) -> Claude picks
from those candidates and explains. The server drops any product id that was not retrieved and rejects model text that
quotes prices, discounts or URLs. Without a key (or on any AI error) the same pipeline runs rule-based and the UI says so.
Config: `AI_MODEL` (default `claude-opus-5-5`), `AI_FALLBACK_MODEL` (server-side refusal fallback, empty to disable),
`AI_DAILY_MESSAGE_LIMIT` (per user, UTC day). Usage (mode, calls, tokens) is stored on each assistant message and logged.
No credits are charged for chat yet - that is an open business decision.

## Credits, wallet and subscriptions (Phase 4)
Two separate balances. **Daily Credits** are a free allowance that lapses at the daily reset; **Super Credits** are bought or
subscription-granted, accumulate, and never expire. Everything lives in an append-only ledger (`credit_transactions`);
`wallets` holds cached balances that `wallet_service.reconcile` can verify. Balances change only through atomic conditional
updates and every grant/spend has a unique idempotency key, so retries, duplicate webhooks and concurrent spends cannot
double-apply or go negative.

**Daily reset:** the period boundary is `reset_hour` in `reset_timezone` (default midnight `Asia/Kolkata`; admin-editable at
`/admin/credits`). All timestamps are stored in UTC. Expiry and the daily grant are applied lazily on every wallet access
and by the scheduled job, both idempotently (one `daily_credit_grants` row per user per period).

**Placeholder business rules (all editable by an admin, all audited):** 10 Daily Credits/day; AI chat costs 0 (free); spend
priority Daily-then-Super; sample packs/plans from `seed.py`; a month = 30 days; renewals are manual (no auto-billing);
cancelling keeps access to period end with no refund. AI chat, when it costs credits, is charged only if the AI delivered
recommendations.

**Jobs:** `flask run-jobs` (cron/Task Scheduler) or set `SCHEDULER_ENABLED=true` for the in-process scheduler (`python run.py`).
Jobs are idempotent and correctness does not depend on them.

## Stylists, consultations and rewards (Phase 5)
**Stylists** are created by an admin from an existing account (`/admin/stylists`) and must be approved before customers see
them. A stylist manages a profile and bookable slots (`/stylist`). **Text consultations:** booking atomically claims the slot
and *reserves* the price in Super Credits (ledger type `reservation`); the stylist accepts or declines; chat opens on
acceptance (polling, not websockets); the stylist completes the session once its start time has passed, which records their
share as earnings (a record only, no money moves). Cancel/decline/expiry release credits per the policy below.

**Placeholder policies (admin-editable at `/admin/stylists`, audited):** 30 Super Credits per consultation (Super-only, with an
optional per-stylist price); free cancellation 24h+ before the start, otherwise 50% refunded (rounded down); stylist
cancel/decline/no response in 24h = full refund; stylist share 70%; minimum 2h booking notice.

**Rewards:** 1 point per full ₹100 on a *delivered, paid* order; referral bonuses (100 referrer / 50 friend) are paid only when
the friend's first order is delivered, once per friend, capped per referrer. Points are a separate currency (no cash value) and
are redeemed through admin-defined offers (placeholder: 100 points -> 10 Super Credits). In-app notifications cover bookings,
messages, reminders and rewards. `flask run-jobs` also expires unanswered requests and sends reminders.

Dev logins from `seed.py`: `stylist@example.com` and `mira@example.com` / `StylistPass123`.

## Admin, hardening and launch (Phase 6)
* **Admin console** (`/admin`): dashboard (revenue, orders, AI usage, credit liability, stock alerts), orders with **refunds**, products, categories +
  inventory, users (deactivate/reactivate takes effect immediately), credits/plans, stylists/rewards, reports (CSV exports with spreadsheet-formula
  protection) and a filterable **audit log** that now covers every sensitive admin action.
* **Privacy:** customers can download their data and delete their account (personal data erased/anonymised, accounting records kept); a retention job
  purges old AI chats, expired revoked-token ids and old read notifications.
* **Hardening:** deactivated accounts are rejected on every endpoint; security headers, request ids, safe JSON errors, 1 MB request cap, readiness probe;
  in production the app **refuses to boot** with default secrets, SQLite, the mock payment provider, non-HTTPS origins or in-memory rate limits.
* **Tests:** 136 backend tests, including an automated authorization audit of every route. Run on MySQL with `TEST_DATABASE_URL=mysql+pymysql://...`.
  Accessibility: run axe-core (`npm i -D axe-core`, serve `node_modules/axe-core/axe.min.js` from the dev server, run `axe.run()` in the browser) -
  it found and we fixed contrast and list-structure issues; zero violations across ~20 pages/states. Manual keyboard/screen-reader testing is still required.
* **Deployment:** `docker-compose.yml`, Dockerfiles, nginx, backup/restore/verify scripts, `docs/DEPLOYMENT.md`, `docs/LAUNCH_CHECKLIST.md`,
  generated `docs/API.md` and `docs/DATABASE.md` (`python backend/scripts/gen_docs.py`). **Read the verification status at the top of DEPLOYMENT.md.**

## Status
Phase 1 complete: skeleton, auth (register/login/logout with token revocation), RBAC, email verification,
password reset (single-use, 1h), account + fashion profile (edit/delete), migrations, shared layout.

Emails are logged to the backend console in dev (app/services/email_service.py). Replace `send_email`
with a real provider before production. Set FRONTEND_URL for correct links.

Phase 2 complete: catalogue (search/filters/sort), product detail with variants, wishlist, cart, addresses,
checkout, mock-gateway payment with verified webhooks, orders + tracking, admin product/order management.

Phase 3 complete: AI stylist chat, hybrid recommender, personalised home recommendations, chat history.

Phase 4 complete: dual-credit ledger wallet, daily grants/expiry, credit packs, subscriptions, admin credit tools + audit log, scheduled jobs.

Phase 5 complete: stylist directory, availability, text-consultation booking with credit reservation/settlement, rewards and referrals, notifications.

Phase 6 complete (with the caveats in docs/DEPLOYMENT.md and docs/LAUNCH_CHECKLIST.md).
