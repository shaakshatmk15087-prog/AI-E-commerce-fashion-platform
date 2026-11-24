from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import and_, case, func, or_

from ..extensions import db
from ..models import Category, Product, ProductVariant, Wishlist
from ..utils.auth import current_user

bp = Blueprint("catalog", __name__, url_prefix="/api/v1")


@bp.get("/categories")
def categories():
    cats = Category.query.filter_by(is_active=True).order_by(Category.name).all()
    return jsonify(categories=[c.to_dict() for c in cats])


def _int(name, default=None, lo=None, hi=None):
    try:
        v = int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


@bp.get("/products")
def list_products():
    a = request.args
    price = case((and_(Product.sale_price_minor.isnot(None), Product.sale_price_minor < Product.price_minor),
                  Product.sale_price_minor), else_=Product.price_minor)
    q = Product.query.filter(Product.status == "active")

    if a.get("q"):
        like = "%" + a["q"].strip().replace("%", r"\%").replace("_", r"\_") + "%"
        q = q.filter(or_(Product.name.ilike(like, escape="\\"), Product.description.ilike(like, escape="\\"),
                         Product.brand.ilike(like, escape="\\"), func.cast(Product.tags, db.String).ilike(like, escape="\\")))
    if a.get("category_id"):
        cid = _int("category_id")
        child_ids = [c.id for c in Category.query.filter_by(parent_id=cid)]
        q = q.filter(Product.category_id.in_([cid, *child_ids]))
    if a.get("brand"):
        q = q.filter(Product.brand.in_(a.getlist("brand")))
    if a.get("min_price"):
        q = q.filter(price >= _int("min_price", 0, 0))
    if a.get("max_price"):
        q = q.filter(price <= _int("max_price", 0, 0))

    vcond = [ProductVariant.stock_quantity > 0]
    if a.get("size"):
        vcond.append(ProductVariant.size.in_(a.getlist("size")))
    if a.get("color"):
        vcond.append(ProductVariant.color.in_(a.getlist("color")))
    if len(vcond) > 1 or a.get("in_stock") == "true":
        q = q.filter(Product.variants.any(and_(*vcond)))

    sort = a.get("sort", "newest")
    q = q.order_by({"price_asc": price.asc(), "price_desc": price.desc()}.get(sort, Product.created_at.desc()), Product.id.desc())

    per_page = _int("per_page", 12, 1, 48)
    page = _int("page", 1, 1)
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify(products=[p.to_dict(detail=False) for p in items], total=total, page=page, per_page=per_page)


@bp.get("/products/<int:pid>")
def product_detail(pid):
    p = db.session.get(Product, pid)
    if not p or p.status != "active":
        return jsonify(error="Product not found"), 404
    return jsonify(product=p.to_dict())


@bp.get("/filters")
def filters():
    """Facet values for the shop sidebar (from in-stock active inventory)."""
    rows = (db.session.query(ProductVariant.size, ProductVariant.color, Product.brand)
            .join(Product).filter(Product.status == "active", ProductVariant.stock_quantity > 0).all())
    return jsonify(sizes=sorted({r[0] for r in rows if r[0]}), colors=sorted({r[1] for r in rows if r[1]}),
                   brands=sorted({r[2] for r in rows if r[2]}))


# ---- Wishlist -------------------------------------------------------------------------------
@bp.get("/wishlist")
@jwt_required()
def get_wishlist():
    rows = Wishlist.query.filter_by(user_id=current_user().id).order_by(Wishlist.created_at.desc()).all()
    return jsonify(products=[w.product.to_dict(detail=False) for w in rows if w.product.status == "active"])


@bp.put("/wishlist/<int:pid>")
@jwt_required()
def add_wishlist(pid):
    u = current_user()
    p = db.session.get(Product, pid)
    if not p or p.status != "active":
        return jsonify(error="Product not found"), 404
    if not Wishlist.query.filter_by(user_id=u.id, product_id=pid).first():
        db.session.add(Wishlist(user_id=u.id, product_id=pid))
        db.session.commit()
    return jsonify(message="Saved")


@bp.delete("/wishlist/<int:pid>")
@jwt_required()
def remove_wishlist(pid):
    Wishlist.query.filter_by(user_id=current_user().id, product_id=pid).delete()
    db.session.commit()
    return jsonify(message="Removed")
