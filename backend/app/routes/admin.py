from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from ..extensions import db
from ..models import (AuditLog, Category, CreditPack, CreditTransaction, Order, OrderItem, Product, ProductImage,
                      ProductVariant, SubscriptionPlan, User)
from ..schemas.shop import CategoryInSchema, OrderStatusSchema, ProductInSchema
from ..schemas.wallet import AdjustSchema, PackInSchema, PlanInSchema
from ..services import rewards_service, settings_service, wallet_service
from ..services.errors import ShopError
from ..utils.auth import current_user, roles_required

bp = Blueprint("admin", __name__, url_prefix="/api/v1/admin")

# Fulfilment moves forward only. Cancellation/refund/return flows need the refund policy (open decision).
NEXT_STATUS = {
    "confirmed": {"processing"},
    "processing": {"shipped"},
    "shipped": {"out_for_delivery", "delivered"},
    "out_for_delivery": {"delivered"},
}


def _load(schema):
    try:
        return schema().load(request.get_json(silent=True) or {}, unknown="raise")
    except ValidationError as e:
        raise ShopError("Validation failed", 400, e.messages)


# ---- Categories -----------------------------------------------------------------------------
@bp.get("/categories")
@roles_required("admin")
def admin_categories():
    return jsonify(categories=[c.to_dict() for c in Category.query.order_by(Category.name)])


@bp.post("/categories")
@roles_required("admin")
def create_category():
    data = _load(CategoryInSchema)
    c = Category(**data)
    db.session.add(c)
    db.session.flush()
    wallet_service.audit(current_user().id, "category.create", "category", c.id, data)
    db.session.commit()
    return jsonify(category=c.to_dict()), 201


@bp.put("/categories/<int:cid>")
@roles_required("admin")
def update_category(cid):
    data = _load(CategoryInSchema)
    c = db.session.get(Category, cid) or _404("Category")
    if data["parent_id"] == cid:
        raise ShopError("A category cannot be its own parent.", 400)
    before = c.to_dict()
    for k, v in data.items():
        setattr(c, k, v)
    wallet_service.audit(current_user().id, "category.update", "category", c.id, {"before": before, "after": data})
    db.session.commit()
    return jsonify(category=c.to_dict())


def _404(what):
    raise ShopError(f"{what} not found.", 404)


# ---- Products -------------------------------------------------------------------------------
def _apply_product(p, data):
    if not db.session.get(Category, data["category_id"]):
        raise ShopError("Validation failed", 400, {"category_id": ["Unknown category."]})
    for k in ("category_id", "name", "description", "brand", "price_minor", "sale_price_minor", "status",
              "material", "care", "tags", "return_eligible"):
        setattr(p, k, data[k])

    existing = {v.id: v for v in p.variants}
    by_sku = {v.sku: v for v in p.variants}
    keep = set()
    for vd in data["variants"]:
        # Match by id, or by SKU when the client sends no id (so a PUT of the same SKU updates it instead of duplicating it).
        v = existing.get(vd["id"]) if vd["id"] else by_sku.get(vd["sku"])
        if vd["id"] and not v:
            raise ShopError("Validation failed", 400, {"variants": [f"Unknown variant id {vd['id']}."]})
        if not v:
            v = ProductVariant()
            p.variants.append(v)
        for k in ("sku", "size", "color", "stock_quantity"):
            setattr(v, k, vd[k])
        if v.id:
            keep.add(v.id)
    for vid, v in existing.items():
        if vid not in keep:
            if OrderItem.query.filter_by(product_variant_id=vid).first():
                v.stock_quantity = 0  # referenced by past orders: retire instead of delete
            else:
                p.variants.remove(v)

    p.images[:] = [ProductImage(image_url=i["image_url"], alt_text=i["alt_text"] or p.name, display_order=n)
                   for n, i in enumerate(data["images"])]


def _sku_conflict(data, product_id=None):
    for vd in data["variants"]:
        q = ProductVariant.query.filter_by(sku=vd["sku"])
        hit = q.first()
        if hit and (product_id is None or hit.product_id != product_id):
            raise ShopError("Validation failed", 400, {"variants": [f"SKU {vd['sku']} already exists."]})


@bp.get("/products")
@roles_required("admin")
def admin_products():
    rows = Product.query.order_by(Product.id.desc()).all()
    return jsonify(products=[p.to_dict(detail=False) | {"stock_total": sum(v.stock_quantity for v in p.variants)} for p in rows])


@bp.get("/products/<int:pid>")
@roles_required("admin")
def admin_product(pid):
    return jsonify(product=(db.session.get(Product, pid) or _404("Product")).to_dict())


@bp.post("/products")
@roles_required("admin")
def create_product():
    data = _load(ProductInSchema)
    _sku_conflict(data)
    p = Product()
    _apply_product(p, data)
    db.session.add(p)
    db.session.flush()
    wallet_service.audit(current_user().id, "product.create", "product", p.id, {"name": p.name, "price_minor": p.price_minor})
    db.session.commit()
    return jsonify(product=p.to_dict()), 201


@bp.put("/products/<int:pid>")
@roles_required("admin")
def update_product(pid):
    data = _load(ProductInSchema)
    p = db.session.get(Product, pid) or _404("Product")
    _sku_conflict(data, pid)
    before = {"name": p.name, "price_minor": p.price_minor, "sale_price_minor": p.sale_price_minor, "status": p.status}
    _apply_product(p, data)
    wallet_service.audit(current_user().id, "product.update", "product", p.id, {"before": before, "after": {
        "name": data["name"], "price_minor": data["price_minor"], "sale_price_minor": data["sale_price_minor"], "status": data["status"]}})
    db.session.commit()
    return jsonify(product=p.to_dict())


@bp.delete("/products/<int:pid>")
@roles_required("admin")
def archive_product(pid):
    p = db.session.get(Product, pid) or _404("Product")
    p.status = "archived"  # never hard-delete: orders reference products
    wallet_service.audit(current_user().id, "product.archive", "product", p.id, {"name": p.name})
    db.session.commit()
    return jsonify(product=p.to_dict(detail=False))


# ---- Orders ---------------------------------------------------------------------------------
@bp.get("/orders")
@roles_required("admin")
def admin_orders():
    q = Order.query
    if request.args.get("status"):
        q = q.filter_by(order_status=request.args["status"])
    return jsonify(orders=[o.to_dict(detail=False) | {"user_id": o.user_id} for o in q.order_by(Order.created_at.desc()).limit(200)])


@bp.get("/orders/<int:oid>")
@roles_required("admin")
def admin_order(oid):
    return jsonify(order=(db.session.get(Order, oid) or _404("Order")).to_dict())


@bp.patch("/orders/<int:oid>/status")
@roles_required("admin")
def set_order_status(oid):
    data = _load(OrderStatusSchema)
    o = db.session.query(Order).filter_by(id=oid).with_for_update().first() or _404("Order")
    if data["order_status"] not in NEXT_STATUS.get(o.order_status, set()):
        raise ShopError(f"Cannot move an order from {o.order_status} to {data['order_status']}.", 409)
    if o.payment_status != "paid":
        raise ShopError("Order is not paid.", 409)
    wallet_service.audit(current_user().id, "order.status", "order", o.id, {"from": o.order_status, "to": data["order_status"]})
    o.order_status = data["order_status"]
    if o.order_status == "delivered":
        rewards_service.on_order_delivered(o)  # qualifying event for purchase points / referral rewards
    db.session.commit()
    return jsonify(order=o.to_dict())


# ---- Credits: configuration, packs, plans, adjustments, audit ---------------------------------------
@bp.get("/settings/credits")
@roles_required("admin")
def get_credit_config():
    return jsonify(settings=settings_service.get_credit_settings(), known_services=settings_service.KNOWN_SERVICES)


@bp.put("/settings/credits")
@roles_required("admin")
def put_credit_config():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ShopError("Validation failed", 400, {"_": ["Expected a JSON object."]})
    before = settings_service.get_credit_settings()
    cleaned = settings_service.validate_credit_settings(body)
    settings_service.save_credit_settings(cleaned)
    wallet_service.audit(current_user().id, "settings.credits.update", "settings", "credits",
                         {"before": before, "after": cleaned})
    db.session.commit()
    return jsonify(settings=cleaned)


def _crud(model, schema, item_key):
    def create():
        data = _load(schema)
        obj = model(**data)
        db.session.add(obj)
        db.session.flush()
        wallet_service.audit(current_user().id, f"{item_key}.create", item_key, obj.id, data)
        db.session.commit()
        return jsonify({item_key: obj.to_dict()}), 201

    def update(oid):
        data = _load(schema)
        obj = db.session.get(model, oid) or _404(item_key)
        for k, v in data.items():
            setattr(obj, k, v)
        wallet_service.audit(current_user().id, f"{item_key}.update", item_key, obj.id, data)
        db.session.commit()
        return jsonify({item_key: obj.to_dict()})

    return create, update


@bp.get("/credit-packs")
@roles_required("admin")
def list_packs():
    return jsonify(packs=[p.to_dict() for p in CreditPack.query.order_by(CreditPack.id)])


@bp.get("/plans")
@roles_required("admin")
def list_plans():
    return jsonify(plans=[p.to_dict() for p in SubscriptionPlan.query.order_by(SubscriptionPlan.id)])


_create_pack, _update_pack = _crud(CreditPack, PackInSchema, "pack")
_create_plan, _update_plan = _crud(SubscriptionPlan, PlanInSchema, "plan")
bp.add_url_rule("/credit-packs", "create_pack", roles_required("admin")(_create_pack), methods=["POST"])
bp.add_url_rule("/credit-packs/<int:oid>", "update_pack", roles_required("admin")(_update_pack), methods=["PUT"])
bp.add_url_rule("/plans", "create_plan", roles_required("admin")(_create_plan), methods=["POST"])
bp.add_url_rule("/plans/<int:oid>", "update_plan", roles_required("admin")(_update_plan), methods=["PUT"])


@bp.get("/users/<int:uid>/wallet")
@roles_required("admin")
def admin_user_wallet(uid):
    if not db.session.get(User, uid):
        raise ShopError("User not found.", 404)
    summary = wallet_service.wallet_summary(uid)
    db.session.commit()
    w = wallet_service.get_wallet(uid, lock=False)
    rows = CreditTransaction.query.filter_by(wallet_id=w.id).order_by(CreditTransaction.id.desc()).limit(50).all()
    return jsonify(wallet=summary, transactions=[r.to_dict() for r in rows],
                   ledger_mismatch={k: list(v) for k, v in wallet_service.reconcile(w).items()})


@bp.post("/users/<int:uid>/wallet/adjust")
@roles_required("admin")
def admin_adjust(uid):
    data = _load(AdjustSchema)
    row = wallet_service.adjust(current_user().id, uid, data["credit_type"], data["amount"], data["reason"])
    db.session.commit()
    return jsonify(transaction=row.to_dict()), 201


@bp.get("/audit-logs")
@roles_required("admin")
def audit_logs():
    q = AuditLog.query
    if request.args.get("action"):
        q = q.filter_by(action=request.args["action"])
    if request.args.get("actor_id", "").isdigit():
        q = q.filter_by(actor_id=int(request.args["actor_id"]))
    try:
        page, per = max(1, int(request.args.get("page", 1))), min(200, max(1, int(request.args.get("per_page", 50))))
    except ValueError:
        page, per = 1, 50
    total = q.count()
    rows = q.order_by(AuditLog.id.desc()).offset((page - 1) * per).limit(per).all()
    actions = [a for (a,) in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all()]
    return jsonify(logs=[a.to_dict() for a in rows], total=total, page=page, per_page=per, actions=actions)


# ---- Stylists, consultations, rewards ---------------------------------------------------------------
from ..models import Consultation, RewardOffer, Stylist  # noqa: E402
from ..schemas.stylist import AdminStylistSchema, OfferSchema  # noqa: E402


def _section_routes(key, name):
    def get():
        return jsonify(settings=settings_service.get_section(key))

    def put():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ShopError("Validation failed", 400, {"_": ["Expected a JSON object."]})
        before = settings_service.get_section(key)
        cleaned = settings_service.validate_section(key, body)
        settings_service.save_section(key, cleaned)
        wallet_service.audit(current_user().id, f"settings.{key}.update", "settings", key, {"before": before, "after": cleaned})
        db.session.commit()
        return jsonify(settings=cleaned)

    bp.add_url_rule(f"/settings/{key}", f"get_{key}", roles_required("admin")(get), methods=["GET"])
    bp.add_url_rule(f"/settings/{key}", f"put_{key}", roles_required("admin")(put), methods=["PUT"])


_section_routes("consultations", "consultation")
_section_routes("rewards", "rewards")


def _stylist_admin(s):
    d = s.to_dict()
    d["email"] = s.user.email
    d["user_id"] = s.user_id
    return d


@bp.get("/stylists")
@roles_required("admin")
def admin_stylists():
    return jsonify(stylists=[_stylist_admin(s) for s in Stylist.query.order_by(Stylist.id)])


@bp.post("/stylists")
@roles_required("admin")
def admin_create_stylist():
    data = _load(AdminStylistSchema)
    user = db.session.get(User, data.pop("user_id") or 0)
    if not user or not user.is_active:
        raise ShopError("Validation failed", 400, {"user_id": ["Unknown or inactive user."]})
    if user.role == "admin" or Stylist.query.filter_by(user_id=user.id).first():
        raise ShopError("This account can't be made a stylist.", 409)
    user.role = "stylist"
    s = Stylist(user_id=user.id, **data)
    db.session.add(s)
    db.session.flush()
    wallet_service.audit(current_user().id, "stylist.create", "stylist", s.id, {"user_id": user.id})
    db.session.commit()
    return jsonify(stylist=_stylist_admin(s)), 201


@bp.put("/stylists/<int:sid>")
@roles_required("admin")
def admin_update_stylist(sid):
    data = _load(AdminStylistSchema)
    data.pop("user_id", None)
    s = db.session.get(Stylist, sid) or _404("Stylist")
    for k, v in data.items():
        setattr(s, k, v)
    wallet_service.audit(current_user().id, "stylist.update", "stylist", s.id, data)
    db.session.commit()
    return jsonify(stylist=_stylist_admin(s))


@bp.get("/consultations")
@roles_required("admin")
def admin_consultations():
    q = Consultation.query
    if request.args.get("status"):
        q = q.filter_by(status=request.args["status"])
    return jsonify(consultations=[c.to_dict() for c in q.order_by(Consultation.id.desc()).limit(200)])


@bp.get("/reward-offers")
@roles_required("admin")
def admin_offers():
    return jsonify(offers=[o.to_dict() for o in RewardOffer.query.order_by(RewardOffer.id)])


_create_offer, _update_offer = _crud(RewardOffer, OfferSchema, "offer")
bp.add_url_rule("/reward-offers", "create_offer", roles_required("admin")(_create_offer), methods=["POST"])
bp.add_url_rule("/reward-offers/<int:oid>", "update_offer", roles_required("admin")(_update_offer), methods=["PUT"])
