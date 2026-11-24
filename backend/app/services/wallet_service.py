"""Ledger-based dual-credit wallet.

* `credit_transactions` is append-only and is the source of truth; `wallets` holds cached balances that
  `reconcile()` can check against it. Corrections are compensating entries, never edits.
* Balances change only through atomic conditional UPDATEs (`balance >= amount`), so concurrent spends cannot go
  negative on any database, with row locks (SELECT ... FOR UPDATE) as a second layer on MySQL.
* Every grant/spend carries a unique idempotency key, so retries and duplicate webhooks cannot double-apply.
* Daily Credits live in one daily period at a time. The period boundary is `reset_hour` in `reset_timezone`
  (both admin-configurable). Expiry and the daily grant are applied lazily on every wallet access and also by the
  scheduled job, both idempotently. All stored datetimes are naive UTC.
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import AuditLog, CreditTransaction, DailyCreditGrant, User, Wallet
from .errors import ShopError
from .settings_service import get_credit_settings


class InsufficientCredits(ShopError):
    def __init__(self, needed, available):
        super().__init__("Not enough credits for this action.", 402, {"needed": needed, "available": available})


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def audit(actor_id, action, target_type=None, target_id=None, details=None):
    db.session.add(AuditLog(actor_id=actor_id, action=action, target_type=target_type,
                            target_id=str(target_id) if target_id is not None else None, details=details))


# ---- Daily period -----------------------------------------------------------------------------------
def period_for(now, cfg=None):
    """(period_date, start_utc, end_utc) of the daily period containing `now` (naive UTC)."""
    cfg = cfg or get_credit_settings()
    tz = ZoneInfo(cfg["reset_timezone"])
    local = now.replace(tzinfo=timezone.utc).astimezone(tz)
    shifted = local - timedelta(hours=cfg["reset_hour"])
    start_local = datetime.combine(shifted.date(), time(0), tz) + timedelta(hours=cfg["reset_hour"])
    end_local = datetime.combine(shifted.date() + timedelta(days=1), time(0), tz) + timedelta(hours=cfg["reset_hour"])
    to_utc = lambda d: d.astimezone(timezone.utc).replace(tzinfo=None)
    return shifted.date(), to_utc(start_local), to_utc(end_local)


# ---- Wallet access ----------------------------------------------------------------------------------
def get_wallet(user_id, lock=True):
    q = Wallet.query.filter_by(user_id=user_id)
    w = (q.with_for_update() if lock else q).first()
    if w:
        return w
    try:
        with db.session.begin_nested():
            w = Wallet(user_id=user_id, daily_balance=0, super_balance=0)
            db.session.add(w)
    except IntegrityError:  # created concurrently
        pass
    return (q.with_for_update() if lock else q).first()


def _balance_col(ctype):
    return Wallet.daily_balance if ctype == "daily" else Wallet.super_balance


def _apply(wallet, ctype, delta):
    """Atomically add `delta` to a balance; a decrease only succeeds if the balance covers it."""
    col = _balance_col(ctype)
    stmt = update(Wallet).where(Wallet.id == wallet.id)
    if delta < 0:
        stmt = stmt.where(col >= -delta)
    stmt = stmt.values(**{col.key: col + delta}).execution_options(synchronize_session=False)
    if db.session.execute(stmt).rowcount != 1:
        return None
    db.session.refresh(wallet)
    return getattr(wallet, f"{ctype}_balance")


def _key_exists(key):
    return key is not None and db.session.query(CreditTransaction.id).filter_by(idempotency_key=key).first() is not None


def _ledger(wallet, ctype, ttype, amount, balance_after, *, source_type=None, source_id=None, description=None,
            key=None, expires_at=None):
    row = CreditTransaction(wallet_id=wallet.id, credit_type=ctype, transaction_type=ttype, amount=amount,
                            balance_after=balance_after, source_type=source_type,
                            source_id=str(source_id) if source_id is not None else None, description=description,
                            idempotency_key=key, expires_at=expires_at)
    db.session.add(row)
    db.session.flush()
    return row


# ---- Grants -----------------------------------------------------------------------------------------
def grant(user_id, ctype, amount, ttype, *, source_type, source_id, key, description, expires_at=None):
    """Add credits exactly once per idempotency key. Returns True if applied, False if already applied."""
    if amount <= 0:
        raise ValueError("grant amount must be positive")
    wallet = get_wallet(user_id)
    if _key_exists(key):
        return False
    try:
        with db.session.begin_nested():
            after = _apply(wallet, ctype, amount)
            _ledger(wallet, ctype, ttype, amount, after, source_type=source_type, source_id=source_id,
                    description=description, key=key, expires_at=expires_at)
            if ctype == "daily":
                wallet.daily_expires_at = expires_at
    except IntegrityError:  # lost a race on the idempotency key: the other writer applied it
        return False
    return True


def expire_if_due(wallet, now):
    """Lapse Daily Credits whose period has ended (one idempotent ledger entry)."""
    if not wallet.daily_expires_at or wallet.daily_expires_at > now:
        return 0
    lapsed_at = wallet.daily_expires_at
    amount = wallet.daily_balance
    key = f"expiry:{wallet.id}:{lapsed_at.isoformat()}"
    if amount > 0 and not _key_exists(key):
        try:
            with db.session.begin_nested():
                after = _apply(wallet, "daily", -amount)
                if after is None:  # balance changed under us; the next pass will handle it
                    return 0
                _ledger(wallet, "daily", "expiry", -amount, after, source_type="system", description="Daily Credits expired",
                        key=key, expires_at=lapsed_at)
        except IntegrityError:
            return 0
    wallet.daily_expires_at = None
    return amount


def is_eligible(user):
    return bool(user and user.is_active and user.role == "customer")


def ensure_current(user_id, now=None):
    """Bring the wallet up to date: expire stale Daily Credits, grant today's allowance and any daily subscription
    credits. Idempotent and safe to call on every access. Caller commits."""
    from . import subscription_service
    now = now or now_utc()
    cfg = get_credit_settings()
    wallet = get_wallet(user_id)
    expire_if_due(wallet, now)
    user = db.session.get(User, user_id)
    if not is_eligible(user):
        return wallet
    period_date, _start, end = period_for(now, cfg)
    allowance = cfg["daily_allowance"]
    if allowance > 0 and not DailyCreditGrant.query.filter_by(user_id=user_id, period_date=period_date).first():
        try:
            with db.session.begin_nested():
                db.session.add(DailyCreditGrant(user_id=user_id, period_date=period_date, amount=allowance))
                db.session.flush()
        except IntegrityError:
            pass  # another request granted it first
        else:
            grant(user_id, "daily", allowance, "grant", source_type="daily_grant", source_id=period_date.isoformat(),
                  key=f"daily:{user_id}:{period_date.isoformat()}", description="Daily free credits", expires_at=end)
    subscription_service.grant_daily(user_id, now, period_date)
    db.session.refresh(wallet)
    return wallet


# ---- Spending ---------------------------------------------------------------------------------------
def service_config(service, cfg=None):
    cfg = cfg or get_credit_settings()
    sc = cfg["services"].get(service)
    if sc is None:
        raise ShopError("Unknown service.", 400)
    return sc


def plan_spend(wallet, service_cfg, priority):
    """Pure calculation of how a cost would be split. Returns (breakdown, available_in_allowed_types)."""
    order = ["daily", "super"] if priority == "daily_first" else ["super", "daily"]
    types = [t for t in order if t in service_cfg["credit_types"]]
    need, breakdown, available = service_cfg["cost"], {}, 0
    for t in types:
        bal = getattr(wallet, f"{t}_balance")
        available += bal
        take = min(need, bal)
        if take:
            breakdown[t] = take
            need -= take
    return (breakdown if need == 0 else None), available


def _with_cost(sc, cost_override):
    return {**sc, "cost": cost_override} if cost_override is not None else sc


def quote(user_id, service, cost_override=None):
    wallet = ensure_current(user_id)
    cfg = get_credit_settings()
    sc = _with_cost(service_config(service, cfg), cost_override)
    breakdown, available = plan_spend(wallet, sc, cfg["spend_priority"])
    return {"service": service, "cost": sc["cost"], "credit_types": sc["credit_types"],
            "breakdown": breakdown or {}, "sufficient": breakdown is not None, "available": available,
            "balances_after": {"daily": wallet.daily_balance - (breakdown or {}).get("daily", 0),
                               "super": wallet.super_balance - (breakdown or {}).get("super", 0)}}


def spend(user_id, service, *, source_type, source_id, key, description=None, ttype="spend", cost_override=None):
    """Debit credits for a service exactly once per `key`. Raises InsufficientCredits (402).
    `ttype="reservation"` marks a hold that may later be released (e.g. a consultation booking)."""
    cfg = get_credit_settings()
    sc = _with_cost(service_config(service, cfg), cost_override)
    wallet = ensure_current(user_id)
    prior = CreditTransaction.query.filter(CreditTransaction.idempotency_key.like(f"{key}:%")).all()
    if prior:
        return {"cost": sc["cost"], "breakdown": {r.credit_type: -r.amount for r in prior}, "idempotent": True}
    if sc["cost"] == 0:
        return {"cost": 0, "breakdown": {}, "idempotent": False}
    breakdown, available = plan_spend(wallet, sc, cfg["spend_priority"])
    if breakdown is None:
        raise InsufficientCredits(sc["cost"], available)
    try:
        with db.session.begin_nested():
            for ctype, amt in breakdown.items():
                after = _apply(wallet, ctype, -amt)
                if after is None:  # lost a race with another spend
                    raise InsufficientCredits(sc["cost"], available)
                _ledger(wallet, ctype, ttype, -amt, after, source_type=source_type, source_id=source_id,
                        description=description or KNOWN_DESC.get(service, service), key=f"{key}:{ctype}",
                        expires_at=wallet.daily_expires_at if ctype == "daily" else None)  # period these credits belong to
    except IntegrityError:
        return {"cost": sc["cost"], "breakdown": breakdown, "idempotent": True}
    return {"cost": sc["cost"], "breakdown": breakdown, "idempotent": False}


KNOWN_DESC = {"ai_chat": "AI stylist chat"}


def refund_spend(key, reason="Refund", percent=100, ttype="refund"):
    """Return the credits of an earlier spend. Daily Credits are only restored while their period is still open
    (expired Daily Credits are not resurrected)."""
    now = now_utc()
    rows = CreditTransaction.query.filter(CreditTransaction.idempotency_key.like(f"{key}:%"),
                                          CreditTransaction.transaction_type.in_(["spend", "reservation"])).all()
    out = {}
    for r in rows:
        wallet = db.session.get(Wallet, r.wallet_id)
        rkey = f"refund:{r.idempotency_key}"
        if _key_exists(rkey):
            continue
        if r.credit_type == "daily":
            # Only while the very period those credits came from is still open.
            if not wallet.daily_expires_at or wallet.daily_expires_at <= now or r.expires_at != wallet.daily_expires_at:
                continue
        give_back = (-r.amount * percent) // 100  # partial refunds round down
        if give_back <= 0:
            continue
        get_wallet(wallet.user_id)
        after = _apply(wallet, r.credit_type, give_back)
        _ledger(wallet, r.credit_type, ttype, give_back, after, source_type=r.source_type, source_id=r.source_id,
                description=reason, key=rkey)
        out[r.credit_type] = give_back
    return out


# ---- Admin adjustments / reporting ------------------------------------------------------------------
def adjust(actor_id, user_id, ctype, amount, reason):
    """Signed admin correction with a mandatory reason; always audited. Daily adjustments need an open period."""
    if ctype not in ("daily", "super") or not isinstance(amount, int) or amount == 0 or abs(amount) > 100000:
        raise ShopError("Invalid adjustment.", 400)
    if not reason or not reason.strip():
        raise ShopError("A reason is required.", 400)
    if not db.session.get(User, user_id):
        raise ShopError("User not found.", 404)
    wallet = ensure_current(user_id)
    if ctype == "daily" and amount > 0 and (not wallet.daily_expires_at or wallet.daily_expires_at <= now_utc()):
        _p, _s, end = period_for(now_utc())
        wallet.daily_expires_at = end  # extra Daily Credits lapse at the end of the current period
    after = _apply(wallet, ctype, amount)
    if after is None:
        raise ShopError("Adjustment would make the balance negative.", 409)
    row = _ledger(wallet, ctype, "adjustment", amount, after, source_type="admin", source_id=actor_id,
                  description=f"Admin adjustment: {reason.strip()[:180]}", key=None)
    audit(actor_id, "wallet.adjust", "user", user_id, {"credit_type": ctype, "amount": amount, "reason": reason.strip(),
                                                          "transaction_id": row.id})
    return row


def reconcile(wallet):
    """Compare cached balances with the ledger sum. Returns {type: (cached, ledger)} for any mismatch."""
    bad = {}
    for t in ("daily", "super"):
        total = (db.session.query(db.func.coalesce(db.func.sum(CreditTransaction.amount), 0))
                 .filter_by(wallet_id=wallet.id, credit_type=t).scalar())
        cached = getattr(wallet, f"{t}_balance")
        if int(total) != cached:
            bad[t] = (cached, int(total))
    return bad


def wallet_summary(user_id):
    wallet = ensure_current(user_id)
    cfg = get_credit_settings()
    _p, _s, end = period_for(now_utc(), cfg)
    return {
        "daily": {"balance": wallet.daily_balance, "expires_at": wallet.daily_expires_at.isoformat() + "Z"
                  if wallet.daily_expires_at else None, "next_reset_at": end.isoformat() + "Z",
                  "daily_allowance": cfg["daily_allowance"], "timezone": cfg["reset_timezone"]},
        "super": {"balance": wallet.super_balance},
        "spend_priority": cfg["spend_priority"],
    }
