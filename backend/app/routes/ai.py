from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required, verify_jwt_in_request
from flask_limiter.util import get_remote_address
from marshmallow import Schema, ValidationError, fields, validate

from ..extensions import db, limiter
from ..models import ChatMessage, ChatSession, Product, User
import uuid

from ..services import ai_service, wallet_service
from ..services.errors import ShopError
from ..services.recommendation_service import SearchSpec, recommend
from ..utils.auth import current_user

bp = Blueprint("ai", __name__, url_prefix="/api/v1")


def _user_key():
    try:
        verify_jwt_in_request(optional=True)
        ident = get_jwt_identity()
    except Exception:  # invalid token: fall back to IP; the endpoint itself will reject it
        ident = None
    return f"user:{ident}" if ident else get_remote_address()


class ChatSchema(Schema):
    message = fields.Str(required=True)
    session_id = fields.Int(load_default=None)


def _card(product_id, reason, cache):
    p = cache.get(product_id)
    if not p or p.status != "active":
        return None
    d = p.to_dict(detail=False)
    d["reason"] = reason
    return d


def _message_dict(m, cache):
    d = {"id": m.id, "sender_type": m.sender_type, "text": m.message_text, "created_at": m.created_at.isoformat() + "Z"}
    if m.sender_type == "assistant":
        cards = [c for c in (_card(p["id"], p.get("reason"), cache) for p in (m.picks or [])) if c]
        d.update(products=cards, mode=(m.meta or {}).get("mode"), ai_generated=(m.meta or {}).get("mode") == "ai")
    return d


def _product_cache(messages):
    ids = {p["id"] for m in messages for p in (m.picks or [])}
    return {p.id: p for p in Product.query.filter(Product.id.in_(ids))} if ids else {}


def _own_session(sid):
    s = ChatSession.query.filter_by(id=sid, user_id=current_user().id, session_type="ai").first()
    if not s:
        raise ShopError("Chat not found.", 404)
    return s


@bp.post("/ai/chat")
@limiter.limit("15/minute", key_func=_user_key)
@jwt_required()
def chat():
    try:
        data = ChatSchema().load(request.get_json(silent=True) or {}, unknown="raise")
    except ValidationError as e:
        raise ShopError("Validation failed", 400, e.messages)
    text = " ".join(data["message"].split())
    limit = current_app.config["AI_MAX_MESSAGE_CHARS"]
    if not text:
        raise ShopError("Validation failed", 400, {"message": ["Please enter a message."]})
    if len(text) > limit:
        raise ShopError("Validation failed", 400, {"message": [f"Please keep messages under {limit} characters."]})

    user = current_user()
    midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    used = (ChatMessage.query.join(ChatSession).filter(ChatSession.user_id == user.id, ChatMessage.sender_type == "user",
                                                       ChatMessage.created_at >= midnight).count())
    if used >= current_app.config["AI_DAILY_MESSAGE_LIMIT"]:
        raise ShopError("You've reached today's AI stylist limit. It resets at midnight UTC.", 429)

    if data["session_id"]:
        session = _own_session(data["session_id"])
    else:
        session = ChatSession(user_id=user.id, session_type="ai", title=text[:60])
        db.session.add(session)
        db.session.flush()
    history = list(session.messages)

    # Credits: charge first (402 if insufficient), refund below if the AI was not actually used. Cost is an
    # admin setting and currently 0 (free) until the business decides.
    spend_key = f"ai_chat:{user.id}:{uuid.uuid4().hex}"
    charge = wallet_service.spend(user.id, "ai_chat", source_type="ai_chat", source_id=session.id, key=spend_key)

    result = ai_service.respond(user.id, history, text)  # LLM calls happen here
    credits = {"charged": charge["breakdown"], "refunded": {}}
    # Charged only when the AI actually delivered recommendations (not for fallbacks, clarifying questions or no results).
    if charge["breakdown"] and (result["meta"].get("mode") != "ai" or not result["picks"]):
        credits["refunded"] = wallet_service.refund_spend(spend_key, "Refund: no AI recommendations delivered")
        credits["charged"] = {}
    result["meta"]["credits"] = credits

    db.session.add(ChatMessage(session_id=session.id, sender_type="user", message_text=text, picks=[]))
    reply = ChatMessage(session_id=session.id, sender_type="assistant", message_text=result["text"],
                        picks=result["picks"], meta=result["meta"])
    db.session.add(reply)
    session.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    return jsonify(session_id=session.id, message=_message_dict(reply, _product_cache([reply])), credits=credits,
                   remaining_today=max(0, current_app.config["AI_DAILY_MESSAGE_LIMIT"] - used - 1)), 201


@bp.get("/ai/sessions")
@jwt_required()
def list_sessions():
    rows = (ChatSession.query.filter_by(user_id=current_user().id, session_type="ai")
            .order_by(ChatSession.updated_at.desc()).limit(50).all())
    return jsonify(sessions=[{"id": s.id, "title": s.title, "updated_at": s.updated_at.isoformat() + "Z"} for s in rows])


@bp.get("/ai/sessions/<int:sid>")
@jwt_required()
def get_session(sid):
    s = _own_session(sid)
    cache = _product_cache(s.messages)
    return jsonify(session={"id": s.id, "title": s.title}, messages=[_message_dict(m, cache) for m in s.messages])


@bp.delete("/ai/sessions/<int:sid>")
@jwt_required()
def delete_session(sid):
    db.session.delete(_own_session(sid))
    db.session.commit()
    return jsonify(message="Deleted")


@bp.get("/recommendations")
def recommendations():
    """Personalised (when signed in) rule-based picks from the fashion profile; no LLM involved."""
    try:
        verify_jwt_in_request(optional=True)
        ident = get_jwt_identity()
    except Exception:
        ident = None
    user = db.session.get(User, int(ident)) if ident else None
    if user is not None and not user.is_active:
        user = None  # a deactivated account gets the anonymous view, never its profile
    ranked, _ = recommend(SearchSpec(), user_id=user.id if user else None, limit=8)
    out = []
    for r in ranked:
        d = r.product.to_dict(detail=False)
        d["reason"] = "; ".join(r.reasons[:2]) or None
        out.append(d)
    return jsonify(products=out, personalized=user is not None)
