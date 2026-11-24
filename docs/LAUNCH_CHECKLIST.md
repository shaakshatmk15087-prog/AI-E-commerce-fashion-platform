# Launch checklist

Tick every box before taking real customers or real money. Items marked **BLOCKER** must not be skipped.

## A. Business decisions still open (spec section 17) - the app runs on PLACEHOLDER values until you decide
All are admin-editable; nothing needs a redeploy.

- [ ] Daily Credits per day, reset time and timezone (placeholder: 10, midnight Asia/Kolkata) - `/admin/credits`
- [ ] Whether AI chat costs credits and how much (placeholder: free) - `/admin/credits`
- [ ] Consultation price in credits, per stylist if needed (placeholder: 30 Super Credits)
- [ ] Consultation cancellation / refund rules, stylist share, request expiry - `/admin/stylists` (placeholder: free until 24 h before, then 50 %, stylist share 70 %)
- [ ] Subscription plans, prices, grant schedule (renewal vs daily) - `/admin/credits`; confirm manual renewal is acceptable or build auto-billing
- [ ] Super Credit pack prices
- [ ] Reward earning/redemption rules and what points can buy (placeholder: 1 point per ₹100; 100 points -> 10 Super Credits)
- [ ] Order return, cancellation, shipping and refund policy (placeholders: shipping ₹99 below ₹999, tax 0 %, full refunds only, restock rules)
- [ ] Tax: GST rate and how it is shown (`TAX_RATE_BPS`, currently 0)
- [ ] Seller / inventory ownership model; whether stylists are employees, contractors or partners (affects payout of the earnings records)

## B. Legal and compliance (**BLOCKER**)
- [ ] The Privacy Policy, Terms and Returns pages are **drafts**. Replace every `[bracketed]` detail and have a qualified professional review them against Indian privacy (DPDP), consumer-protection, e-commerce, tax and payment rules.
- [ ] Appoint and publish a grievance/privacy contact; confirm retention periods (chat history default 365 days; accounting records [n] years).
- [ ] Confirm the account-deletion and data-export behaviour (Account -> Privacy & data) matches your obligations.
- [ ] Check the AI provider's data-processing terms (chat content leaves your infrastructure); disclose the provider by name in the policy.

## C. Payments (**BLOCKER**)
- [ ] Real gateway implemented, tested in its test mode (success, failure, duplicate webhook, refund) - see DEPLOYMENT.md section 5.
- [ ] `MOCK_PAYMENTS_ENABLED=false`, `PAYMENT_PROVIDER` set, webhook secret rotated and stored in a secret manager.
- [ ] Reconcile one day of gateway settlements against the admin Payments CSV.

## D. Security
- [ ] All secrets unique and from a secret manager; `.env` never committed. Rotate any secret that was ever shared.
- [ ] Default dev accounts removed (`seed.py` was never run in production); admin password strong; consider MFA at the identity layer.
- [ ] HTTPS everywhere, HSTS active (`curl -I` shows `Strict-Transport-Security`), HTTP redirected.
- [ ] `docker compose logs backend` contains no tokens/passwords; request ids present.
- [ ] Rate limits in Redis (the app refuses to boot otherwise). Consider a WAF/CDN for bot and DoS protection.
- [ ] Penetration test or at least an external vulnerability scan; dependency audit (`pip-audit`, `npm audit`) and a plan to patch.
- [ ] Note the known trade-off: the bearer token is kept in `sessionStorage` (cleared on tab close, simple, but readable by any XSS). The strict CSP and React's escaping mitigate XSS; moving to HttpOnly cookies would also require CSRF protection.
- [ ] Admin accounts: review the audit log weekly (`/admin/reports`).

## E. Reliability and operations
- [ ] Backups scheduled **and copied off-host**; `verify-restore.sh` run successfully on the real host; RPO/RTO agreed.
- [ ] Monitoring/alerts configured (DEPLOYMENT.md section 3); Sentry (or equivalent) DSN set.
- [ ] Exactly one `scheduler` running; confirm `maintenance:` log lines.
- [ ] Load test checkout and AI chat at expected peak; size gunicorn workers and DB accordingly.
- [ ] Email provider implemented (today emails are only logged): verification, password reset, order updates.
- [ ] Runbook: who is on call, how to roll back, how to disable the AI (`AI_ENABLED=false`) or payments in an emergency.

## F. Product quality
- [ ] Replace seeded placeholder products/photos with real catalogue data; set real low-stock thresholds.
- [ ] Accessibility: automated axe-core WCAG 2.1 A/AA checks pass on ~20 pages/states (verified during development). Still do a manual pass: keyboard-only navigation, a screen reader (NVDA/VoiceOver), 200 % zoom, reduced motion.
- [ ] Cross-browser/device test (Safari iOS, Chrome Android, Firefox) of checkout, AI chat, booking.
- [ ] Verify with real AI key: send chats and confirm replies are labelled "AI-generated" (not "Rule-based") and costs/tokens appear in the admin dashboard.
- [ ] Content: About, FAQ, Contact details filled in.

## G. After launch
- [ ] Watch the dashboard daily for the first weeks (revenue, refunds, AI fallback share, stock alerts).
- [ ] Revisit placeholder policies with real data (credit usage, cancellation rates, referral abuse).
- [ ] Plan the deferred roadmap items: voice/video consultations, automatic subscription renewal, email/SMS notifications, digital wardrobe, virtual try-on.
