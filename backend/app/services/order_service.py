import secrets
from datetime import timedelta

from flask import current_app

from ..extensions import db
from ..models import Address, Cart, Order, OrderItem, ProductVariant
from ..models.user import utcnow
from .errors import ShopError


def get_active_cart(user_id, create=True):
    cart = Cart.query.filter_by(user_id=user_id, status="active").first()
    if not cart and create:
        cart = Cart(user_id=user_id)
        db.session.add(cart)
        db.session.flush()
    return cart


def compute_totals(subtotal_minor):
    cfg = current_app.config
    shipping = 0 if subtotal_minor >= cfg["FREE_SHIPPING_THRESHOLD_MINOR"] else cfg["SHIPPING_FLAT_MINOR"]
    discount = 0  # coupons/rewards arrive in later phases
    tax = (subtotal_minor - discount) * cfg["TAX_RATE_BPS"] // 10000  # 0 until the tax policy is decided
    return {"subtotal_minor": subtotal_minor, "discount_minor": discount, "shipping_minor": shipping,
            "tax_minor": tax, "total_minor": subtotal_minor - discount + shipping + tax}


def release_stock(order):
    """Return reserved stock for an order's items (call inside a transaction, order row locked)."""
    ids = sorted(i.product_variant_id for i in order.items)
    variants = {v.id: v for v in ProductVariant.query.filter(ProductVariant.id.in_(ids)).order_by(ProductVariant.id).with_for_update()}
    for it in order.items:
        variants[it.product_variant_id].stock_quantity += it.quantity


def cancel_order(order, reason_status="cancelled"):
    if order.order_status != "pending_payment":
        raise ShopError("Only orders awaiting payment can be cancelled.", 409)
    release_stock(order)
    order.order_status = reason_status


def release_expired_orders(minutes=None):
    """Cancel unpaid orders older than `minutes` and release their stock. Call from the scheduler (Phase 4)."""
    if minutes is None:
        minutes = current_app.config["PENDING_ORDER_MINUTES"]
    cutoff = utcnow() - timedelta(minutes=minutes)
    n = 0
    for o in Order.query.filter(Order.order_status == "pending_payment", Order.created_at < cutoff).with_for_update().all():
        cancel_order(o)
        n += 1
    db.session.commit()
    return n


def _new_order_number():
    return "ORD-" + utcnow().strftime("%y%m%d") + "-" + secrets.token_hex(3).upper()


def checkout(user, address_id):
    """Create a pending order from the cart. Prices/stock come from the DB, never the client.
    Stock is reserved (decremented) now and restored if the order is cancelled/expires."""
    address = Address.query.filter_by(id=address_id, user_id=user.id, is_deleted=False).first()
    if not address:
        raise ShopError("Select a valid delivery address.", 400)

    # A new checkout supersedes the user's earlier unpaid orders (releases their reserved stock).
    for old in Order.query.filter_by(user_id=user.id, order_status="pending_payment").with_for_update().all():
        cancel_order(old)

    cart = get_active_cart(user.id, create=False)
    if not cart or not cart.items:
        raise ShopError("Your cart is empty.", 400)

    ids = sorted(i.product_variant_id for i in cart.items)
    variants = {v.id: v for v in ProductVariant.query.filter(ProductVariant.id.in_(ids)).order_by(ProductVariant.id).with_for_update()}

    problems, lines = [], []
    for it in cart.items:
        v = variants.get(it.product_variant_id)
        p = v.product if v else None
        if not v or p.status != "active":
            problems.append({"variant_id": it.product_variant_id, "problem": "unavailable"})
        elif v.stock_quantity < it.quantity:
            problems.append({"variant_id": v.id, "problem": "insufficient_stock", "available": v.stock_quantity})
        else:
            lines.append((it, v, p))
    if problems:
        raise ShopError("Some items are no longer available in the requested quantity.", 409, problems)

    order = Order(user_id=user.id, address_id=address.id, order_number=_new_order_number(),
                  subtotal_minor=0, total_minor=0, currency="INR")
    subtotal = 0
    for it, v, p in lines:
        price = p.effective_price_minor
        v.stock_quantity -= it.quantity
        subtotal += price * it.quantity
        order.items.append(OrderItem(
            product_id=p.id, product_variant_id=v.id, product_name_snapshot=p.name, sku_snapshot=v.sku,
            size_snapshot=v.size, color_snapshot=v.color, image_snapshot=p.images[0].image_url if p.images else None,
            quantity=it.quantity, unit_price_minor=price, line_total_minor=price * it.quantity))
    for k, val in compute_totals(subtotal).items():
        setattr(order, k, val)
    db.session.add(order)
    db.session.flush()
    return order
