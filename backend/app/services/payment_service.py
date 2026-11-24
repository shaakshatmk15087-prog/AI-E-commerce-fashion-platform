"""Payment provider abstraction + idempotent, signature-verified event processing.

The mock provider signs events with HMAC-SHA256 exactly like a real gateway webhook, and the mock "pay"
endpoint feeds them through the same `handle_webhook` path, so the confirm-after-verified-payment logic is
exercised end to end. To add Razorpay: implement a provider with create_order/verify_signature and map its
payload to the event shape in `handle_webhook`.

A payment has a `purpose`: "order" (confirms an order), "credit_pack" (grants Super Credits) or "subscription"
(activates a plan). Fulfilment happens only here, only after signature + amount verification, once per payment.
"""
import hashlib
import hmac
import json
import secrets

from flask import current_app
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Cart, CreditPack, Order, Payment, WebhookEvent
from . import subscription_service, wallet_service
from .errors import ShopError


class MockProvider:
    name = "mock"

    def __init__(self, secret):
        self.secret = secret.encode()

    def create_order(self, amount_minor, currency, receipt):
        return {"id": "mock_order_" + secrets.token_hex(8)}

    def sign(self, raw: bytes) -> str:
        return hmac.new(self.secret, raw, hashlib.sha256).hexdigest()

    def verify_signature(self, raw: bytes, signature: str) -> bool:
        return bool(signature) and hmac.compare_digest(self.sign(raw), signature)

    def refund(self, provider_payment_id, amount_minor, idempotency_key):
        """Return the provider's refund id. A real gateway call must pass `idempotency_key` so a retry cannot refund twice."""
        return {"id": "mock_refund_" + secrets.token_hex(8)}


def get_provider():
    cfg = current_app.config
    if cfg["PAYMENT_PROVIDER"] == "mock":
        return MockProvider(cfg["PAYMENT_WEBHOOK_SECRET"])
    raise RuntimeError("Unsupported payment provider: " + cfg["PAYMENT_PROVIDER"])


def create_payment(user_id, amount_minor, currency, purpose, *, order_id=None, reference_id=None, meta=None, receipt=""):
    provider = get_provider()
    po = provider.create_order(amount_minor, currency, receipt)
    payment = Payment(user_id=user_id, order_id=order_id, payment_provider=provider.name, provider_order_id=po["id"],
                      amount_minor=amount_minor, currency=currency, purpose=purpose, reference_id=reference_id, meta=meta)
    db.session.add(payment)
    db.session.flush()
    return payment


def create_payment_for_order(order):
    """Return the open payment attempt for the order, creating one if needed."""
    existing = Payment.query.filter_by(order_id=order.id, status="pending").first()
    if existing:
        return existing
    return create_payment(order.user_id, order.total_minor, order.currency, "order", order_id=order.id,
                          receipt=order.order_number)


def payment_dict(p):
    return {"provider": p.payment_provider, "provider_order_id": p.provider_order_id, "purpose": p.purpose,
            "amount_minor": p.amount_minor, "currency": p.currency, "status": p.status}


def _fulfil_order(payment, order):
    order.payment_status = "paid"
    if order.order_status == "pending_payment":
        order.order_status = "confirmed"
        cart = Cart.query.filter_by(user_id=order.user_id, status="active").first()
        if cart:
            for it in list(cart.items):
                db.session.delete(it)
    else:
        # Paid after the order was cancelled/expired: needs a manual refund (admin refund flow is later).
        current_app.logger.error("Late payment for non-pending order %s", order.order_number)
    return "paid"


def _fulfil_pack(payment):
    meta = payment.meta or {}
    credits = meta.get("credits")
    if not credits:
        pack = db.session.get(CreditPack, payment.reference_id)
        credits = pack.credits if pack else 0
    if credits <= 0:
        current_app.logger.error("Credit pack payment %s has nothing to grant", payment.id)
        return "nothing_to_grant"
    wallet_service.grant(payment.user_id, "super", credits, "purchase", source_type="payment", source_id=payment.id,
                         key=f"payment:{payment.id}", description=f"Purchased {meta.get('pack_name', 'credit pack')}")
    return "paid"


def handle_webhook(raw: bytes, signature: str):
    """Verify, dedupe, and apply a provider event. Returns a short result string."""
    provider = get_provider()
    if not provider.verify_signature(raw, signature):
        raise ShopError("Invalid signature", 400)
    try:
        event = json.loads(raw)
        event_id, etype, data = event["id"], event["type"], event["data"]
        provider_order_id = data["provider_order_id"]
    except (ValueError, KeyError, TypeError):
        raise ShopError("Malformed event", 400)

    db.session.add(WebhookEvent(provider=provider.name, event_id=str(event_id), event_type=str(etype)))
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return "duplicate"

    payment = Payment.query.filter_by(provider_order_id=provider_order_id).with_for_update().first()
    if not payment:
        db.session.commit()
        return "unknown_payment"
    order = (db.session.query(Order).filter_by(id=payment.order_id).with_for_update().first()
             if payment.purpose == "order" and payment.order_id else None)

    if etype == "payment.captured":
        if payment.status in ("paid", "refunded"):  # a refunded payment must never be re-fulfilled by a late/replayed event
            result = "already_paid"
        elif data.get("amount_minor") != payment.amount_minor or data.get("currency", payment.currency) != payment.currency:
            current_app.logger.error("Payment amount mismatch for %s", provider_order_id)
            result = "amount_mismatch"  # never fulfil on a mismatched amount
        else:
            payment.status = "paid"
            payment.provider_payment_id = data.get("provider_payment_id")
            if payment.purpose == "order" and order:
                result = _fulfil_order(payment, order)
            elif payment.purpose == "credit_pack":
                result = _fulfil_pack(payment)
            elif payment.purpose == "subscription":
                result = subscription_service.activate(payment)
            else:
                result = "ignored"
    elif etype == "payment.failed":
        if payment.status == "pending":
            payment.status = "failed"
            if order and order.payment_status != "paid":
                order.payment_status = "failed"
            if payment.purpose == "subscription":
                subscription_service.mark_failed(payment)
        result = "failed"
    else:
        result = "ignored"
    db.session.commit()
    return result


def mock_complete(payment, outcome):
    """Dev-only: build a signed provider event and process it through the real webhook path."""
    provider = get_provider()
    etype = "payment.captured" if outcome == "success" else "payment.failed"
    event = {"id": "evt_" + secrets.token_hex(8), "type": etype,
             "data": {"provider_order_id": payment.provider_order_id,
                      "provider_payment_id": "mock_pay_" + secrets.token_hex(6),
                      "amount_minor": payment.amount_minor, "currency": payment.currency}}
    raw = json.dumps(event).encode()
    return handle_webhook(raw, provider.sign(raw))
