import json
import re
import time
from datetime import timedelta

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.hardening import validate_production_config
from app.models import (Address, AuditLog, Category, ChatMessage, ChatSession, Consultation, FashionProfile, Notification, Order,
                        Payment, Product, ProductImage, ProductVariant, Refund, RewardAccount, RewardTransaction, TokenBlocklist,
                        User, Wallet, Wishlist)
from app.routes.admin_ops import _cell
from app.services import payment_service, rewards_service, wallet_service
from app.services.payment_service import MockProvider
from app.tasks import jobs


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


def register(client, email, role=None):
    r = client.post("/api/v1/auth/register", json={"name": email.split("@")[0].title(), "email": email, "password": "Passw0rdX"})
    uid = r.json["user"]["id"]
    if role:
        User.query.filter_by(id=uid).update({"role": role})
        db.session.commit()
    return {"Authorization": f"Bearer {r.json['access_token']}"}, uid


@pytest.fixture()
def admin(client):
    return register(client, "boss@example.com", "admin")


def add_product(name="Tee", price=100000, stock=5):
    cat = Category.query.first() or Category(name="Tops")
    db.session.add(cat)
    db.session.flush()
    p = Product(category_id=cat.id, name=name, brand="Acme", price_minor=price, tags=["casual"], description="d")
    p.images = [ProductImage(image_url="https://example.com/x.jpg")]
    p.variants.append(ProductVariant(sku=f"{name[:3].upper()}-{time.time_ns()}", size="M", color="black", stock_quantity=stock))
    db.session.add(p)
    db.session.commit()
    return p


def buy(client, h, product, qty=1, pay=True):
    """Full real flow: address -> cart -> checkout -> mock payment. Returns order id."""
    a = client.post("/api/v1/addresses", headers=h, json={"recipient_name": "R", "phone": "9999999999", "address_line_1": "1 Street",
                                                           "city": "Pune", "state": "MH", "postal_code": "411001"}).json["address"]
    client.post("/api/v1/cart/items", headers=h, json={"variant_id": product.variants[0].id, "quantity": qty})
    oid = client.post("/api/v1/checkout", headers=h, json={"address_id": a["id"]}).json["order"]["id"]
    if pay:
        client.post("/api/v1/payments/mock/pay", headers=h, json={"order_id": oid, "outcome": "success"})
    return oid


def stock(variant_id):
    db.session.expire_all()
    return db.session.get(ProductVariant, variant_id).stock_quantity


def points(uid):
    db.session.expire_all()
    a = RewardAccount.query.filter_by(user_id=uid).first()
    return a.balance if a else 0


# ---- deactivated accounts -------------------------------------------------------------------------------------
def test_deactivated_account_token_stops_working_everywhere(client, admin):
    adm, _ = admin
    h, uid = register(client, "victim@example.com")
    assert client.get("/api/v1/wallet", headers=h).status_code == 200
    assert client.patch(f"/api/v1/admin/users/{uid}", headers=adm, json={"is_active": False}).status_code == 200
    for method, url in [("get", "/api/v1/wallet"), ("get", "/api/v1/orders"), ("get", "/api/v1/profile"), ("get", "/api/v1/cart"),
                        ("get", "/api/v1/notifications"), ("get", "/api/v1/rewards/balance"), ("get", "/api/v1/consultations"),
                        ("post", "/api/v1/ai/chat"), ("get", "/api/v1/auth/me")]:
        r = getattr(client, method)(url, headers=h, json={"message": "hi"} if method == "post" else None)
        assert r.status_code == 401, url
    assert client.post("/api/v1/auth/login", json={"email": "victim@example.com", "password": "Passw0rdX"}).status_code == 401
    assert client.get("/api/v1/recommendations", headers=h).json["personalized"] is False      # anonymous view only
    client.patch(f"/api/v1/admin/users/{uid}", headers=adm, json={"is_active": True})
    assert client.get("/api/v1/wallet", headers=h).status_code == 200                           # reactivation restores access
    assert AuditLog.query.filter(AuditLog.action.in_(["user.deactivate", "user.activate"])).count() == 2


def test_user_management_guards_and_filters(client, admin):
    adm, aid = admin
    cust, cid = register(client, "alice@example.com")
    register(client, "bob_smith@example.com")
    assert client.patch(f"/api/v1/admin/users/{aid}", headers=adm, json={"is_active": False}).status_code == 409       # not yourself
    other, oid = register(client, "second-admin@example.com", "admin")
    assert client.patch(f"/api/v1/admin/users/{oid}", headers=adm, json={"is_active": False}).status_code == 200
    assert client.patch(f"/api/v1/admin/users/{aid}", headers=other, json={"is_active": False}).status_code == 401    # (now inactive)
    client.patch(f"/api/v1/admin/users/{oid}", headers=adm, json={"is_active": True})
    last = User.query.filter(User.role == "admin", User.id != aid)
    last.update({"is_active": False})
    db.session.commit()
    assert client.patch(f"/api/v1/admin/users/{aid}", headers=adm, json={"is_active": False}).status_code == 409
    assert client.patch("/api/v1/admin/users/9999", headers=adm, json={"is_active": False}).status_code == 404
    assert client.patch(f"/api/v1/admin/users/{cid}", headers=cust, json={"is_active": False}).status_code == 403
    assert client.patch(f"/api/v1/admin/users/{cid}", headers=adm, json={"is_active": "no", "x": 1}).status_code == 400
    r = client.get("/api/v1/admin/users?q=alice", headers=adm).json
    assert [u["email"] for u in r["users"]] == ["alice@example.com"] and r["total"] == 1 and "password_hash" not in json.dumps(r)
    assert client.get("/api/v1/admin/users?q=%25", headers=adm).json["total"] == 0                                        # % is literal
    assert client.get("/api/v1/admin/users?role=admin&per_page=1", headers=adm).json["total"] >= 1
    assert client.get("/api/v1/admin/users?active=false", headers=adm).json["total"] == 1


# ---- inventory --------------------------------------------------------------------------------------------------
def test_inventory_view_and_audited_stock_edit(client, admin):
    adm, _ = admin
    low, ok = add_product("Lowtee", stock=2), add_product("Plenty", stock=50)
    cust, _ = register(client, "c@example.com")
    assert client.get("/api/v1/admin/inventory", headers=cust).status_code == 403
    r = client.get("/api/v1/admin/inventory?low=true", headers=adm).json
    assert [i["product"] for i in r["items"]] == ["Lowtee"] and r["low_stock_threshold"] == 5
    assert [i["product"] for i in client.get("/api/v1/admin/inventory?q=plen", headers=adm).json["items"]] == ["Plenty"]
    vid = low.variants[0].id
    assert client.patch(f"/api/v1/admin/variants/{vid}/stock", headers=adm, json={"stock_quantity": -1}).status_code == 400
    assert client.patch(f"/api/v1/admin/variants/{vid}/stock", headers=adm, json={"stock_quantity": 40}).json["stock_quantity"] == 40
    assert client.patch("/api/v1/admin/variants/9999/stock", headers=adm, json={"stock_quantity": 1}).status_code == 404
    log = AuditLog.query.filter_by(action="inventory.set").one()
    assert log.details["before"] == 2 and log.details["after"] == 40
    client.delete(f"/api/v1/admin/products/{ok.id}", headers=adm)
    assert "Plenty" not in [i["product"] for i in client.get("/api/v1/admin/inventory", headers=adm).json["items"]]    # archived hidden


# ---- refunds ----------------------------------------------------------------------------------------------------
def test_refund_paid_order_restocks_reverses_points_and_is_idempotent(client, admin):
    adm, _ = admin
    p = add_product(price=250000, stock=5)
    h, uid = register(client, "buyer@example.com")
    oid = buy(client, h, p, qty=2)
    assert stock(p.variants[0].id) == 3
    client.patch(f"/api/v1/admin/orders/{oid}/status", headers=adm, json={"order_status": "processing"})
    client.patch(f"/api/v1/admin/orders/{oid}/status", headers=adm, json={"order_status": "shipped"})
    client.patch(f"/api/v1/admin/orders/{oid}/status", headers=adm, json={"order_status": "delivered"})
    assert points(uid) == 50                                                        # INR 5,000 -> 50 points

    assert client.post(f"/api/v1/admin/orders/{oid}/refund", headers=h, json={"reason": "x"}).status_code == 403
    assert client.post(f"/api/v1/admin/orders/{oid}/refund", headers=adm, json={"reason": ""}).status_code == 400
    r = client.post(f"/api/v1/admin/orders/{oid}/refund", headers=adm, json={"reason": "Customer returned the goods", "restock": True})
    assert r.status_code == 201 and r.json["refund"]["amount_minor"] == 500000 + 0 or r.json["refund"]["amount_minor"] > 0
    order = client.get(f"/api/v1/orders/{oid}", headers=h).json["order"]
    assert order["order_status"] == "refunded" and order["payment_status"] == "refunded"
    assert stock(p.variants[0].id) == 5 and points(uid) == 0                        # goods back, points clawed back
    assert rewards_service.reconcile(uid) == {}
    assert Payment.query.filter_by(order_id=oid).one().status == "refunded"
    assert Notification.query.filter_by(user_id=uid, type="order").count() == 1
    log = AuditLog.query.filter_by(action="order.refund").one()
    assert log.details["points_reversed"] == 50 and log.details["restocked"] is True and log.details["reason"].startswith("Customer")

    assert client.post(f"/api/v1/admin/orders/{oid}/refund", headers=adm, json={"reason": "again"}).status_code == 409
    assert Refund.query.count() == 1 and stock(p.variants[0].id) == 5
    assert [x["order_id"] for x in client.get("/api/v1/admin/refunds", headers=adm).json["refunds"]] == [oid]


def test_refund_before_shipping_restocks_by_default_and_delivered_does_not(client, admin):
    adm, _ = admin
    p = add_product(stock=10)
    h, _ = register(client, "b@example.com")
    o1 = buy(client, h, p, qty=3)
    assert stock(p.variants[0].id) == 7
    client.post(f"/api/v1/admin/orders/{o1}/refund", headers=adm, json={"reason": "Customer changed mind"})
    assert stock(p.variants[0].id) == 10                                           # never shipped: goods go back on the shelf
    o2 = buy(client, h, p, qty=2)
    for st in ("processing", "shipped", "delivered"):
        client.patch(f"/api/v1/admin/orders/{o2}/status", headers=adm, json={"order_status": st})
    client.post(f"/api/v1/admin/orders/{o2}/refund", headers=adm, json={"reason": "Goodwill refund"})
    assert stock(p.variants[0].id) == 8                                            # delivered: not restocked unless the admin says so


def test_refund_rules_and_provider_failure_changes_nothing(client, admin, monkeypatch):
    adm, _ = admin
    p = add_product()
    h, uid = register(client, "r@example.com")
    unpaid = buy(client, h, p, pay=False)
    assert client.post(f"/api/v1/admin/orders/{unpaid}/refund", headers=adm, json={"reason": "no money taken"}).status_code == 409
    assert client.post("/api/v1/admin/orders/9999/refund", headers=adm, json={"reason": "nothing here"}).status_code == 404
    client.post("/api/v1/payments/mock/pay", headers=h, json={"order_id": unpaid, "outcome": "success"})

    def boom(self, *a, **k):
        raise RuntimeError("gateway down")

    monkeypatch.setattr(MockProvider, "refund", boom)
    r = client.post(f"/api/v1/admin/orders/{unpaid}/refund", headers=adm, json={"reason": "try while down"})
    assert r.status_code == 502 and Refund.query.count() == 0
    assert client.get(f"/api/v1/orders/{unpaid}", headers=h).json["order"]["payment_status"] == "paid"
    monkeypatch.undo()
    assert client.post(f"/api/v1/admin/orders/{unpaid}/refund", headers=adm, json={"reason": "gateway is back"}).status_code == 201


def test_refunded_payment_cannot_be_refulfilled_by_a_replayed_webhook(client, admin):
    adm, _ = admin
    p = add_product()
    h, uid = register(client, "w@example.com")
    oid = buy(client, h, p)
    client.post(f"/api/v1/admin/orders/{oid}/refund", headers=adm, json={"reason": "refund then replay"})
    pay = Payment.query.filter_by(order_id=oid).one()
    raw = json.dumps({"id": "late-evt", "type": "payment.captured", "data": {
        "provider_order_id": pay.provider_order_id, "provider_payment_id": "x", "amount_minor": pay.amount_minor, "currency": "INR"}}).encode()
    sig = payment_service.get_provider().sign(raw)
    assert client.post("/api/v1/payments/webhook", data=raw, headers={"X-Signature": sig}).json["result"] == "already_paid"
    assert client.get(f"/api/v1/orders/{oid}", headers=h).json["order"]["order_status"] == "refunded"


def test_late_payment_on_cancelled_order_can_be_refunded(client, admin):
    adm, _ = admin
    p = add_product(stock=5)
    h, uid = register(client, "late@example.com")
    oid = buy(client, h, p, pay=False)
    client.post(f"/api/v1/orders/{oid}/cancel", headers=h)                          # stock released
    pay = Payment.query.filter_by(order_id=oid).one()
    raw = json.dumps({"id": "late", "type": "payment.captured", "data": {"provider_order_id": pay.provider_order_id, "provider_payment_id": "x",
                                                                         "amount_minor": pay.amount_minor, "currency": "INR"}}).encode()
    client.post("/api/v1/payments/webhook", data=raw, headers={"X-Signature": payment_service.get_provider().sign(raw)})
    assert client.get(f"/api/v1/orders/{oid}", headers=h).json["order"]["order_status"] == "cancelled"
    assert client.post(f"/api/v1/admin/orders/{oid}/refund", headers=adm, json={"reason": "Paid after cancellation"}).status_code == 201
    assert stock(p.variants[0].id) == 5                                             # not restocked twice


# ---- dashboard + reports -----------------------------------------------------------------------------------------
def test_dashboard_metrics(client, admin):
    adm, _ = admin
    tee, cap = add_product("Tee", 100000, stock=3), add_product("Cap", 40000, stock=40)
    h, uid = register(client, "shopper@example.com")
    buy(client, h, tee, qty=2)
    o2 = buy(client, h, cap, qty=1)
    client.post(f"/api/v1/admin/orders/{o2}/refund", headers=adm, json={"reason": "Dashboard test refund"})
    client.get("/api/v1/wallet", headers=h)
    cs = ChatSession(user_id=uid, session_type="ai")
    db.session.add(cs)
    db.session.flush()
    for mode, i, o in (("ai", 100, 40), ("fallback", 0, 0), ("ai", 50, 10)):
        db.session.add(ChatMessage(session_id=cs.id, sender_type="assistant", message_text="x", picks=[], meta={"mode": mode, "input_tokens": i, "output_tokens": o}))
    db.session.commit()

    d = client.get("/api/v1/admin/dashboard?days=30", headers=adm).json
    assert d["revenue"]["gross_minor"] == 249900 and d["revenue"]["refunded_minor"] == 49900 and d["revenue"]["net_minor"] == 200000   # Cap order: 40000 + 9900 shipping
    assert d["revenue"]["by_purpose"]["order"]["count"] == 2
    assert d["orders"]["by_status"] == {"confirmed": 1, "refunded": 1} and d["orders"]["total"] == 2
    assert d["top_products"][0] == {"name": "Tee", "units": 2, "revenue_minor": 200000}
    assert d["users"]["customers"] == 1 and d["users"]["new"] == 1
    assert d["credits"]["daily_outstanding"] == 10 and d["credits"]["super_outstanding"] == 0
    assert d["ai"] == {"messages": 3, "ai_mode": 2, "fallback_mode": 1, "input_tokens": 150, "output_tokens": 50, "truncated": False}
    assert d["inventory"]["low_stock_variants"] == 1 and d["inventory"]["out_of_stock_variants"] == 0     # Tee: 3 left
    assert sum(x["amount_minor"] for x in d["daily"]) == 249900
    assert client.get("/api/v1/admin/dashboard?days=abc", headers=adm).json["range"]["days"] == 30
    assert client.get("/api/v1/admin/dashboard?days=99999", headers=adm).json["range"]["days"] == 365
    assert client.get("/api/v1/admin/dashboard", headers=h).status_code == 403
    assert client.get("/api/v1/admin/dashboard").status_code == 401


def test_csv_reports_and_formula_injection_defence(client, admin):
    adm, _ = admin
    p = add_product()
    h, _ = register(client, "csv@example.com")
    buy(client, h, p)
    r = client.get("/api/v1/admin/reports/orders.csv", headers=adm)
    assert r.status_code == 200 and r.mimetype == "text/csv" and "attachment" in r.headers["Content-Disposition"]
    lines = r.get_data(as_text=True).strip().splitlines()
    assert lines[0].startswith("order_number,created_at") and len(lines) == 2 and ",confirmed,paid," in lines[1]
    for name in ("payments", "credits", "audit"):
        assert client.get(f"/api/v1/admin/reports/{name}.csv", headers=adm).status_code == 200
    assert client.get("/api/v1/admin/reports/secrets.csv", headers=adm).status_code == 404
    assert client.get("/api/v1/admin/reports/orders.csv", headers=h).status_code == 403
    assert [_cell(x) for x in ("=SUM(A1)", "+1", "-1", "@cmd", "\tx", "ok", None, 5)] == ["'=SUM(A1)", "'+1", "'-1", "'@cmd", "'\tx", "ok", "", "5"]


def test_audit_log_covers_sensitive_admin_actions(client, admin):
    adm, _ = admin
    cid = client.post("/api/v1/admin/categories", headers=adm, json={"name": "Shoes"}).json["category"]["id"]
    client.put(f"/api/v1/admin/categories/{cid}", headers=adm, json={"name": "Footwear"})
    body = {"category_id": cid, "name": "Boot", "price_minor": 5000, "variants": [{"sku": "B1", "stock_quantity": 1}], "images": []}
    pid = client.post("/api/v1/admin/products", headers=adm, json=body).json["product"]["id"]
    client.put(f"/api/v1/admin/products/{pid}", headers=adm, json={**body, "price_minor": 6000})
    client.delete(f"/api/v1/admin/products/{pid}", headers=adm)
    actions = {a.action for a in AuditLog.query}
    assert {"category.create", "category.update", "product.create", "product.update", "product.archive"} <= actions
    upd = AuditLog.query.filter_by(action="product.update").one().details
    assert upd["before"]["price_minor"] == 5000 and upd["after"]["price_minor"] == 6000
    page = client.get("/api/v1/admin/audit-logs?action=product.update&per_page=1", headers=adm).json
    assert page["total"] == 1 and "product.archive" in page["actions"]


# ---- privacy: export + deletion -----------------------------------------------------------------------------------
def _full_customer(client):
    h, uid = register(client, "gone@example.com")
    client.put("/api/v1/profile/fashion", headers=h, json={"preferred_styles": ["casual"]})
    p = add_product(stock=5)
    client.put(f"/api/v1/wishlist/{p.id}", headers=h)
    client.get("/api/v1/wallet", headers=h)
    cs = ChatSession(user_id=uid, session_type="ai", title="secret chat")
    cs.messages.append(ChatMessage(sender_type="user", message_text="my private question", picks=[]))
    db.session.add(cs)
    db.session.commit()
    return h, uid, p


def test_export_contains_the_users_data_and_no_secrets(client):
    h, uid, p = _full_customer(client)
    buy(client, h, p)
    r = client.get("/api/v1/profile/export", headers=h)
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    d = r.get_json()
    assert d["account"]["email"] == "gone@example.com" and d["fashion_profile"]["preferred_styles"] == ["casual"]
    assert len(d["orders"]) == 1 and len(d["addresses"]) == 1 and d["wishlist_product_ids"] == [p.id]
    assert d["chats"][0]["messages"][0]["text"] == "my private question" and d["credit_transactions"]
    blob = json.dumps(d)
    assert "password_hash" not in blob and "scrypt" not in blob
    other, _ = register(client, "other@example.com")
    assert "gone@example.com" not in json.dumps(client.get("/api/v1/profile/export", headers=other).get_json())
    assert client.get("/api/v1/profile/export").status_code == 401


def test_account_deletion_erases_pii_but_keeps_accounting_records(client):
    h, uid, p = _full_customer(client)
    oid = buy(client, h, p)
    client.patch(f"/api/v1/admin/orders/{oid}/status", headers=register(client, "adm@example.com", "admin")[0], json={"order_status": "processing"})
    for st in ("shipped", "delivered"):
        adm = {"Authorization": "Bearer " + client.post("/api/v1/auth/login", json={"email": "adm@example.com", "password": "Passw0rdX"}).json["access_token"]}
        client.patch(f"/api/v1/admin/orders/{oid}/status", headers=adm, json={"order_status": st})
    assert client.post("/api/v1/profile/delete-account", headers=h, json={"password": "WrongPass1", "confirm": "DELETE"}).status_code == 403
    assert client.post("/api/v1/profile/delete-account", headers=h, json={"password": "Passw0rdX", "confirm": "yes"}).status_code == 400
    assert client.post("/api/v1/profile/delete-account", json={"password": "Passw0rdX", "confirm": "DELETE"}).status_code == 401
    r = client.post("/api/v1/profile/delete-account", headers=h, json={"password": "Passw0rdX", "confirm": "DELETE"})
    assert r.status_code == 200
    u = db.session.get(User, uid)
    assert u.name == "Deleted user" and u.email == f"deleted-{uid}@deleted.invalid" and u.phone is None and not u.is_active
    assert FashionProfile.query.filter_by(user_id=uid).count() == 0 and Wishlist.query.filter_by(user_id=uid).count() == 0
    assert ChatSession.query.filter_by(user_id=uid).count() == 0 and ChatMessage.query.filter_by(message_text="my private question").count() == 0
    a = Address.query.filter_by(user_id=uid).one()
    assert a.recipient_name == "Deleted" and a.address_line_1 == "Deleted" and a.is_deleted
    assert Order.query.filter_by(user_id=uid).count() == 1 and Payment.query.filter_by(user_id=uid).count() == 1   # records kept
    assert Wallet.query.filter_by(user_id=uid).count() == 1
    assert client.get("/api/v1/wallet", headers=h).status_code == 401                                              # token dead
    assert client.post("/api/v1/auth/login", json={"email": "gone@example.com", "password": "Passw0rdX"}).status_code == 401
    log = AuditLog.query.filter_by(action="account.delete").one()
    assert "gone@example.com" not in json.dumps(log.details)
    assert client.post("/api/v1/auth/register", json={"name": "New", "email": "gone@example.com", "password": "Passw0rdX"}).status_code == 201


def test_account_deletion_is_blocked_while_things_are_in_flight(client, admin):
    adm, _ = admin
    h, uid = register(client, "busy@example.com")
    p = add_product()
    oid = buy(client, h, p)
    body = {"password": "Passw0rdX", "confirm": "DELETE"}
    assert client.post("/api/v1/profile/delete-account", headers=h, json=body).status_code == 409          # paid order not yet delivered
    for st in ("processing", "shipped", "delivered"):
        client.patch(f"/api/v1/admin/orders/{oid}/status", headers=adm, json={"order_status": st})
    unpaid = buy(client, h, p, pay=False)                                                                  # reserves stock
    assert stock(p.variants[0].id) == 3
    assert client.post("/api/v1/profile/delete-account", headers=h, json=body).status_code == 200
    assert Order.query.get(unpaid).order_status == "cancelled" and stock(p.variants[0].id) == 4            # reservation released


def test_stylists_and_admins_cannot_self_delete(client, admin):
    adm, _ = admin
    s, _ = register(client, "sty@example.com", "stylist")
    for h in (adm, s):
        assert client.post("/api/v1/profile/delete-account", headers=h, json={"password": "Passw0rdX", "confirm": "DELETE"}).status_code == 403


# ---- retention --------------------------------------------------------------------------------------------------
def test_retention_job_purges_only_what_is_expired(client, app):
    _, uid = register(client, "ret@example.com")
    now = wallet_service.now_utc()
    old, recent = now - timedelta(days=400), now - timedelta(hours=1)
    db.session.add_all([TokenBlocklist(jti="old-jti", created_at=now - timedelta(days=2)), TokenBlocklist(jti="new-jti", created_at=recent)])
    stale = ChatSession(user_id=uid, session_type="ai", title="stale", updated_at=old)
    fresh = ChatSession(user_id=uid, session_type="ai", title="fresh", updated_at=recent)
    consult_chat = ChatSession(user_id=uid, session_type="stylist", title="stylist", updated_at=old)
    db.session.add_all([stale, fresh, consult_chat])
    db.session.add_all([Notification(user_id=uid, type="x", title="old read", is_read=True, created_at=now - timedelta(days=120)),
                        Notification(user_id=uid, type="x", title="old unread", is_read=False, created_at=now - timedelta(days=120)),
                        Notification(user_id=uid, type="x", title="new read", is_read=True, created_at=recent)])
    db.session.commit()
    out = jobs.retention_maintenance(now)
    assert out == {"revoked_tokens_purged": 1, "ai_chats_purged": 1, "notifications_purged": 1}
    assert {s.title for s in ChatSession.query} == {"fresh", "stylist"}                  # stylist chats follow the consultation, not this rule
    assert {n.title for n in Notification.query.filter_by(user_id=uid)} == {"old unread", "new read"}
    assert TokenBlocklist.query.one().jti == "new-jti"
    assert jobs.retention_maintenance(now) == {"revoked_tokens_purged": 0, "ai_chats_purged": 0, "notifications_purged": 0}


# ---- hardening --------------------------------------------------------------------------------------------------
def test_security_headers_request_ids_and_safe_errors(client):
    r = client.get("/api/v1/products")
    h = r.headers
    assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY" and h["Referrer-Policy"] == "no-referrer"
    assert h["Cache-Control"] == "no-store" and "default-src 'none'" in h["Content-Security-Policy"] and h["X-Request-ID"]
    assert client.get("/api/v1/products", headers={"X-Request-ID": "trace-12345678"}).headers["X-Request-ID"] == "trace-12345678"
    assert client.get("/api/v1/products", headers={"X-Request-ID": "bad id <script>"}).headers["X-Request-ID"] != "bad id <script>"
    assert "Strict-Transport-Security" not in h                                          # only in production
    nf = client.get("/api/v1/nope")
    assert nf.status_code == 404 and nf.is_json and nf.json["error"] == "Not Found" and "<html" not in nf.get_data(as_text=True)
    assert client.delete("/api/v1/products").status_code == 405 and client.delete("/api/v1/products").is_json
    big = client.post("/api/v1/auth/login", data="x" * (2 * 1024 * 1024), content_type="application/json")
    assert big.status_code == 413 and big.json["error"] == "Request too large"


def test_readiness_probe(client, monkeypatch):
    assert client.get("/api/v1/health").json == {"status": "ok"}
    assert client.get("/api/v1/health/ready").json == {"status": "ready"}

    def down(*a, **k):
        raise RuntimeError("db gone")

    monkeypatch.setattr(db.session, "execute", down)
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 503 and r.json == {"status": "unavailable"}


GOOD = {"SECRET_KEY": "a" * 40, "JWT_SECRET_KEY": "b" * 40, "SQLALCHEMY_DATABASE_URI": "mysql+pymysql://u:p@db/app",
        "PAYMENT_PROVIDER": "razorpay", "MOCK_PAYMENTS_ENABLED": False, "PAYMENT_WEBHOOK_SECRET": "w" * 32,
        "CORS_ORIGINS": ["https://shop.example.com"], "FRONTEND_URL": "https://shop.example.com", "RATELIMIT_STORAGE_URI": "redis://redis:6379/0"}


def test_production_config_validation():
    assert validate_production_config(GOOD) == []
    bad = validate_production_config({**GOOD, "SECRET_KEY": "dev-secret", "JWT_SECRET_KEY": "dev-secret", "SQLALCHEMY_DATABASE_URI": "sqlite:///x.db",
                                      "PAYMENT_PROVIDER": "mock", "MOCK_PAYMENTS_ENABLED": True, "PAYMENT_WEBHOOK_SECRET": "dev-webhook",
                                      "CORS_ORIGINS": ["http://localhost:5173"], "FRONTEND_URL": "http://localhost:5173", "RATELIMIT_STORAGE_URI": "memory://"})
    joined = " ".join(bad)
    for needle in ("SECRET_KEY", "must differ", "MySQL", "mock payment", "PAYMENT_WEBHOOK_SECRET", "CORS_ORIGINS", "FRONTEND_URL", "RATELIMIT_STORAGE_URI"):
        assert needle in joined, needle
    assert validate_production_config({**GOOD, "PAYMENT_PROVIDER": "mock", "ALLOW_INSECURE_MOCK_PAYMENTS": True}) == []     # explicit staging override


def test_app_refuses_to_boot_with_insecure_production_config():
    class Prod(TestConfig):
        APP_ENV = "production"
        TESTING = False

    with pytest.raises(RuntimeError, match="insecure production configuration"):
        create_app(Prod)


# ---- authorization audit of every route ---------------------------------------------------------------------------
PUBLIC = {
    ("GET", "/api/v1/health"), ("GET", "/api/v1/health/ready"), ("POST", "/api/v1/auth/register"), ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/forgot-password"), ("POST", "/api/v1/auth/reset-password"), ("POST", "/api/v1/auth/verify-email"),
    ("POST", "/api/v1/payments/webhook"), ("GET", "/api/v1/products"), ("GET", "/api/v1/products/<int:pid>"), ("GET", "/api/v1/categories"),
    ("GET", "/api/v1/filters"), ("GET", "/api/v1/stylists"), ("GET", "/api/v1/stylists/<int:sid>"),
    ("GET", "/api/v1/stylists/<int:sid>/availability"), ("GET", "/api/v1/wallet/packs"), ("GET", "/api/v1/wallet/credit-costs"),
    ("GET", "/api/v1/subscriptions/plans"), ("GET", "/api/v1/rewards/offers"), ("GET", "/api/v1/recommendations"),
}
ROLE_ONLY = ("/api/v1/admin/", "/api/v1/stylist/")  # plus accept/decline/complete below


def _routes(app):
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        for m in rule.methods - {"HEAD", "OPTIONS"}:
            yield m, rule.rule, re.sub(r"<[^>]+>", "1", rule.rule)


def test_every_non_public_route_requires_authentication(client, app):
    leaks = []
    for method, rule, url in _routes(app):
        if (method, rule) in PUBLIC:
            continue
        r = client.open(url, method=method, json={})
        if r.status_code != 401:
            leaks.append((method, rule, r.status_code))
    assert leaks == [], f"routes reachable without a token: {leaks}"


def test_admin_stylist_routes_reject_customers(client, app):
    cust, _ = register(client, "plain@example.com")
    role_only = [(m, r, u) for m, r, u in _routes(app)
                 if r.startswith(ROLE_ONLY) or re.match(r"/api/v1/consultations/<int:cid>/(accept|decline|complete)$", r)]
    assert len(role_only) > 40                                                         # the audit really covers the admin surface
    leaks = [(m, r, client.open(u, method=m, headers=cust, json={}).status_code) for m, r, u in role_only]
    assert [x for x in leaks if x[2] != 403] == []


def test_admin_routes_reject_stylists_too(client, app):
    sty, _ = register(client, "styl@example.com", "stylist")
    leaks = [(m, r) for m, r, u in _routes(app) if r.startswith("/api/v1/admin/") and client.open(u, method=m, headers=sty, json={}).status_code != 403]
    assert leaks == []
