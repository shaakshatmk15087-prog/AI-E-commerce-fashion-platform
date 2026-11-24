from marshmallow import Schema, ValidationError, fields, validate, validates_schema


class QuoteSchema(Schema):
    service = fields.Str(required=True, validate=validate.Length(min=1, max=40))


class PlanIdSchema(Schema):
    plan_id = fields.Int(required=True)


class PackInSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    credits = fields.Int(required=True, validate=validate.Range(min=1, max=100000))
    price_minor = fields.Int(required=True, validate=validate.Range(min=100, max=100_000_000))
    is_active = fields.Bool(load_default=True)


class PlanInSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    description = fields.Str(allow_none=True, load_default=None, validate=validate.Length(max=1000))
    price_minor = fields.Int(required=True, validate=validate.Range(min=100, max=100_000_000))
    billing_interval = fields.Str(load_default="month", validate=validate.OneOf(["month", "year"]))
    super_credit_amount = fields.Int(required=True, validate=validate.Range(min=1, max=100000))
    grant_frequency = fields.Str(load_default="renewal", validate=validate.OneOf(["renewal", "daily"]))
    benefits = fields.List(fields.Str(validate=validate.Length(max=120)), load_default=list, validate=validate.Length(max=12))
    is_active = fields.Bool(load_default=True)


class AdjustSchema(Schema):
    credit_type = fields.Str(required=True, validate=validate.OneOf(["daily", "super"]))
    amount = fields.Int(required=True)
    reason = fields.Str(required=True, validate=validate.Length(min=3, max=200))

    @validates_schema
    def nonzero(self, data, **kwargs):
        if data["amount"] == 0 or abs(data["amount"]) > 100000:
            raise ValidationError("Amount must be non-zero and at most 100000.", "amount")
