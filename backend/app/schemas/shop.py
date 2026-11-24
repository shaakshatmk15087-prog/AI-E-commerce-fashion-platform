from marshmallow import Schema, ValidationError, fields, validate, validates, validates_schema


class AddressSchema(Schema):
    recipient_name = fields.Str(required=True, validate=validate.Length(min=1, max=120))
    phone = fields.Str(required=True, validate=validate.Regexp(r"^[0-9+\- ]{7,20}$"))
    address_line_1 = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    address_line_2 = fields.Str(allow_none=True, load_default=None, validate=validate.Length(max=255))
    city = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    state = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    postal_code = fields.Str(required=True, validate=validate.Regexp(r"^[0-9A-Za-z \-]{3,12}$"))
    country = fields.Str(load_default="India", validate=validate.Length(min=1, max=60))
    is_default = fields.Bool(load_default=False)


class CartAddSchema(Schema):
    variant_id = fields.Int(required=True)
    quantity = fields.Int(load_default=1, validate=validate.Range(min=1, max=10))


class CartUpdateSchema(Schema):
    quantity = fields.Int(required=True, validate=validate.Range(min=1, max=10))


class CheckoutSchema(Schema):
    address_id = fields.Int(required=True)


class PayOrderSchema(Schema):
    order_id = fields.Int(required=True)


class MockPaySchema(Schema):
    order_id = fields.Int(load_default=None)
    provider_order_id = fields.Str(load_default=None, validate=validate.Length(max=100))
    outcome = fields.Str(required=True, validate=validate.OneOf(["success", "failure"]))

    @validates_schema
    def exactly_one(self, data, **kwargs):
        if bool(data.get("order_id")) == bool(data.get("provider_order_id")):
            raise ValidationError("Provide exactly one of order_id or provider_order_id.", "order_id")


def _http_url(v):
    if not (v.startswith("https://") or v.startswith("http://")):
        raise ValidationError("Must be an http(s) URL.")


class VariantInSchema(Schema):
    id = fields.Int(load_default=None)
    sku = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    size = fields.Str(allow_none=True, load_default=None, validate=validate.Length(max=20))
    color = fields.Str(allow_none=True, load_default=None, validate=validate.Length(max=40))
    stock_quantity = fields.Int(required=True, validate=validate.Range(min=0, max=1_000_000))


class ImageInSchema(Schema):
    image_url = fields.Str(required=True, validate=[validate.Length(max=500), _http_url])
    alt_text = fields.Str(allow_none=True, load_default=None, validate=validate.Length(max=255))


class ProductInSchema(Schema):
    category_id = fields.Int(required=True)
    name = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    description = fields.Str(allow_none=True, load_default=None)
    brand = fields.Str(allow_none=True, load_default=None, validate=validate.Length(max=100))
    price_minor = fields.Int(required=True, validate=validate.Range(min=1, max=100_000_000))
    sale_price_minor = fields.Int(allow_none=True, load_default=None, validate=validate.Range(min=1))
    status = fields.Str(load_default="active", validate=validate.OneOf(["active", "draft", "archived"]))
    material = fields.Str(allow_none=True, load_default=None, validate=validate.Length(max=255))
    care = fields.Str(allow_none=True, load_default=None, validate=validate.Length(max=255))
    tags = fields.List(fields.Str(validate=validate.Length(max=40)), load_default=list, validate=validate.Length(max=30))
    return_eligible = fields.Bool(load_default=True)
    variants = fields.List(fields.Nested(VariantInSchema), required=True, validate=validate.Length(min=1, max=100))
    images = fields.List(fields.Nested(ImageInSchema), load_default=list, validate=validate.Length(max=12))

    @validates_schema
    def check(self, data, **kwargs):
        sp = data.get("sale_price_minor")
        if sp is not None and sp >= data["price_minor"]:
            raise ValidationError("Sale price must be lower than the price.", "sale_price_minor")
        skus = [v["sku"] for v in data["variants"]]
        if len(skus) != len(set(skus)):
            raise ValidationError("Duplicate SKUs.", "variants")


class CategoryInSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    parent_id = fields.Int(allow_none=True, load_default=None)
    description = fields.Str(allow_none=True, load_default=None)
    is_active = fields.Bool(load_default=True)


class OrderStatusSchema(Schema):
    order_status = fields.Str(required=True)

    @validates("order_status")
    def known(self, value, **kwargs):
        from ..models import ORDER_STATUSES
        if value not in ORDER_STATUSES:
            raise ValidationError("Unknown status.")
