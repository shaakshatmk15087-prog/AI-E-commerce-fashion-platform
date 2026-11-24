from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from marshmallow import ValidationError

from ..extensions import db, limiter
from ..models import CreditPack, CreditTransaction, SubscriptionPlan
from ..services import payment_service, subscription_service, wallet_service
from ..services.errors import ShopError
from ..services.settings_service import KNOWN_SERVICES, get_credit_settings
from ..schemas.wallet import PlanIdSchema, QuoteSchema
from ..utils.auth import current_user

bp = Blueprint("wallet", __name__, url_prefix="/api/v1")


def _load(schema):
    try:
        return schema().load(request.get_json(silent=True) or {}, unknown="raise")
    except ValidationError as e:
        raise ShopError("Validation failed", 400, e.messages)


def _sub_dict(user_id):
    sub = subscription_service.current(user_id)
    return sub.to_dict() if sub else None


@bp.get("/wallet")
@jwt_required()
def get_wallet():
    user = current_user()
    summary = wallet_service.wallet_summary(user.id)  # applies expiry + today's grant
    db.session.commit()
    return jsonify(wallet=summary, subscription=_sub_dict(user.id))


@bp.get("/wallet/transactions")
@jwt_required()
def transactions():
    user = current_user()
    wallet = wallet_service.get_wallet(user.id, lock=False)
    q = CreditTransaction.query.filter_by(wallet_id=wallet.id) if wallet else CreditTransaction.query.filter(False)
    if request.args.get("credit_type") in ("daily", "super"):
        q = q.filter_by(credit_type=request.args["credit_type"])
    try:
        page, per = max(1, int(request.args.get("page", 1))), min(100, max(1, int(request.args.get("per_page", 20))))
    except ValueError:
        page, per = 1, 20
    total = q.count()
    rows = q.order_by(CreditTransaction.id.desc()).offset((page - 1) * per).limit(per).all()
    return jsonify(transactions=[r.to_dict() for r in rows], total=total, page=page, per_page=per)


@bp.get("/wallet/credit-costs")
def credit_costs():
    cfg = get_credit_settings()
    return jsonify(spend_priority=cfg["spend_priority"], services=[
        {"service": k, "label": KNOWN_SERVICES[k], **v} for k, v in cfg["services"].items()])


@bp.post("/wallet/transactions/quote")
@jwt_required()
def quote():
    data = _load(QuoteSchema)
    q = wallet_service.quote(current_user().id, data["service"])
    db.session.commit()
    return jsonify(quote=q)


# ---- Super Credit packs -----------------------------------------------------------------------------
@bp.get("/wallet/packs")
def packs():
    rows = CreditPack.query.filter_by(is_active=True).order_by(CreditPack.price_minor).all()
    return jsonify(packs=[p.to_dict() for p in rows])


@bp.post("/wallet/packs/<int:pack_id>/purchase")
@jwt_required()
@limiter.limit("20/minute")
def purchase_pack(pack_id):
    pack = db.session.get(CreditPack, pack_id)
    if not pack or not pack.is_active:
        raise ShopError("Credit pack not available.", 404)
    user = current_user()
    payment = payment_service.create_payment(
        user.id, pack.price_minor, pack.currency, "credit_pack", reference_id=pack.id,
        meta={"credits": pack.credits, "pack_name": pack.name}, receipt=f"pack-{pack.id}")
    db.session.commit()
    return jsonify(payment=payment_service.payment_dict(payment)), 201


# ---- Subscriptions ----------------------------------------------------------------------------------
@bp.get("/subscriptions/plans")
def plans():
    rows = SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.price_minor).all()
    return jsonify(plans=[p.to_dict() for p in rows])


@bp.post("/subscriptions/checkout")
@jwt_required()
@limiter.limit("20/minute")
def subscription_checkout():
    data = _load(PlanIdSchema)
    user = current_user()
    sub, plan = subscription_service.begin_checkout(user, data["plan_id"])
    payment = payment_service.create_payment(user.id, plan.price_minor, plan.currency, "subscription",
                                             reference_id=sub.id, receipt=f"sub-{sub.id}")
    db.session.commit()
    return jsonify(payment=payment_service.payment_dict(payment)), 201


@bp.get("/subscriptions/me")
@jwt_required()
def my_subscription():
    return jsonify(subscription=_sub_dict(current_user().id))


@bp.post("/subscriptions/cancel")
@jwt_required()
def cancel_subscription():
    sub = subscription_service.cancel(current_user())
    wallet_service.audit(current_user().id, "subscription.cancel", "subscription", sub.id)
    db.session.commit()
    return jsonify(subscription=sub.to_dict())
