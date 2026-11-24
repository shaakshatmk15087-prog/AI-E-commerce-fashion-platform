"""Subscriptions. Activation only ever happens from a verified payment event (payment_service), never from the browser.

Placeholder policies (open business decisions): a month is 30 days and a year 365 days; renewing is a manual,
separately-paid action (no automatic recurring billing yet); cancelling keeps access until the paid period ends and
is not refunded; each plan grants Super Credits either once per paid period ("renewal") or once per daily period
("daily"). Granted Super Credits accumulate and never expire.
"""
from datetime import timedelta

from ..extensions import db
from ..models import SubscriptionPlan, UserSubscription
from . import wallet_service
from .errors import ShopError

INTERVAL_DAYS = {"month": 30, "year": 365}


def _live(now):
    return (UserSubscription.status == "active") & (UserSubscription.current_period_end > now)


def current(user_id, now=None):
    now = now or wallet_service.now_utc()
    return (UserSubscription.query.filter(UserSubscription.user_id == user_id, _live(now))
            .order_by(UserSubscription.id.desc()).first())


def begin_checkout(user, plan_id):
    """Create (or reuse) the pending subscription row for a purchase/renewal. Caller creates the payment."""
    plan = db.session.get(SubscriptionPlan, plan_id)
    if not plan or not plan.is_active:
        raise ShopError("Plan not available.", 404)
    wallet_service.get_wallet(user.id)  # row lock on the wallet serialises concurrent checkouts per user
    now = wallet_service.now_utc()
    active = current(user.id, now)
    if active and active.plan_id != plan.id:
        raise ShopError("You already have an active subscription. Let it end (or cancel) before switching plans.", 409)
    if active:
        return active, plan
    pending = (UserSubscription.query.filter(UserSubscription.user_id == user.id,
                                              UserSubscription.status.in_(["pending", "incomplete"])).first())
    if pending:  # retry after an unfinished/failed payment: reuse the row instead of piling up new ones
        pending.plan_id, pending.status = plan.id, "pending"
        return pending, plan
    sub = UserSubscription(user_id=user.id, plan_id=plan.id, status="pending")
    db.session.add(sub)
    db.session.flush()
    return sub, plan


def activate(payment):
    """Apply a verified, paid subscription payment: start/extend the period and grant credits (idempotent)."""
    sub = db.session.get(UserSubscription, payment.reference_id)
    if not sub:
        return "unknown_subscription"
    plan = sub.plan
    now = wallet_service.now_utc()
    days = timedelta(days=INTERVAL_DAYS[plan.billing_interval])
    if sub.status == "active" and sub.current_period_end and sub.current_period_end > now:
        sub.current_period_end = sub.current_period_end + days  # renewal extends the paid period
    else:
        sub.start_at = sub.start_at or now
        sub.current_period_start, sub.current_period_end = now, now + days
    sub.status = "active"
    sub.cancel_at = None
    if plan.grant_frequency == "renewal":
        wallet_service.grant(sub.user_id, "super", plan.super_credit_amount, "subscription", source_type="subscription",
                             source_id=sub.id, key=f"sub:{sub.id}:payment:{payment.id}",
                             description=f"{plan.name} subscription credits")
    else:
        period_date, _s, _e = wallet_service.period_for(now)
        grant_daily(sub.user_id, now, period_date)
    return "paid"


def grant_daily(user_id, now, period_date):
    """Daily-frequency plans: one Super Credit grant per daily period while the subscription is live."""
    sub = current(user_id, now)
    if sub and sub.plan.grant_frequency == "daily" and sub.plan.super_credit_amount > 0:
        wallet_service.grant(user_id, "super", sub.plan.super_credit_amount, "subscription", source_type="subscription",
                             source_id=sub.id, key=f"sub:{sub.id}:day:{period_date.isoformat()}",
                             description=f"{sub.plan.name} daily credits")


def mark_failed(payment):
    sub = db.session.get(UserSubscription, payment.reference_id)
    if sub and sub.status == "pending":
        sub.status = "incomplete"


def cancel(user):
    now = wallet_service.now_utc()
    sub = current(user.id, now)
    if not sub:
        raise ShopError("You have no active subscription.", 404)
    sub.cancel_at = sub.current_period_end
    return sub


def expire_due(now=None):
    """Scheduled: close subscriptions whose paid period ended."""
    now = now or wallet_service.now_utc()
    n = 0
    for sub in UserSubscription.query.filter(UserSubscription.status == "active",
                                             UserSubscription.current_period_end <= now).all():
        sub.status = "cancelled" if sub.cancel_at else "expired"
        n += 1
    return n
