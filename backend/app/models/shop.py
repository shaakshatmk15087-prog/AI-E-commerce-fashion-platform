from ..extensions import db
from .user import utcnow

ORDER_STATUSES = (
    "pending_payment", "confirmed", "processing", "shipped", "out_for_delivery",
    "delivered", "cancelled", "return_requested", "returned", "refunded",
)
PAYMENT_STATUSES = ("pending", "paid", "failed", "refunded")


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "parent_id": self.parent_id,
                "description": self.description, "is_active": self.is_active}


class Product(db.Model):
    """Stock lives on variants; a product is purchasable if any variant has stock."""
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    brand = db.Column(db.String(100), nullable=True, index=True)
    price_minor = db.Column(db.Integer, nullable=False)
    sale_price_minor = db.Column(db.Integer, nullable=True)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    status = db.Column(db.String(20), nullable=False, default="active", index=True)  # active | draft | archived
    material = db.Column(db.String(255), nullable=True)
    care = db.Column(db.String(255), nullable=True)
    tags = db.Column(db.JSON, nullable=False, default=list)
    return_eligible = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    category = db.relationship("Category")
    variants = db.relationship("ProductVariant", backref="product", cascade="all, delete-orphan", order_by="ProductVariant.id")
    images = db.relationship("ProductImage", backref="product", cascade="all, delete-orphan", order_by="ProductImage.display_order")

    @property
    def effective_price_minor(self):
        s = self.sale_price_minor
        return s if s is not None and s < self.price_minor else self.price_minor

    @property
    def in_stock(self):
        return any(v.stock_quantity > 0 for v in self.variants)

    def to_dict(self, detail=True):
        d = {
            "id": self.id, "name": self.name, "brand": self.brand, "category_id": self.category_id,
            "category": self.category.name if self.category else None,
            "price_minor": self.price_minor, "sale_price_minor": self.sale_price_minor,
            "effective_price_minor": self.effective_price_minor, "currency": self.currency,
            "in_stock": self.in_stock, "status": self.status,
            "image": self.images[0].image_url if self.images else None,
            "colors": sorted({v.color for v in self.variants if v.color and v.stock_quantity > 0}),
            "sizes": sorted({v.size for v in self.variants if v.size and v.stock_quantity > 0}),
        }
        if detail:
            d.update(
                description=self.description, material=self.material, care=self.care, tags=self.tags or [],
                return_eligible=self.return_eligible,
                images=[i.to_dict() for i in self.images],
                variants=[v.to_dict() for v in self.variants],
            )
        return d


class ProductVariant(db.Model):
    __tablename__ = "product_variants"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    sku = db.Column(db.String(64), nullable=False, unique=True)
    size = db.Column(db.String(20), nullable=True)
    color = db.Column(db.String(40), nullable=True)
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.CheckConstraint("stock_quantity >= 0", name="ck_variant_stock_nonneg"),)

    def to_dict(self):
        return {"id": self.id, "sku": self.sku, "size": self.size, "color": self.color,
                "stock_quantity": self.stock_quantity, "available": self.stock_quantity > 0}


class ProductImage(db.Model):
    __tablename__ = "product_images"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    image_url = db.Column(db.String(500), nullable=False)
    alt_text = db.Column(db.String(255), nullable=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        return {"id": self.id, "image_url": self.image_url, "alt_text": self.alt_text}


class Wishlist(db.Model):
    __tablename__ = "wishlists"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    product = db.relationship("Product")
    __table_args__ = (db.UniqueConstraint("user_id", "product_id", name="uq_wishlist_user_product"),)


class Cart(db.Model):
    __tablename__ = "carts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    items = db.relationship("CartItem", backref="cart", cascade="all, delete-orphan", order_by="CartItem.id")


class CartItem(db.Model):
    __tablename__ = "cart_items"
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey("carts.id", ondelete="CASCADE"), nullable=False)
    product_variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price_minor = db.Column(db.Integer, nullable=False)  # price when added; NOT authoritative
    variant = db.relationship("ProductVariant")
    __table_args__ = (db.UniqueConstraint("cart_id", "product_variant_id", name="uq_cart_variant"),)


class Address(db.Model):
    __tablename__ = "addresses"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address_line_1 = db.Column(db.String(255), nullable=False)
    address_line_2 = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    postal_code = db.Column(db.String(12), nullable=False)
    country = db.Column(db.String(60), nullable=False, default="India")
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)  # soft delete: orders reference addresses

    def to_dict(self):
        return {c: getattr(self, c) for c in (
            "id", "recipient_name", "phone", "address_line_1", "address_line_2",
            "city", "state", "postal_code", "country", "is_default")}


class Order(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    address_id = db.Column(db.Integer, db.ForeignKey("addresses.id"), nullable=False)
    order_number = db.Column(db.String(32), nullable=False, unique=True)
    subtotal_minor = db.Column(db.Integer, nullable=False)
    discount_minor = db.Column(db.Integer, nullable=False, default=0)
    shipping_minor = db.Column(db.Integer, nullable=False, default=0)
    tax_minor = db.Column(db.Integer, nullable=False, default=0)
    total_minor = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    payment_status = db.Column(db.String(20), nullable=False, default="pending")
    order_status = db.Column(db.String(30), nullable=False, default="pending_payment", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    address = db.relationship("Address")
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan", order_by="OrderItem.id")

    def to_dict(self, detail=True):
        d = {
            "id": self.id, "order_number": self.order_number, "order_status": self.order_status,
            "payment_status": self.payment_status, "total_minor": self.total_minor, "currency": self.currency,
            "created_at": self.created_at.isoformat() + "Z", "item_count": sum(i.quantity for i in self.items),
        }
        if detail:
            d.update(subtotal_minor=self.subtotal_minor, discount_minor=self.discount_minor,
                     shipping_minor=self.shipping_minor, tax_minor=self.tax_minor,
                     address=self.address.to_dict() if self.address else None,
                     items=[i.to_dict() for i in self.items])
        return d


class OrderItem(db.Model):
    __tablename__ = "order_items"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    product_variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=False)
    product_name_snapshot = db.Column(db.String(200), nullable=False)
    sku_snapshot = db.Column(db.String(64), nullable=False)
    size_snapshot = db.Column(db.String(20), nullable=True)
    color_snapshot = db.Column(db.String(40), nullable=True)
    image_snapshot = db.Column(db.String(500), nullable=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price_minor = db.Column(db.Integer, nullable=False)
    line_total_minor = db.Column(db.Integer, nullable=False)

    def to_dict(self):
        return {"id": self.id, "product_id": self.product_id, "name": self.product_name_snapshot,
                "sku": self.sku_snapshot, "size": self.size_snapshot, "color": self.color_snapshot,
                "image": self.image_snapshot, "quantity": self.quantity,
                "unit_price_minor": self.unit_price_minor, "line_total_minor": self.line_total_minor}


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=True, index=True)
    payment_provider = db.Column(db.String(30), nullable=False)
    provider_order_id = db.Column(db.String(100), nullable=False, unique=True)
    provider_payment_id = db.Column(db.String(100), nullable=True)
    amount_minor = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    status = db.Column(db.String(20), nullable=False, default="pending")
    idempotency_key = db.Column(db.String(100), nullable=True, unique=True)
    purpose = db.Column(db.String(20), nullable=False, default="order")  # order | credit_pack | subscription
    reference_id = db.Column(db.Integer, nullable=True)  # pack id / subscription id for non-order payments
    meta = db.Column(db.JSON, nullable=True)  # snapshot of what was bought (e.g. pack credits) at purchase time
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class WebhookEvent(db.Model):
    """Every processed provider event id; the unique key makes webhooks idempotent."""
    __tablename__ = "webhook_events"
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(30), nullable=False)
    event_id = db.Column(db.String(100), nullable=False)
    event_type = db.Column(db.String(60), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    __table_args__ = (db.UniqueConstraint("provider", "event_id", name="uq_webhook_event"),)


class Refund(db.Model):
    """Full refund of a paid order. One per order (unique) so a refund can never be issued twice."""
    __tablename__ = "refunds"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, unique=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"), nullable=False)
    amount_minor = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    reason = db.Column(db.String(255), nullable=False)
    provider_refund_id = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="completed")
    restocked = db.Column(db.Boolean, nullable=False, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def to_dict(self):
        return {"id": self.id, "order_id": self.order_id, "amount_minor": self.amount_minor, "currency": self.currency,
                "reason": self.reason, "status": self.status, "restocked": self.restocked,
                "provider_refund_id": self.provider_refund_id, "created_at": self.created_at.isoformat() + "Z"}
