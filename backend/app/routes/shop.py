from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from marshmallow import ValidationError

from ..extensions import db, limiter
from ..models import Address, CartItem, Order, Payment, ProductVariant
from ..schemas.shop import (AddressSchema, CartAddSchema, CartUpdateSchema, CheckoutSchema, MockPaySchema, PayOrderSchema)
from ..services import order_service, payment_service
from ..services.errors import ShopError
from ..utils.auth import current_user

bp = Blueprint("shop", __name__, url_prefix="/api/v1")


def load(schema):
    try:
        return schema().load(request.get_json(silent=True) or {}, unknown="raise")
    except ValidationError as e:
        raise ShopError("Validation failed", 400, e.messages)


# ---- Cart -----------------------------------------------------------------------------------
def cart_dict(cart):
    items, subtotal, issues = [], 0, False
    for it in (cart.items if cart else []):
        v = it.variant
        p = v.product
        price = p.effective_price_minor
        ok = p.status == "active" and v.stock_quantity >= it.quantity
        issues = issues or not ok
        subtotal += price * it.quantity if ok else 0
        items.append({
            "id": it.id, "variant_id": v.id, "product_id": p.id, "name": p.name, "brand": p.brand,
            "image": p.images[0].image_url if p.images else None, "size": v.size, "color": v.color,
            "quantity": it.quantity, "unit_price_minor": price, "line_total_minor": price * it.quantity,
            "price_changed": price != it.unit_price_minor, "available": ok, "stock_quantity": v.stock_quantity,
        })
    return {"items": items, "totals": order_service.compute_totals(subtotal) if items else None, "has_issues": issues}


@bp.get("/cart")
@jwt_required()
def get_cart():
    return jsonify(cart=cart_dict(order_service.get_active_cart(current_user().id, create=False)))


@bp.post("/cart/items")
@jwt_required()
def add_to_cart():
    data = load(CartAddSchema)
    v = db.session.get(ProductVariant, data["variant_id"])
    if not v or v.product.status != "active":
        raise ShopError("Product not available.", 404)
    cart = order_service.get_active_cart(current_user().id)
    item = CartItem.query.filter_by(cart_id=cart.id, product_variant_id=v.id).first()
    qty = data["quantity"] + (item.quantity if item else 0)
    if qty > min(10, v.stock_quantity):
        raise ShopError(f"Only {min(10, v.stock_quantity)} available for this size/colour.", 409)
    if item:
        item.quantity = qty
        item.unit_price_minor = v.product.effective_price_minor
    else:
        db.session.add(CartItem(cart_id=cart.id, product_variant_id=v.id, quantity=qty,
                                unit_price_minor=v.product.effective_price_minor))
    db.session.commit()
    return jsonify(cart=cart_dict(cart)), 201


def _own_item(item_id):
    cart = order_service.get_active_cart(current_user().id, create=False)
    item = CartItem.query.filter_by(id=item_id, cart_id=cart.id).first() if cart else None
    if not item:
        raise ShopError("Cart item not found.", 404)
    return cart, item


@bp.patch("/cart/items/<int:item_id>")
@jwt_required()
def update_cart_item(item_id):
    data = load(CartUpdateSchema)
    cart, item = _own_item(item_id)
    limit = min(10, item.variant.stock_quantity)
    if data["quantity"] > limit:
        raise ShopError(f"Only {limit} available.", 409)
    item.quantity = data["quantity"]
    db.session.commit()
    return jsonify(cart=cart_dict(cart))


@bp.delete("/cart/items/<int:item_id>")
@jwt_required()
def delete_cart_item(item_id):
    cart, item = _own_item(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify(cart=cart_dict(cart))


# ---- Addresses ------------------------------------------------------------------------------
@bp.get("/addresses")
@jwt_required()
def list_addresses():
    rows = Address.query.filter_by(user_id=current_user().id, is_deleted=False).order_by(Address.is_default.desc(), Address.id).all()
    return jsonify(addresses=[a.to_dict() for a in rows])


def _set_default(user_id, addr):
    Address.query.filter(Address.user_id == user_id, Address.id != addr.id).update({"is_default": False})
    addr.is_default = True


@bp.post("/addresses")
@jwt_required()
def create_address():
    data = load(AddressSchema)
    u = current_user()
    first = not Address.query.filter_by(user_id=u.id, is_deleted=False).first()
    a = Address(user_id=u.id, **{**data, "is_default": False})
    db.session.add(a)
    db.session.flush()
    if data["is_default"] or first:
        _set_default(u.id, a)
    db.session.commit()
    return jsonify(address=a.to_dict()), 201


@bp.put("/addresses/<int:aid>")
@jwt_required()
def update_address(aid):
    data = load(AddressSchema)
    u = current_user()
    a = Address.query.filter_by(id=aid, user_id=u.id, is_deleted=False).first()
    if not a:
        raise ShopError("Address not found.", 404)
    for k, v in data.items():
        if k != "is_default":
            setattr(a, k, v)
    if data["is_default"]:
        _set_default(u.id, a)
    db.session.commit()
    return jsonify(address=a.to_dict())


@bp.delete("/addresses/<int:aid>")
@jwt_required()
def delete_address(aid):
    a = Address.query.filter_by(id=aid, user_id=current_user().id, is_deleted=False).first()
    if not a:
        raise ShopError("Address not found.", 404)
    a.is_deleted = True  # soft delete: past orders keep their delivery address
    a.is_default = False
    db.session.commit()
    return jsonify(message="Deleted")


# ---- Checkout, orders, payments -------------------------------------------------------------
@bp.post("/checkout")
@jwt_required()
@limiter.limit("20/minute")
def checkout():
    data = load(CheckoutSchema)
    order = order_service.checkout(current_user(), data["address_id"])
    payment = payment_service.create_payment_for_order(order)
    db.session.commit()
    return jsonify(order=order.to_dict(), payment=payment_service.payment_dict(payment)), 201


@bp.get("/orders")
@jwt_required()
def list_orders():
    rows = Order.query.filter_by(user_id=current_user().id).order_by(Order.created_at.desc()).all()
    return jsonify(orders=[o.to_dict(detail=False) for o in rows])


def _own_order(oid):
    o = Order.query.filter_by(id=oid, user_id=current_user().id).first()
    if not o:
        raise ShopError("Order not found.", 404)
    return o


@bp.get("/orders/<int:oid>")
@jwt_required()
def order_detail(oid):
    return jsonify(order=_own_order(oid).to_dict())


@bp.post("/orders/<int:oid>/cancel")
@jwt_required()
def cancel(oid):
    o = Order.query.filter_by(id=oid, user_id=current_user().id).with_for_update().first()
    if not o:
        raise ShopError("Order not found.", 404)
    order_service.cancel_order(o)
    db.session.commit()
    return jsonify(order=o.to_dict())


@bp.post("/payments/create-order")
@jwt_required()
@limiter.limit("20/minute")
def create_payment_order():
    data = load(PayOrderSchema)
    o = Order.query.filter_by(id=data["order_id"], user_id=current_user().id).with_for_update().first()
    if not o:
        raise ShopError("Order not found.", 404)
    if o.order_status != "pending_payment":
        raise ShopError("This order is not awaiting payment.", 409)
    p = payment_service.create_payment_for_order(o)
    db.session.commit()
    return jsonify(payment=payment_service.payment_dict(p))


@bp.post("/payments/webhook")
def webhook():
    # Raw bytes are verified against the provider signature before anything is parsed or trusted.
    result = payment_service.handle_webhook(request.get_data(), request.headers.get("X-Signature", ""))
    return jsonify(result=result)


@bp.post("/payments/mock/pay")
@jwt_required()
def mock_pay():
    """Dev-only stand-in for the gateway checkout page. Disabled unless MOCK_PAYMENTS_ENABLED."""
    if not current_app.config["MOCK_PAYMENTS_ENABLED"] or current_app.config["PAYMENT_PROVIDER"] != "mock":
        raise ShopError("Not found", 404)
    data = load(MockPaySchema)
    if data["order_id"]:
        o = _own_order(data["order_id"])
        p = Payment.query.filter_by(order_id=o.id, status="pending").first()
    else:
        o = None
        p = Payment.query.filter_by(provider_order_id=data["provider_order_id"], user_id=current_user().id,
                                    status="pending").first()
    if not p:
        raise ShopError("No pending payment found.", 409)
    result = payment_service.mock_complete(p, data["outcome"])
    if o:
        db.session.refresh(o)
        return jsonify(result=result, order=o.to_dict())
    db.session.refresh(p)
    return jsonify(result=result, payment=payment_service.payment_dict(p))
