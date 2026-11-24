"""Data-subject features: export everything we hold about a user, and delete (anonymise) an account.

Deletion policy (placeholder, to be confirmed with legal advice): personal data is erased or anonymised; records that other
parties or the business must keep (orders, payments, the credit/points ledgers, consultation records) stay but are no longer
linked to a name, email, phone or address. Remaining credits, points and any active subscription are forfeited (no refund).
Deletion is refused while money or a service is in flight (orders in fulfilment, a pending/accepted consultation).
"""
import secrets

from ..extensions import db
from ..models import (Address, Cart, ChatMessage, ChatSession, Consultation, CreditTransaction, FashionProfile, Notification,
                      Order, RewardTransaction, TokenBlocklist, User, UserSubscription, Wallet, Wishlist)
from . import order_service, wallet_service
from .errors import ShopError

IN_FLIGHT = ("confirmed", "processing", "shipped", "out_for_delivery", "return_requested")


def export_data(user):
    """A machine-readable copy of the user's data (no password hash, no other people's data)."""
    iso = lambda d: d.isoformat() + "Z" if d else None
    fp = FashionProfile.query.filter_by(user_id=user.id).first()
    wallet = Wallet.query.filter_by(user_id=user.id).first()
    sessions = ChatSession.query.filter_by(user_id=user.id).all()
    return {
        "account": {**user.to_dict(), "created_at": iso(user.created_at), "referral_code": user.referral_code},
        "fashion_profile": fp.to_dict() if fp else None,
        "addresses": [a.to_dict() for a in Address.query.filter_by(user_id=user.id, is_deleted=False)],
        "orders": [o.to_dict() for o in Order.query.filter_by(user_id=user.id).order_by(Order.id)],
        "wallet": {"daily_balance": wallet.daily_balance, "super_balance": wallet.super_balance} if wallet else None,
        "credit_transactions": [t.to_dict() for t in CreditTransaction.query.filter_by(wallet_id=wallet.id).order_by(CreditTransaction.id)] if wallet else [],
        "reward_transactions": [t.to_dict() for t in RewardTransaction.query.filter_by(user_id=user.id).order_by(RewardTransaction.id)],
        "subscriptions": [s.to_dict() for s in UserSubscription.query.filter_by(user_id=user.id)],
        "consultations": [c.to_dict() for c in Consultation.query.filter_by(customer_id=user.id)],
        "chats": [{"id": s.id, "type": s.session_type, "title": s.title, "created_at": iso(s.created_at),
                   "messages": [{"from": m.sender_type, "text": m.message_text, "at": iso(m.created_at)} for m in s.messages]}
                  for s in sessions],
        "wishlist_product_ids": [w.product_id for w in Wishlist.query.filter_by(user_id=user.id)],
        "notifications": [n.to_dict() for n in Notification.query.filter_by(user_id=user.id)],
    }


def delete_account(user, password, current_jti=None):
    if user.role != "customer":
        raise ShopError("Stylist and admin accounts can't be self-deleted. Please contact support.", 403)
    if not user.check_password(password or ""):
        raise ShopError("Password is incorrect.", 403)

    if Order.query.filter(Order.user_id == user.id, Order.order_status.in_(IN_FLIGHT)).first():
        raise ShopError("You have orders in progress. Please wait until they are delivered or cancelled.", 409)
    if Consultation.query.filter(Consultation.customer_id == user.id, Consultation.status.in_(["requested", "accepted"])).first():
        raise ShopError("You have an upcoming consultation. Please cancel it first.", 409)

    for o in Order.query.filter_by(user_id=user.id, order_status="pending_payment").with_for_update().all():
        order_service.cancel_order(o)  # releases reserved stock
    wallet_service.get_wallet(user.id)  # takes the wallet row lock: serialises with concurrent credit operations
    for s in UserSubscription.query.filter(UserSubscription.user_id == user.id, UserSubscription.status.in_(["active", "pending", "incomplete"])):
        s.status, s.cancel_at = "cancelled", wallet_service.now_utc()

    # Erase personal data.
    Wishlist.query.filter_by(user_id=user.id).delete()
    Notification.query.filter_by(user_id=user.id).delete()
    FashionProfile.query.filter_by(user_id=user.id).delete()
    for cart in Cart.query.filter_by(user_id=user.id).all():
        db.session.delete(cart)
    for s in ChatSession.query.filter_by(user_id=user.id, session_type="ai").all():
        db.session.delete(s)
    for s in ChatSession.query.filter_by(user_id=user.id, session_type="stylist").all():
        for m in s.messages:
            m.message_text = "[deleted]"
    for c in Consultation.query.filter_by(customer_id=user.id):
        c.customer_notes = None
    for a in Address.query.filter_by(user_id=user.id):  # orders reference addresses, so scrub in place
        a.recipient_name, a.phone, a.address_line_1, a.address_line_2 = "Deleted", "0000000", "Deleted", None
        a.city = a.state = "Deleted"
        a.postal_code, a.is_deleted, a.is_default = "000000", True, False

    old_email = user.email
    user.name, user.email, user.phone, user.referral_code = "Deleted user", f"deleted-{user.id}@deleted.invalid", None, None
    user.set_password(secrets.token_urlsafe(32))  # unusable credential
    user.is_active, user.is_verified = False, False
    if current_jti:
        db.session.add(TokenBlocklist(jti=current_jti))
    wallet_service.audit(user.id, "account.delete", "user", user.id, {"former_email_domain": old_email.split("@")[-1]})
    return user
