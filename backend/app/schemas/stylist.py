from marshmallow import Schema, ValidationError, fields, validate, validates_schema

_tags = lambda: fields.List(fields.Str(validate=validate.Length(min=1, max=50)), load_default=list, validate=validate.Length(max=15))


class StylistProfileSchema(Schema):
    bio = fields.Str(allow_none=True, load_default=None, validate=validate.Length(max=2000))
    expertise = _tags()
    languages = _tags()
    is_available = fields.Bool(load_default=True)


class SlotSchema(Schema):
    start_at = fields.DateTime(required=True)  # ISO 8601; naive values are treated as UTC
    duration_minutes = fields.Int(load_default=30, validate=validate.Range(min=15, max=120))


class BookSchema(Schema):
    slot_id = fields.Int(required=True)
    notes = fields.Str(allow_none=True, load_default=None, validate=validate.Length(max=500))


class QuoteSlotSchema(Schema):
    slot_id = fields.Int(required=True)


class MessageSchema(Schema):
    text = fields.Str(required=True, validate=validate.Length(min=1, max=1000))


class AdminStylistSchema(Schema):
    user_id = fields.Int(load_default=None)  # required on create only
    bio = fields.Str(allow_none=True, load_default=None, validate=validate.Length(max=2000))
    expertise = _tags()
    languages = _tags()
    price_credits_text = fields.Int(allow_none=True, load_default=None, validate=validate.Range(min=0, max=100000))
    is_approved = fields.Bool(load_default=False)
    is_available = fields.Bool(load_default=True)


class OfferSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    points_cost = fields.Int(required=True, validate=validate.Range(min=1, max=1_000_000))
    super_credits = fields.Int(required=True, validate=validate.Range(min=1, max=100000))
    is_active = fields.Bool(load_default=True)


class RedeemSchema(Schema):
    offer_id = fields.Int(required=True)


class ReadSchema(Schema):
    ids = fields.List(fields.Int(), load_default=None)
