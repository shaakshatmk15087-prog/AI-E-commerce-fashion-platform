"""Reward points + referrals.

Points are a third, separate currency: not Daily Credits, not Super Credits, and they carry no cash value. They are earned
only from verified events (a delivered, paid order; a referred friend's first delivered order) and redeemed only through
admin-defined offers (placeholder: Super Credits). Like the wallet, the ledger is append-only, balances move through atomic
conditional updates, and every earn has a unique idempotency key.
"""
import secrets

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Order, Referral, RewardAccount, RewardOffer, RewardTransaction, User
from ..models.user import utcnow
from . import notification_service, wallet_service
from .errors import ShopError
from .settings_service import get_section


def get_account(user_id, lock=True):
    q = RewardAccount.query.filter_by(user_id=user_id)
    acct = (q.with_for_update() if lock else q).first()
    if acct:
        return acct
    try:
        with db.session.begin_nested():
            db.session.add(RewardAccount(user_id=user_id, balance=0))
    except IntegrityError:
        pass
    return (q.with_for_update() if lock else q).first()


def _apply(acct, delta):
    stmt = update(RewardAccount).where(RewardAccount.id == acct.id)
    if delta < 0:
        stmt = stmt.where(RewardAccount.balance >= -delta)
    stmt = stmt.values(balance=RewardAccount.balance + delta).execution_options(synchronize_session=False)
    if db.session.execute(stmt).rowcount != 1:
        return None
    db.session.refresh(acct)
    return acct.balance


def _tx(user_id, ttype, points, after, source_type, source_id, description, key=None):
    row = RewardTransaction(user_id=user_id, transaction_type=ttype, points=points, balance_after=after,
                            source_type=source_type, source_id=str(source_id) if source_id is not None else None,
                            description=description, idempotency_key=key)
    db.session.add(row)
    db.session.flush()
    return row


def earn(user_id, points, source_type, source_id, key, description):
    """Add points once per key. Returns True if newly applied."""
    if points <= 0:
        return False
    acct = get_account(user_id)
    if db.session.query(RewardTransaction.id).filter_by(idempotency_key=key).first():
        return False
    try:
        with db.session.begin_nested():
            after = _apply(acct, points)
            _tx(user_id, "earn", points, after, source_type, source_id, description, key)
    except IntegrityError:
        return False
    notification_service.notify(user_id, "reward", f"You earned {points} reward points", description, "/rewards")
    return True


# ---- Referrals --------------------------------------------------------------------------------------
def ensure_referral_code(user):
    if not user.referral_code:
        for _ in range(10):
            code = secrets.token_urlsafe(6).replace("-", "A").replace("_", "B")[:8].upper()
            if not User.query.filter_by(referral_code=code).first():
                user.referral_code = code
                break
    return user.referral_code


def attach_referral(new_user, code):
    """Link a freshly registered user to a referrer. Invalid/self codes are ignored silently (no code probing)."""
    code = (code or "").strip().upper()
    if not code:
        return None
    referrer = User.query.filter_by(referral_code=code).first()
    if not referrer or referrer.id == new_user.id or not referrer.is_active:
        return None
    try:
        with db.session.begin_nested():
            ref = Referral(referrer_id=referrer.id, referred_id=new_user.id)
            db.session.add(ref)
        return ref
    except IntegrityError:
        return None


def on_order_delivered(order):
    """Qualifying event: a PAID order reached 'delivered'. Awards purchase points and, if this is the customer's first
    delivered order, settles a pending referral for both sides. Idempotent."""
    if order.payment_status != "paid" or order.order_status != "delivered":
        return
    cfg = get_section("rewards")
    pts = (order.total_minor // 10000) * cfg["points_per_100_inr"]
    earn(order.user_id, pts, "order", order.id, f"order:{order.id}:earn", f"Order {order.order_number}")

    ref = Referral.query.filter_by(referred_id=order.user_id, status="pending").with_for_update().first()
    if not ref:
        return
    other = Order.query.filter(Order.user_id == order.user_id, Order.order_status == "delivered", Order.id != order.id).count()
    if other:
        return  # not the first delivered order
    rewarded = Referral.query.filter_by(referrer_id=ref.referrer_id, status="rewarded").count()
    if rewarded >= cfg["max_rewarded_referrals"]:
        ref.status = "capped"
        return
    earn(ref.referrer_id, cfg["referrer_points"], "referral", ref.id, f"referral:{ref.id}:referrer", "A friend you referred completed an order")
    earn(ref.referred_id, cfg["referred_points"], "referral", ref.id, f"referral:{ref.id}:referred", "Welcome bonus for joining through a referral")
    ref.status, ref.rewarded_at = "rewarded", utcnow()


def reverse_order(order):
    """Claw back the purchase points earned on an order that was refunded. Points that were already redeemed cannot be
    recovered, so the reversal is capped at the current balance. Referral bonuses are not reversed (policy undecided)."""
    earned = RewardTransaction.query.filter_by(idempotency_key=f"order:{order.id}:earn").first()
    key = f"order:{order.id}:reversal"
    if not earned or db.session.query(RewardTransaction.id).filter_by(idempotency_key=key).first():
        return 0
    acct = get_account(order.user_id)
    take = min(earned.points, acct.balance)
    if take <= 0:
        return 0
    after = _apply(acct, -take)
    _tx(order.user_id, "reversal", -take, after, "order", order.id, f"Order {order.order_number} refunded", key)
    return take


# ---- Redemption -------------------------------------------------------------------------------------
def redeem(user_id, offer_id):
    offer = db.session.get(RewardOffer, offer_id)
    if not offer or not offer.is_active:
        raise ShopError("Offer not available.", 404)
    acct = get_account(user_id)
    after = _apply(acct, -offer.points_cost)
    if after is None:
        raise ShopError("Not enough reward points.", 402, {"needed": offer.points_cost, "available": acct.balance})
    tx = _tx(user_id, "redeem", -offer.points_cost, after, "offer", offer.id, f"Redeemed: {offer.name}")
    wallet_service.grant(user_id, "super", offer.super_credits, "grant", source_type="reward", source_id=tx.id,
                         key=f"reward-redeem:{tx.id}", description=f"Reward: {offer.name}")
    return {"points_spent": offer.points_cost, "super_credits": offer.super_credits, "balance": after}


def summary(user_id):
    acct = get_account(user_id)
    user = db.session.get(User, user_id)
    code = ensure_referral_code(user)
    refs = Referral.query.filter_by(referrer_id=user_id)
    return {"balance": acct.balance, "referral_code": code,
            "referrals": {"total": refs.count(), "rewarded": refs.filter_by(status="rewarded").count()},
            "rules": get_section("rewards")}


def reconcile(user_id):
    total = (db.session.query(db.func.coalesce(db.func.sum(RewardTransaction.points), 0)).filter_by(user_id=user_id).scalar())
    acct = get_account(user_id, lock=False)
    return {} if int(total) == (acct.balance if acct else 0) else {"cached": acct.balance if acct else 0, "ledger": int(total)}
