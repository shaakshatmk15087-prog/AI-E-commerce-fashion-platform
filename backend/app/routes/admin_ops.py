"""Admin operations: users, inventory, refunds, subscriptions, dashboard metrics and CSV reports."""
import csv
import io
from datetime import timedelta

from flask import Blueprint, Response, jsonify, request
from marshmallow import Schema, ValidationError, fields, validate
from sqlalchemy import func

from ..extensions import db
from ..models import (AuditLog, ChatMessage, ChatSession, Consultation, CreditTransaction, Order, OrderItem, Payment, Product,
                      ProductVariant, Refund, User, UserSubscription, Wallet)
from ..services import refund_service, wallet_service
from ..services.errors import ShopError
from ..utils.auth import current_user, roles_required

bp = Blueprint("admin_ops", __name__, url_prefix="/api/v1/admin")
LOW_STOCK = 5


def _load(schema):
    try:
        return schema().load(request.get_json(silent=True) or {}, unknown="raise")
    except ValidationError as e:
        raise ShopError("Validation failed", 400, e.messages)


def _page():
    try:
        return max(1, int(request.args.get("page", 1))), min(200, max(1, int(request.args.get("per_page", 20))))
    except ValueError:
        return 1, 20


# ---- Users ----------------------------------------------------------------------------------------------
@bp.get("/users")
@roles_required("admin")
def list_users():
    q = User.query
    if request.args.get("q"):
        like = "%" + request.args["q"].strip().replace("%", r"\%").replace("_", r"\_") + "%"
        q = q.filter(User.email.ilike(like, escape="\\") | User.name.ilike(like, escape="\\"))
    if request.args.get("role") in ("customer", "stylist", "admin"):
        q = q.filter_by(role=request.args["role"])
    if request.args.get("active") in ("true", "false"):
        q = q.filter_by(is_active=request.args["active"] == "true")
    page, per = _page()
    total = q.count()
    rows = q.order_by(User.id).offset((page - 1) * per).limit(per).all()
    return jsonify(users=[{**u.to_dict(), "is_active": u.is_active, "created_at": u.created_at.isoformat() + "Z"} for u in rows],
                   total=total, page=page, per_page=per)


class UserStateSchema(Schema):
    is_active = fields.Bool(required=True)


@bp.patch("/users/<int:uid>")
@roles_required("admin")
def set_user_state(uid):
    """Deactivate/reactivate an account. Deactivation takes effect immediately: current_user() rejects inactive accounts."""
    data = _load(UserStateSchema)
    me = current_user()
    u = db.session.get(User, uid)
    if not u:
        raise ShopError("User not found.", 404)
    if u.id == me.id:
        raise ShopError("You can't change your own account state.", 409)
    if u.role == "admin" and not data["is_active"] and User.query.filter_by(role="admin", is_active=True).count() <= 1:
        raise ShopError("You can't deactivate the last active administrator.", 409)
    before, u.is_active = u.is_active, data["is_active"]
    wallet_service.audit(me.id, "user.activate" if u.is_active else "user.deactivate", "user", u.id, {"was_active": before, "email": u.email})
    db.session.commit()
    return jsonify(user={**u.to_dict(), "is_active": u.is_active})


# ---- Inventory ------------------------------------------------------------------------------------------
@bp.get("/inventory")
@roles_required("admin")
def inventory():
    q = db.session.query(ProductVariant, Product).join(Product, Product.id == ProductVariant.product_id).filter(Product.status != "archived")
    if request.args.get("q"):
        like = "%" + request.args["q"].strip().replace("%", r"\%").replace("_", r"\_") + "%"
        q = q.filter(Product.name.ilike(like, escape="\\") | ProductVariant.sku.ilike(like, escape="\\"))
    if request.args.get("low") == "true":
        q = q.filter(ProductVariant.stock_quantity <= LOW_STOCK)
    page, per = _page()
    total = q.count()
    rows = q.order_by(ProductVariant.stock_quantity, ProductVariant.id).offset((page - 1) * per).limit(per).all()
    return jsonify(items=[{"variant_id": v.id, "sku": v.sku, "size": v.size, "color": v.color, "stock_quantity": v.stock_quantity,
                           "product_id": p.id, "product": p.name, "status": p.status} for v, p in rows],
                   total=total, page=page, per_page=per, low_stock_threshold=LOW_STOCK)


class StockSchema(Schema):
    stock_quantity = fields.Int(required=True, validate=validate.Range(min=0, max=1_000_000))


@bp.patch("/variants/<int:vid>/stock")
@roles_required("admin")
def set_stock(vid):
    data = _load(StockSchema)
    v = db.session.query(ProductVariant).filter_by(id=vid).with_for_update().first()
    if not v:
        raise ShopError("Variant not found.", 404)
    before, v.stock_quantity = v.stock_quantity, data["stock_quantity"]
    wallet_service.audit(current_user().id, "inventory.set", "variant", v.id, {"sku": v.sku, "before": before, "after": v.stock_quantity})
    db.session.commit()
    return jsonify(variant_id=v.id, stock_quantity=v.stock_quantity)


# ---- Refunds --------------------------------------------------------------------------------------------
class RefundSchema(Schema):
    reason = fields.Str(required=True, validate=validate.Length(min=3, max=255))
    restock = fields.Bool(load_default=None, allow_none=True)


@bp.post("/orders/<int:oid>/refund")
@roles_required("admin")
def refund_order(oid):
    data = _load(RefundSchema)
    r = refund_service.refund_order(current_user().id, oid, data["reason"], data["restock"])
    db.session.commit()
    return jsonify(refund=r.to_dict()), 201


@bp.get("/refunds")
@roles_required("admin")
def list_refunds():
    return jsonify(refunds=[r.to_dict() for r in Refund.query.order_by(Refund.id.desc()).limit(200)])


# ---- Subscriptions (read-only) --------------------------------------------------------------------------
@bp.get("/subscriptions")
@roles_required("admin")
def list_subscriptions():
    rows = (db.session.query(UserSubscription, User).join(User, User.id == UserSubscription.user_id)
            .order_by(UserSubscription.id.desc()).limit(200).all())
    return jsonify(subscriptions=[{**s.to_dict(), "user": {"id": u.id, "email": u.email}} for s, u in rows])


# ---- Dashboard ------------------------------------------------------------------------------------------
def _range():
    try:
        days = min(365, max(1, int(request.args.get("days", 30))))
    except ValueError:
        days = 30
    now = wallet_service.now_utc()
    return days, now - timedelta(days=days), now


@bp.get("/dashboard")
@roles_required("admin")
def dashboard():
    days, since, now = _range()

    paid = (db.session.query(Payment.purpose, func.coalesce(func.sum(Payment.amount_minor), 0), func.count(Payment.id))
            .filter(Payment.status.in_(["paid", "refunded"]), Payment.updated_at >= since).group_by(Payment.purpose).all())
    by_purpose = {p: {"amount_minor": int(a), "count": int(c)} for p, a, c in paid}
    refunded = int(db.session.query(func.coalesce(func.sum(Refund.amount_minor), 0)).filter(Refund.created_at >= since).scalar())
    gross = sum(v["amount_minor"] for v in by_purpose.values())

    status_counts = dict(db.session.query(Order.order_status, func.count(Order.id)).filter(Order.created_at >= since).group_by(Order.order_status).all())
    daily = (db.session.query(func.date(Payment.updated_at), func.count(Payment.id), func.coalesce(func.sum(Payment.amount_minor), 0))
             .filter(Payment.status.in_(["paid", "refunded"]), Payment.updated_at >= since)
             .group_by(func.date(Payment.updated_at)).order_by(func.date(Payment.updated_at)).all())
    top = (db.session.query(OrderItem.product_name_snapshot, func.sum(OrderItem.quantity), func.sum(OrderItem.line_total_minor))
           .join(Order, Order.id == OrderItem.order_id).filter(Order.payment_status == "paid", Order.created_at >= since)
           .group_by(OrderItem.product_id, OrderItem.product_name_snapshot).order_by(func.sum(OrderItem.line_total_minor).desc()).limit(5).all())

    consult = dict(db.session.query(Consultation.status, func.count(Consultation.id)).filter(Consultation.created_at >= since).group_by(Consultation.status).all())
    sub_active = UserSubscription.query.filter(UserSubscription.status == "active", UserSubscription.current_period_end > now).count()
    daily_out, super_out = db.session.query(func.coalesce(func.sum(Wallet.daily_balance), 0), func.coalesce(func.sum(Wallet.super_balance), 0)).one()

    ai = {"messages": 0, "ai_mode": 0, "fallback_mode": 0, "input_tokens": 0, "output_tokens": 0, "truncated": False}
    rows = (db.session.query(ChatMessage.meta).join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .filter(ChatSession.session_type == "ai", ChatMessage.sender_type == "assistant", ChatMessage.created_at >= since)
            .limit(50001).all())
    ai["truncated"] = len(rows) > 50000
    for (meta,) in rows[:50000]:
        meta = meta or {}
        ai["messages"] += 1
        ai["ai_mode" if meta.get("mode") == "ai" else "fallback_mode"] += 1
        ai["input_tokens"] += int(meta.get("input_tokens", 0))
        ai["output_tokens"] += int(meta.get("output_tokens", 0))

    low = (db.session.query(ProductVariant).join(Product)  # 1..threshold: out-of-stock variants are counted separately
           .filter(Product.status == "active", ProductVariant.stock_quantity > 0, ProductVariant.stock_quantity <= LOW_STOCK).count())
    out_of = (db.session.query(ProductVariant).join(Product).filter(Product.status == "active", ProductVariant.stock_quantity == 0).count())

    return jsonify(
        range={"days": days, "since": since.isoformat() + "Z"},
        revenue={"gross_minor": gross, "refunded_minor": refunded, "net_minor": gross - refunded, "by_purpose": by_purpose},
        orders={"by_status": status_counts, "total": sum(status_counts.values())},
        daily=[{"date": str(d), "payments": int(c), "amount_minor": int(a)} for d, c, a in daily],
        top_products=[{"name": n, "units": int(u), "revenue_minor": int(r)} for n, u, r in top],
        users={"customers": User.query.filter_by(role="customer").count(),
               "new": User.query.filter(User.role == "customer", User.created_at >= since).count(),
               "stylists": User.query.filter_by(role="stylist").count()},
        subscriptions={"active": sub_active},
        credits={"daily_outstanding": int(daily_out), "super_outstanding": int(super_out)},
        consultations={"by_status": consult, "total": sum(consult.values())},
        ai=ai, inventory={"low_stock_variants": low, "out_of_stock_variants": out_of, "threshold": LOW_STOCK},
    )


# ---- CSV reports ----------------------------------------------------------------------------------------
def _cell(v):
    """Neutralise spreadsheet formula injection: a cell starting with = + - @ (or tab/CR) is prefixed with a quote."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def _csv_response(name, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow([_cell(c) for c in r])
    return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


MAX_ROWS = 50000


@bp.get("/reports/<name>.csv")
@roles_required("admin")
def report(name):
    days, since, _ = _range()
    if name == "orders":
        rows = Order.query.filter(Order.created_at >= since).order_by(Order.id.desc()).limit(MAX_ROWS).all()
        return _csv_response("orders", ["order_number", "created_at", "order_status", "payment_status", "items", "subtotal", "shipping", "tax", "total"],
                             [[o.order_number, o.created_at.isoformat(), o.order_status, o.payment_status, sum(i.quantity for i in o.items),
                               o.subtotal_minor / 100, o.shipping_minor / 100, o.tax_minor / 100, o.total_minor / 100] for o in rows])
    if name == "payments":
        rows = Payment.query.filter(Payment.updated_at >= since).order_by(Payment.id.desc()).limit(MAX_ROWS).all()
        return _csv_response("payments", ["id", "updated_at", "purpose", "status", "provider", "provider_order_id", "amount", "currency"],
                             [[p.id, p.updated_at.isoformat(), p.purpose, p.status, p.payment_provider, p.provider_order_id, p.amount_minor / 100, p.currency] for p in rows])
    if name == "credits":
        rows = (db.session.query(CreditTransaction, Wallet.user_id).join(Wallet, Wallet.id == CreditTransaction.wallet_id)
                .filter(CreditTransaction.created_at >= since).order_by(CreditTransaction.id.desc()).limit(MAX_ROWS).all())
        return _csv_response("credit_ledger", ["id", "created_at", "user_id", "credit_type", "transaction_type", "amount", "balance_after", "description"],
                             [[t.id, t.created_at.isoformat(), uid, t.credit_type, t.transaction_type, t.amount, t.balance_after, t.description] for t, uid in rows])
    if name == "audit":
        rows = AuditLog.query.filter(AuditLog.created_at >= since).order_by(AuditLog.id.desc()).limit(MAX_ROWS).all()
        return _csv_response("audit_log", ["id", "created_at", "actor_id", "action", "target_type", "target_id", "details"],
                             [[a.id, a.created_at.isoformat(), a.actor_id, a.action, a.target_type, a.target_id, a.details] for a in rows])
    raise ShopError("Unknown report.", 404)
