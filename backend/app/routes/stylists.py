from datetime import timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from marshmallow import ValidationError

from ..extensions import db, limiter
from ..models import Consultation, Notification, RewardOffer, RewardTransaction, Stylist, StylistAvailability
from ..schemas.stylist import (BookSchema, MessageSchema, QuoteSlotSchema, ReadSchema, RedeemSchema, SlotSchema,
                               StylistProfileSchema)
from ..services import consultation_service as cs
from ..services import rewards_service, wallet_service
from ..services.errors import ShopError
from ..utils.auth import current_user, roles_required

bp = Blueprint("stylists", __name__, url_prefix="/api/v1")


def _load(schema):
    try:
        return schema().load(request.get_json(silent=True) or {}, unknown="raise")
    except ValidationError as e:
        raise ShopError("Validation failed", 400, e.messages)


def _stylist_card(s):
    d = s.to_dict(price=cs.price_for(s))
    d["next_slots"] = len(cs.open_slots(s))
    return d


# ---- Public directory -----------------------------------------------------------------------------------
@bp.get("/stylists")
def list_stylists():
    rows = Stylist.query.filter_by(is_approved=True, is_available=True).order_by(Stylist.id).all()
    return jsonify(stylists=[_stylist_card(s) for s in rows if cs.bookable(s)])


def _public_stylist(sid):
    s = db.session.get(Stylist, sid)
    if not s or not s.is_approved:
        raise ShopError("Stylist not found.", 404)
    return s


@bp.get("/stylists/<int:sid>")
def stylist_detail(sid):
    return jsonify(stylist=_stylist_card(_public_stylist(sid)))


@bp.get("/stylists/<int:sid>/availability")
def stylist_availability(sid):
    s = _public_stylist(sid)
    return jsonify(slots=[x.to_dict() for x in cs.open_slots(s)] if cs.bookable(s) else [])


# ---- Stylist self-service -------------------------------------------------------------------------------
def _me():
    s = cs.stylist_for_user(current_user().id)
    if not s:
        raise ShopError("No stylist profile for this account.", 404)
    return s


@bp.get("/stylist/profile")
@roles_required("stylist")
def my_profile():
    s = _me()
    return jsonify(stylist=s.to_dict(price=cs.price_for(s)))


@bp.put("/stylist/profile")
@roles_required("stylist")
def update_profile():
    data = _load(StylistProfileSchema)
    s = _me()
    for k, v in data.items():  # approval and pricing are admin-only and never accepted here
        setattr(s, k, v)
    db.session.commit()
    return jsonify(stylist=s.to_dict(price=cs.price_for(s)))


@bp.get("/stylist/availability")
@roles_required("stylist")
def my_slots():
    now = wallet_service.now_utc()
    rows = (StylistAvailability.query.filter(StylistAvailability.stylist_id == _me().id, StylistAvailability.end_at >= now)
            .order_by(StylistAvailability.start_at).all())
    return jsonify(slots=[r.to_dict() for r in rows])


@bp.post("/stylist/availability")
@roles_required("stylist")
def add_slot():
    data = _load(SlotSchema)
    s = _me()
    start = data["start_at"]
    start = start.replace(tzinfo=None) if start.tzinfo is None else start.astimezone(timezone.utc).replace(tzinfo=None)
    end = start + timedelta(minutes=data["duration_minutes"])
    now = wallet_service.now_utc()
    if start <= now:
        raise ShopError("Slots must start in the future.", 400, {"start_at": ["Must be in the future."]})
    if StylistAvailability.query.filter(StylistAvailability.stylist_id == s.id, StylistAvailability.start_at < end,
                                        StylistAvailability.end_at > start).first():
        raise ShopError("That overlaps one of your existing slots.", 409)
    if StylistAvailability.query.filter(StylistAvailability.stylist_id == s.id, StylistAvailability.start_at > now).count() >= 200:
        raise ShopError("You have too many upcoming slots.", 409)
    slot = StylistAvailability(stylist_id=s.id, start_at=start, end_at=end)
    db.session.add(slot)
    db.session.commit()
    return jsonify(slot=slot.to_dict()), 201


@bp.delete("/stylist/availability/<int:slot_id>")
@roles_required("stylist")
def delete_slot(slot_id):
    slot = StylistAvailability.query.filter_by(id=slot_id, stylist_id=_me().id).first()
    if not slot:
        raise ShopError("Slot not found.", 404)
    if slot.status != "open":
        raise ShopError("A booked slot can't be removed. Cancel the consultation instead.", 409)
    db.session.delete(slot)
    db.session.commit()
    return jsonify(message="Removed")


@bp.get("/stylist/earnings")
@roles_required("stylist")
def my_earnings():
    return jsonify(earnings=cs.earnings(_me()))


# ---- Consultations --------------------------------------------------------------------------------------
@bp.post("/consultations/quote")
@jwt_required()
def quote():
    q = cs.quote(current_user(), _load(QuoteSlotSchema)["slot_id"])
    db.session.commit()
    return jsonify(quote=q)


@bp.post("/consultations")
@jwt_required()
@limiter.limit("20/hour")
def book():
    data = _load(BookSchema)
    c = cs.book(current_user(), data["slot_id"], data["notes"])
    db.session.commit()
    return jsonify(consultation=c.to_dict(), credits=wallet_service.wallet_summary(current_user().id)), 201


@bp.get("/consultations")
@jwt_required()
def list_consultations():
    user = current_user()
    if request.args.get("as") == "stylist":
        s = cs.stylist_for_user(user.id)
        q = Consultation.query.filter_by(stylist_id=s.id) if s else Consultation.query.filter(False)
    else:
        q = Consultation.query.filter_by(customer_id=user.id)
    if request.args.get("status"):
        q = q.filter(Consultation.status.in_(request.args["status"].split(",")))
    return jsonify(consultations=[c.to_dict() for c in q.order_by(Consultation.scheduled_start.desc()).limit(100)])


@bp.get("/consultations/<int:cid>")
@jwt_required()
def consultation_detail(cid):
    user = current_user()
    c = db.session.get(Consultation, cid)
    if not c or user.id not in (c.customer_id, c.stylist.user_id) and user.role != "admin":
        raise ShopError("Consultation not found.", 404)
    return jsonify(consultation=c.to_dict(), role="stylist" if user.id == c.stylist.user_id else "customer")


def _action(fn, role=None):
    user = current_user()
    c = fn(user)
    db.session.commit()
    return jsonify(consultation=c.to_dict())


@bp.post("/consultations/<int:cid>/accept")
@roles_required("stylist")
def accept(cid):
    return _action(lambda u: cs.accept(u, cid))


@bp.post("/consultations/<int:cid>/decline")
@roles_required("stylist")
def decline(cid):
    return _action(lambda u: cs.decline(u, cid))


@bp.post("/consultations/<int:cid>/complete")
@roles_required("stylist")
def complete(cid):
    return _action(lambda u: cs.complete(u, cid))


@bp.post("/consultations/<int:cid>/cancel")
@jwt_required()
def cancel(cid):
    return _action(lambda u: cs.cancel(u, cid))


@bp.get("/consultations/<int:cid>/messages")
@jwt_required()
def get_messages(cid):
    try:
        after = int(request.args.get("after", 0))
    except ValueError:
        after = 0
    c, msgs = cs.messages(current_user(), cid, after)
    return jsonify(messages=msgs, status=c.status)


@bp.post("/consultations/<int:cid>/messages")
@jwt_required()
@limiter.limit("60/minute")
def post_message(cid):
    data = _load(MessageSchema)
    text = " ".join(data["text"].split())
    if not text:
        raise ShopError("Validation failed", 400, {"text": ["Please enter a message."]})
    m = cs.post_message(current_user(), cid, text)
    db.session.commit()
    return jsonify(message={"id": m.id, "sender_type": m.sender_type, "text": m.message_text,
                            "created_at": m.created_at.isoformat() + "Z"}), 201


# ---- Notifications --------------------------------------------------------------------------------------
@bp.get("/notifications")
@jwt_required()
def notifications():
    uid = current_user().id
    rows = Notification.query.filter_by(user_id=uid).order_by(Notification.id.desc()).limit(30).all()
    unread = Notification.query.filter_by(user_id=uid, is_read=False).count()
    return jsonify(notifications=[n.to_dict() for n in rows], unread=unread)


@bp.post("/notifications/read")
@jwt_required()
def mark_read():
    data = _load(ReadSchema)
    q = Notification.query.filter_by(user_id=current_user().id, is_read=False)
    if data["ids"]:
        q = q.filter(Notification.id.in_(data["ids"]))
    q.update({"is_read": True}, synchronize_session=False)
    db.session.commit()
    return jsonify(message="ok")


# ---- Rewards --------------------------------------------------------------------------------------------
@bp.get("/rewards/balance")
@jwt_required()
def rewards_balance():
    s = rewards_service.summary(current_user().id)
    db.session.commit()
    return jsonify(rewards=s)


@bp.get("/rewards/transactions")
@jwt_required()
def rewards_transactions():
    try:
        page, per = max(1, int(request.args.get("page", 1))), min(100, max(1, int(request.args.get("per_page", 20))))
    except ValueError:
        page, per = 1, 20
    q = RewardTransaction.query.filter_by(user_id=current_user().id)
    rows = q.order_by(RewardTransaction.id.desc()).offset((page - 1) * per).limit(per).all()
    return jsonify(transactions=[r.to_dict() for r in rows], total=q.count(), page=page, per_page=per)


@bp.get("/rewards/offers")
def rewards_offers():
    rows = RewardOffer.query.filter_by(is_active=True).order_by(RewardOffer.points_cost).all()
    return jsonify(offers=[o.to_dict() for o in rows])


@bp.post("/rewards/redeem")
@jwt_required()
@limiter.limit("20/hour")
def rewards_redeem():
    data = _load(RedeemSchema)
    out = rewards_service.redeem(current_user().id, data["offer_id"])
    db.session.commit()
    return jsonify(redeemed=out), 201
