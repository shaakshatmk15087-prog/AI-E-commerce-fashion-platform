"""Stylist consultations: booking, lifecycle, credit reservation/release and settlement.

Credit flow (all placeholder policy, admin-configurable in the 'consultations' settings):
  book      -> the slot is claimed with an atomic conditional UPDATE and the price is RESERVED (debited, ledger type
               'reservation'). Super-only by default, so Daily Credits can't lapse before the session happens.
  decline / stylist cancel / expiry      -> full release.
  customer cancel while still requested  -> full release; after acceptance: full release if at least
               `cancel_full_refund_hours` before the start, otherwise `late_cancel_refund_percent` (rounded down).
  complete (stylist, only once the start time has arrived) -> settlement: the reservation stays spent and the stylist's
               share is recorded on the consultation as earnings (a record; no money moves here).
"""
from datetime import timedelta

from sqlalchemy import update

from ..extensions import db
from ..models import ChatMessage, ChatSession, Consultation, Stylist, StylistAvailability
from . import notification_service, wallet_service
from .errors import ShopError
from .settings_service import get_credit_settings, get_section

SERVICE = "consultation_text"
ACTIVE = ("requested", "accepted")


def price_for(stylist):
    if stylist.price_credits_text is not None:
        return stylist.price_credits_text
    return get_credit_settings()["services"][SERVICE]["cost"]


def stylist_for_user(user_id):
    return Stylist.query.filter_by(user_id=user_id).first()


def bookable(stylist):
    return stylist.is_approved and stylist.is_available and "text" in (stylist.consultation_types or [])


def open_slots(stylist, now=None):
    now = now or wallet_service.now_utc()
    notice = timedelta(hours=get_section("consultations")["min_notice_hours"])
    return (StylistAvailability.query.filter(StylistAvailability.stylist_id == stylist.id, StylistAvailability.status == "open",
                                             StylistAvailability.start_at >= now + notice)
            .order_by(StylistAvailability.start_at).limit(100).all())


def _release_slot(c, now):
    if c.slot_id and c.scheduled_start > now:
        db.session.execute(update(StylistAvailability).where(StylistAvailability.id == c.slot_id)
                           .values(status="open").execution_options(synchronize_session=False))


def _refund(c, percent, reason):
    out = wallet_service.refund_spend(f"consult:{c.id}", reason, percent=percent, ttype="release")
    c.refunded_credits = sum(out.values())


def quote(customer, slot_id):
    slot = db.session.get(StylistAvailability, slot_id) or _missing("Slot")
    stylist = db.session.get(Stylist, slot.stylist_id)
    cost = price_for(stylist)
    q = wallet_service.quote(customer.id, SERVICE, cost_override=cost)
    cfg = get_section("consultations")
    q["policy"] = {"full_refund_hours": cfg["cancel_full_refund_hours"], "late_refund_percent": cfg["late_cancel_refund_percent"],
                   "request_expiry_hours": cfg["request_expiry_hours"]}
    q["stylist"] = stylist.user.name
    q["slot"] = slot.to_dict()
    return q


def _missing(what):
    raise ShopError(f"{what} not found.", 404)


def book(customer, slot_id, notes=None):
    if customer.role != "customer":
        raise ShopError("Only customer accounts can book consultations.", 403)
    now = wallet_service.now_utc()
    slot = db.session.get(StylistAvailability, slot_id) or _missing("Slot")
    stylist = db.session.get(Stylist, slot.stylist_id)
    if not bookable(stylist):
        raise ShopError("This stylist is not accepting bookings.", 409)
    if slot.start_at < now + timedelta(hours=get_section("consultations")["min_notice_hours"]):
        raise ShopError("This slot starts too soon to be booked.", 409)
    cost = price_for(stylist)

    # Claim the slot atomically: of two simultaneous bookings exactly one gets rowcount 1.
    claimed = db.session.execute(update(StylistAvailability).where(StylistAvailability.id == slot.id,
                                                                    StylistAvailability.status == "open")
                                 .values(status="booked").execution_options(synchronize_session=False)).rowcount
    if claimed != 1:
        raise ShopError("That slot was just taken. Please choose another time.", 409)

    c = Consultation(customer_id=customer.id, stylist_id=stylist.id, slot_id=slot.id, consultation_type="text",
                     scheduled_start=slot.start_at, scheduled_end=slot.end_at, credit_cost=cost,
                     customer_notes=(notes or "").strip()[:500] or None, created_at=now)
    db.session.add(c)
    db.session.flush()
    # Raises InsufficientCredits (402); the caller's rollback un-claims the slot.
    wallet_service.spend(customer.id, SERVICE, source_type="consultation", source_id=c.id, key=f"consult:{c.id}",
                         description=f"Consultation with {stylist.user.name}", ttype="reservation", cost_override=cost)
    notification_service.notify(stylist.user_id, "consultation", "New consultation request",
                                f"{customer.name} requested a session on {slot.start_at:%d %b %H:%M} UTC.", f"/stylist/consultations/{c.id}")
    return c


def _locked(cid):
    c = db.session.query(Consultation).filter_by(id=cid).with_for_update().first()
    if not c:
        raise ShopError("Consultation not found.", 404)
    return c


def _own_as_stylist(user, cid):
    c = _locked(cid)
    if c.stylist.user_id != user.id:
        raise ShopError("Consultation not found.", 404)
    return c


def accept(user, cid):
    c = _own_as_stylist(user, cid)
    now = wallet_service.now_utc()
    if c.status != "requested":
        raise ShopError(f"This request is already {c.status}.", 409)
    if c.scheduled_start <= now:
        raise ShopError("This session's start time has passed.", 409)
    c.status, c.accepted_at = "accepted", now
    if not ChatSession.query.filter_by(consultation_id=c.id).first():
        db.session.add(ChatSession(user_id=c.customer_id, session_type="stylist", consultation_id=c.id,
                                   title=f"Consultation with {c.stylist.user.name}"))
    notification_service.notify(c.customer_id, "consultation", "Your consultation was accepted",
                                f"{c.stylist.user.name} confirmed your session.", f"/consultations/{c.id}")
    return c


def decline(user, cid):
    c = _own_as_stylist(user, cid)
    if c.status != "requested":
        raise ShopError(f"This request is already {c.status}.", 409)
    now = wallet_service.now_utc()
    c.status, c.cancelled_by = "declined", "stylist"
    _refund(c, 100, "Refund: stylist declined")
    _release_slot(c, now)
    notification_service.notify(c.customer_id, "consultation", "Consultation declined",
                                "Your credits were returned in full.", f"/consultations/{c.id}")
    return c


def cancel(user, cid):
    c = _locked(cid)
    now = wallet_service.now_utc()
    is_customer, is_stylist = c.customer_id == user.id, c.stylist.user_id == user.id
    if not (is_customer or is_stylist):
        raise ShopError("Consultation not found.", 404)
    if c.status not in ACTIVE:
        raise ShopError(f"This consultation is already {c.status}.", 409)
    cfg = get_section("consultations")
    if is_stylist or c.status == "requested":
        percent = 100
    elif c.scheduled_start - now >= timedelta(hours=cfg["cancel_full_refund_hours"]):
        percent = 100
    else:
        percent = cfg["late_cancel_refund_percent"]
    c.status, c.cancelled_by = "cancelled", "stylist" if is_stylist else "customer"
    _refund(c, percent, f"Refund: cancelled by {c.cancelled_by} ({percent}%)")
    _release_slot(c, now)
    other = c.customer_id if is_stylist else c.stylist.user_id
    notification_service.notify(other, "consultation", "Consultation cancelled",
                                f"Cancelled by the {c.cancelled_by}." + (f" {c.refunded_credits} credits refunded." if not is_stylist else ""),
                                f"/consultations/{c.id}")
    return c


def complete(user, cid):
    c = _own_as_stylist(user, cid)
    now = wallet_service.now_utc()
    if c.status != "accepted":
        raise ShopError("Only accepted consultations can be completed.", 409)
    if now < c.scheduled_start:
        raise ShopError("A consultation can't be completed before its start time.", 409)
    share = get_section("consultations")["stylist_share_percent"]
    c.status, c.completed_at = "completed", now
    c.stylist_payout_credits = (c.credit_cost * share) // 100
    notification_service.notify(c.customer_id, "consultation", "Consultation completed",
                                "Thanks for booking. Your styling notes are in the chat.", f"/consultations/{c.id}")
    return c


# ---- Messages -----------------------------------------------------------------------------------------
def _participant(user, cid):
    c = db.session.get(Consultation, cid) or _missing("Consultation")
    if user.id not in (c.customer_id, c.stylist.user_id) and user.role != "admin":
        raise ShopError("Consultation not found.", 404)
    return c


def messages(user, cid, after=0):
    c = _participant(user, cid)
    sess = ChatSession.query.filter_by(consultation_id=c.id).first()
    rows = (ChatMessage.query.filter(ChatMessage.session_id == sess.id, ChatMessage.id > after).order_by(ChatMessage.id).limit(200).all()
            if sess else [])
    return c, [{"id": m.id, "sender_type": m.sender_type, "text": m.message_text, "created_at": m.created_at.isoformat() + "Z"} for m in rows]


def post_message(user, cid, text):
    c = _participant(user, cid)
    if user.role == "admin":
        raise ShopError("Admins can read but not post in consultations.", 403)
    if c.status != "accepted":
        raise ShopError("Chat opens once the stylist accepts and closes when the consultation ends.", 409)
    sess = ChatSession.query.filter_by(consultation_id=c.id).first()
    sender = "customer" if user.id == c.customer_id else "stylist"
    m = ChatMessage(session_id=sess.id, sender_type=sender, message_text=text, picks=[])
    db.session.add(m)
    db.session.flush()
    other = c.stylist.user_id if sender == "customer" else c.customer_id
    notification_service.notify(other, "message", "New message in your consultation", text[:100], f"/consultations/{c.id}",
                                dedupe_key=None)
    return m


# ---- Scheduled maintenance ------------------------------------------------------------------------------
def expire_stale(now=None):
    """Unanswered requests (too old, or whose start time has passed) expire with a full release."""
    now = now or wallet_service.now_utc()
    cutoff = now - timedelta(hours=get_section("consultations")["request_expiry_hours"])
    n = 0
    for c in (db.session.query(Consultation).filter(Consultation.status == "requested",
                                                    (Consultation.created_at < cutoff) | (Consultation.scheduled_start <= now))
              .with_for_update().all()):
        c.status, c.cancelled_by = "expired", "system"
        _refund(c, 100, "Refund: request not answered in time")
        _release_slot(c, now)
        notification_service.notify(c.customer_id, "consultation", "Request expired",
                                    "The stylist didn't respond in time. Your credits were returned.", f"/consultations/{c.id}")
        n += 1
    return n


def send_reminders(now=None):
    now = now or wallet_service.now_utc()
    horizon = now + timedelta(minutes=get_section("consultations")["reminder_minutes"])
    n = 0
    for c in Consultation.query.filter(Consultation.status == "accepted", Consultation.scheduled_start > now,
                                       Consultation.scheduled_start <= horizon).all():
        for uid in (c.customer_id, c.stylist.user_id):
            made = notification_service.notify(uid, "reminder", "Consultation starting soon",
                                               f"Starts at {c.scheduled_start:%H:%M} UTC.",
                                               f"/consultations/{c.id}" if uid == c.customer_id else f"/stylist/consultations/{c.id}",
                                               dedupe_key=f"consult:{c.id}:reminder:{uid}")
            n += 1 if made else 0
    return n


def earnings(stylist):
    rows = Consultation.query.filter_by(stylist_id=stylist.id).all()
    done = [c for c in rows if c.status == "completed"]
    return {"completed": len(done), "earned_credits": sum(c.stylist_payout_credits or 0 for c in done),
            "upcoming": sum(1 for c in rows if c.status == "accepted"), "pending_requests": sum(1 for c in rows if c.status == "requested"),
            "share_percent": get_section("consultations")["stylist_share_percent"],
            "history": [{"id": c.id, "date": c.completed_at.isoformat() + "Z", "credits": c.stylist_payout_credits}
                        for c in sorted(done, key=lambda c: c.completed_at, reverse=True)[:50]]}
