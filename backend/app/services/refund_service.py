"""Admin-initiated full refund of a paid order.

Policy (placeholder, since the refund/return policy is still an open decision): full refunds only; a refund moves the order
to 'refunded', returns the payment through the provider, restocks goods that never shipped (or any, if the admin says the goods
came back), claws back the purchase points earned, notifies the customer and is audited. Credit-pack and subscription
payments are not refundable here.

Crash safety: the Refund row is flushed *before* the provider call and the provider receives a stable idempotency key
(`refund-<order id>`), so a retry after a crash between "provider refunded" and "database committed" cannot refund twice.
"""
from ..extensions import db
from ..models import Order, Payment, Refund
from . import notification_service, order_service, payment_service, rewards_service, wallet_service
from .errors import ShopError

REFUNDABLE = ("confirmed", "processing", "shipped", "out_for_delivery", "delivered", "cancelled")


def refund_order(admin_id, order_id, reason, restock=None):
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise ShopError("Validation failed", 400, {"reason": ["A reason is required."]})
    order = db.session.query(Order).filter_by(id=order_id).with_for_update().first()
    if not order:
        raise ShopError("Order not found.", 404)
    if Refund.query.filter_by(order_id=order.id).first() or order.payment_status == "refunded":
        raise ShopError("This order has already been refunded.", 409)
    if order.payment_status != "paid" or order.order_status not in REFUNDABLE:
        raise ShopError("Only paid orders can be refunded.", 409)
    payment = Payment.query.filter_by(order_id=order.id, purpose="order", status="paid").first()
    if not payment:
        raise ShopError("No captured payment found for this order.", 409)

    previous_status = order.order_status
    if restock is None:  # sensible default: goods that never left are put back; delivered goods need an explicit decision
        restock = previous_status in ("confirmed", "processing", "shipped", "out_for_delivery")
    if previous_status == "cancelled":
        restock = False  # cancellation already released the stock

    refund = Refund(order_id=order.id, payment_id=payment.id, amount_minor=payment.amount_minor, currency=payment.currency,
                    reason=reason[:255], status="pending", restocked=bool(restock), created_by=admin_id)
    db.session.add(refund)
    db.session.flush()
    try:
        result = payment_service.get_provider().refund(payment.provider_payment_id, payment.amount_minor, f"refund-{order.id}")
    except Exception as e:  # provider failure: nothing is changed
        raise ShopError("The payment provider could not process the refund. Nothing was changed; try again.", 502) from e
    refund.provider_refund_id, refund.status = result["id"], "completed"

    payment.status = "refunded"
    order.payment_status, order.order_status = "refunded", "refunded"
    if restock:
        order_service.release_stock(order)
    clawed_back = rewards_service.reverse_order(order)
    notification_service.notify(order.user_id, "order", "Your order was refunded",
                                f"Order {order.order_number}: {reason[:120]}", f"/orders/{order.id}")
    wallet_service.audit(admin_id, "order.refund", "order", order.id,
                         {"amount_minor": refund.amount_minor, "reason": reason, "from_status": previous_status,
                          "restocked": bool(restock), "points_reversed": clawed_back, "provider_refund_id": result["id"]})
    return refund
