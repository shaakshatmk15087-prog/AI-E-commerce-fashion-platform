import json

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import Category, Product, ProductVariant, User
from app.services import order_service, payment_service


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_user(client, email, admin=False):
    r = client.post("/api/v1/auth/register", json={"name": "U", "email": email, "password": "Passw0rdX"})
    if admin:
        User.query.filter_by(email=email).update({"role": "admin"})
        db.session.commit()
    return {"Authorization": f"Bearer {r.json['access_token']}"}


def product_body(cat_id, sku="TS-1", price=50000, sale=None, stock=5, name="Cotton Tee", **kw):
    return {"category_id": cat_id, "name": name, "brand": "Acme", "price_minor": price, "sale_price_minor": sale,
            "description": "Soft tee", "tags": ["casual"],
            "variants": [{"sku": sku, "size": "M", "color": "black", "stock_quantity": stock},
                         {"sku": sku + "-L", "size": "L", "color": "white", "stock_quantity": stock}],
            "images": [{"image_url": "https://example.com/a.jpg"}], **kw}


@pytest.fixture()
def seeded(client):
    admin = make_user(client, "admin@example.com", admin=True)
    cat = client.post("/api/v1/admin/categories", json={"name": "Tops"}, headers=admin).json["category"]
    p = client.post("/api/v1/admin/products", json=product_body(cat["id"]), headers=admin).json["product"]
    return {"admin": admin, "cat": cat, "product": p, "variant": p["variants"][0]}


def address(client, h):
    return client.post("/api/v1/addresses", headers=h, json={
        "recipient_name": "R", "phone": "9999999999", "address_line_1": "1 Street",
        "city": "Pune", "state": "MH", "postal_code": "411001"}).json["address"]


def add(client, h, variant_id, qty=1):
    return client.post("/api/v1/cart/items", json={"variant_id": variant_id, "quantity": qty}, headers=h)


def stock(variant_id):
    db.session.expire_all()
    return db.session.get(ProductVariant, variant_id).stock_quantity


def start_checkout(client, h, seeded, qty=2):
    add(client, h, seeded["variant"]["id"], qty)
    return client.post("/api/v1/checkout", json={"address_id": address(client, h)["id"]}, headers=h)


# ---- admin / catalogue --------------------------------------------------------------------------
def test_customer_cannot_manage_products(client, seeded):
    c = make_user(client, "c@example.com")
    assert client.post("/api/v1/admin/products", json=product_body(seeded["cat"]["id"], "X"), headers=c).status_code == 403
    assert client.get("/api/v1/admin/orders", headers=c).status_code == 403


def test_product_validation(client, seeded):
    a = seeded["admin"]
    bad = product_body(seeded["cat"]["id"], "Z", price=1000, sale=2000)
    assert client.post("/api/v1/admin/products", json=bad, headers=a).status_code == 400
    dup = product_body(seeded["cat"]["id"], "TS-1")
    assert client.post("/api/v1/admin/products", json=dup, headers=a).status_code == 400  # SKU exists
    js = product_body(seeded["cat"]["id"], "J1", images=[{"image_url": "javascript:alert(1)"}])
    assert client.post("/api/v1/admin/products", json=js, headers=a).status_code == 400


def test_search_filter_sort_and_visibility(client, seeded):
    a, cid = seeded["admin"], seeded["cat"]["id"]
    client.post("/api/v1/admin/products", headers=a, json=product_body(cid, "SH-1", price=90000, sale=70000, name="Linen Shirt"))
    client.post("/api/v1/admin/products", headers=a, json=product_body(cid, "DR-1", name="Draft Item", status="draft"))
    names = lambda r: [p["name"] for p in r.json["products"]]
    assert "Draft Item" not in names(client.get("/api/v1/products"))
    assert names(client.get("/api/v1/products?q=linen")) == ["Linen Shirt"]
    assert names(client.get("/api/v1/products?sort=price_asc"))[0] == "Cotton Tee"      # 500 < 700 sale price
    assert names(client.get("/api/v1/products?max_price=60000")) == ["Cotton Tee"]
    assert len(names(client.get("/api/v1/products?size=L&color=white"))) == 2
    assert names(client.get("/api/v1/products?size=XXL")) == []
    assert client.get(f"/api/v1/products/{seeded['product']['id'] + 2}").status_code == 404  # draft hidden


# ---- cart ---------------------------------------------------------------------------------------
def test_cart_limits_and_isolation(client, seeded):
    h1, h2 = make_user(client, "u1@example.com"), make_user(client, "u2@example.com")
    vid = seeded["variant"]["id"]
    assert add(client, h1, vid, 3).status_code == 201
    assert add(client, h1, vid, 3).status_code == 409          # 6 > stock 5
    assert add(client, h1, 9999).status_code == 404
    item = client.get("/api/v1/cart", headers=h1).json["cart"]["items"][0]
    assert client.patch(f"/api/v1/cart/items/{item['id']}", json={"quantity": 2}, headers=h2).status_code == 404
    assert client.patch(f"/api/v1/cart/items/{item['id']}", json={"quantity": 2}, headers=h1).status_code == 200
    assert client.get("/api/v1/cart").status_code == 401


# ---- checkout / payment -------------------------------------------------------------------------
def test_checkout_uses_server_prices_and_reserves_stock(client, seeded):
    h = make_user(client, "buyer@example.com")
    add(client, h, seeded["variant"]["id"], 2)
    r = client.post("/api/v1/checkout", headers=h, json={"address_id": address(client, h)["id"]})
    assert r.status_code == 201
    o = r.json["order"]
    assert o["subtotal_minor"] == 100000 and o["shipping_minor"] == 0       # >= free-shipping threshold
    assert o["total_minor"] == 100000 and o["order_status"] == "pending_payment" and o["payment_status"] == "pending"
    assert stock(seeded["variant"]["id"]) == 3
    # client-supplied prices are rejected outright
    bad = client.post("/api/v1/checkout", headers=h, json={"address_id": 1, "total_minor": 1})
    assert bad.status_code == 400


def test_shipping_charged_below_threshold(client, seeded):
    h = make_user(client, "b2@example.com")
    r = start_checkout(client, h, seeded, qty=1)
    assert r.json["order"]["shipping_minor"] == 9900 and r.json["order"]["total_minor"] == 59900


def test_payment_success_confirms_once_and_clears_cart(client, seeded):
    h = make_user(client, "pay@example.com")
    oid = start_checkout(client, h, seeded).json["order"]["id"]
    r = client.post("/api/v1/payments/mock/pay", json={"order_id": oid, "outcome": "success"}, headers=h)
    assert r.json["result"] == "paid" and r.json["order"]["order_status"] == "confirmed"
    assert client.get("/api/v1/cart", headers=h).json["cart"]["items"] == []
    assert client.post("/api/v1/payments/mock/pay", json={"order_id": oid, "outcome": "success"}, headers=h).status_code == 409


def test_failed_payment_does_not_confirm_and_can_retry(client, seeded):
    h = make_user(client, "fail@example.com")
    oid = start_checkout(client, h, seeded).json["order"]["id"]
    r = client.post("/api/v1/payments/mock/pay", json={"order_id": oid, "outcome": "failure"}, headers=h)
    assert r.json["order"]["order_status"] == "pending_payment" and r.json["order"]["payment_status"] == "failed"
    assert client.post("/api/v1/payments/create-order", json={"order_id": oid}, headers=h).status_code == 200
    r = client.post("/api/v1/payments/mock/pay", json={"order_id": oid, "outcome": "success"}, headers=h)
    assert r.json["order"]["order_status"] == "confirmed"


def _event(payment, etype="payment.captured", amount=None, eid="evt_1"):
    return json.dumps({"id": eid, "type": etype, "data": {
        "provider_order_id": payment.provider_order_id, "provider_payment_id": "p1",
        "amount_minor": amount if amount is not None else payment.amount_minor, "currency": "INR"}}).encode()


def test_webhook_signature_idempotency_and_amount(client, app, seeded):
    from app.models import Payment
    h = make_user(client, "wh@example.com")
    oid = start_checkout(client, h, seeded).json["order"]["id"]
    pay = Payment.query.filter_by(order_id=oid).first()
    sign = payment_service.get_provider().sign

    raw = _event(pay)
    assert client.post("/api/v1/payments/webhook", data=raw, headers={"X-Signature": "bad"}).status_code == 400
    assert client.post("/api/v1/payments/webhook", data=raw).status_code == 400
    db.session.expire_all()
    assert client.get(f"/api/v1/orders/{oid}", headers=h).json["order"]["payment_status"] == "pending"

    wrong = _event(pay, amount=1, eid="evt_wrong")
    assert client.post("/api/v1/payments/webhook", data=wrong, headers={"X-Signature": sign(wrong)}).json["result"] == "amount_mismatch"
    assert client.get(f"/api/v1/orders/{oid}", headers=h).json["order"]["order_status"] == "pending_payment"

    assert client.post("/api/v1/payments/webhook", data=raw, headers={"X-Signature": sign(raw)}).json["result"] == "paid"
    assert client.post("/api/v1/payments/webhook", data=raw, headers={"X-Signature": sign(raw)}).json["result"] == "duplicate"
    dup2 = _event(pay, eid="evt_2")  # same payment, new event id: must not double-process
    assert client.post("/api/v1/payments/webhook", data=dup2, headers={"X-Signature": sign(dup2)}).json["result"] == "already_paid"
    assert client.get(f"/api/v1/orders/{oid}", headers=h).json["order"]["order_status"] == "confirmed"


def test_oversell_blocked_and_cancel_releases_stock(client, seeded):
    vid = seeded["variant"]["id"]
    h1, h2 = make_user(client, "o1@example.com"), make_user(client, "o2@example.com")
    o1 = start_checkout(client, h1, seeded, qty=4).json["order"]
    assert stock(vid) == 1
    assert add(client, h2, vid, 2).status_code == 409            # cart add respects remaining stock
    # simulate a cart that became stale after someone else reserved stock
    add(client, h2, vid, 1)
    db.session.query(ProductVariant).filter_by(id=vid).update({"stock_quantity": 0})
    db.session.commit()
    r = client.post("/api/v1/checkout", headers=h2, json={"address_id": address(client, h2)["id"]})
    assert r.status_code == 409 and r.json["details"][0]["problem"] == "insufficient_stock"
    db.session.query(ProductVariant).filter_by(id=vid).update({"stock_quantity": 1})
    db.session.commit()
    assert client.post(f"/api/v1/orders/{o1['id']}/cancel", headers=h1).status_code == 200
    assert stock(vid) == 5


def test_new_checkout_supersedes_pending_order(client, seeded):
    h = make_user(client, "sup@example.com")
    first = start_checkout(client, h, seeded, qty=2).json["order"]
    assert stock(seeded["variant"]["id"]) == 3
    second = client.post("/api/v1/checkout", headers=h, json={"address_id": address(client, h)["id"]}).json["order"]
    assert stock(seeded["variant"]["id"]) == 3                      # not double-reserved
    assert client.get(f"/api/v1/orders/{first['id']}", headers=h).json["order"]["order_status"] == "cancelled"
    assert second["order_status"] == "pending_payment"


def test_expired_pending_orders_release_stock(client, app, seeded):
    h = make_user(client, "exp@example.com")
    start_checkout(client, h, seeded, qty=2)
    assert order_service.release_expired_orders(minutes=0) == 1
    assert stock(seeded["variant"]["id"]) == 5


def test_orders_are_private_and_admin_fulfilment(client, seeded):
    h1, h2 = make_user(client, "p1@example.com"), make_user(client, "p2@example.com")
    oid = start_checkout(client, h1, seeded).json["order"]["id"]
    assert client.get(f"/api/v1/orders/{oid}", headers=h2).status_code == 404
    a = seeded["admin"]
    assert client.patch(f"/api/v1/admin/orders/{oid}/status", json={"order_status": "shipped"}, headers=a).status_code == 409  # unpaid
    client.post("/api/v1/payments/mock/pay", json={"order_id": oid, "outcome": "success"}, headers=h1)
    assert client.patch(f"/api/v1/admin/orders/{oid}/status", json={"order_status": "shipped"}, headers=a).status_code == 409  # skip step
    assert client.patch(f"/api/v1/admin/orders/{oid}/status", json={"order_status": "processing"}, headers=a).status_code == 200


def test_unavailable_product_cannot_be_added_or_bought(client, seeded):
    h = make_user(client, "arch@example.com")
    vid = seeded["variant"]["id"]
    add(client, h, vid, 1)
    client.delete(f"/api/v1/admin/products/{seeded['product']['id']}", headers=seeded["admin"])
    assert add(client, h, vid, 1).status_code == 404
    r = client.post("/api/v1/checkout", headers=h, json={"address_id": address(client, h)["id"]})
    assert r.status_code == 409


def test_wishlist_and_address_soft_delete(client, seeded):
    h = make_user(client, "w@example.com")
    pid = seeded["product"]["id"]
    assert client.put(f"/api/v1/wishlist/{pid}", headers=h).status_code == 200
    client.put(f"/api/v1/wishlist/{pid}", headers=h)  # idempotent
    assert len(client.get("/api/v1/wishlist", headers=h).json["products"]) == 1
    client.delete(f"/api/v1/wishlist/{pid}", headers=h)
    assert client.get("/api/v1/wishlist", headers=h).json["products"] == []
    a = address(client, h)
    assert a["is_default"] is True
    assert client.delete(f"/api/v1/addresses/{a['id']}", headers=h).status_code == 200
    assert client.get("/api/v1/addresses", headers=h).json["addresses"] == []
