from marshmallow import Schema, ValidationError, fields, validate, validates_schema

_tag = fields.Str(validate=validate.Length(min=1, max=50))


def _tags():
    return fields.List(_tag, validate=validate.Length(max=20))


class AccountSchema(Schema):
    name = fields.Str(validate=validate.Length(min=1, max=120))
    phone = fields.Str(allow_none=True, validate=validate.Length(max=20))


class FashionSchema(Schema):
    preferred_styles = _tags()
    preferred_colors = _tags()
    preferred_brands = _tags()
    preferred_categories = _tags()
    occasion_preferences = _tags()
    budget_min_minor = fields.Int(allow_none=True, validate=validate.Range(min=0, max=100_000_000))
    budget_max_minor = fields.Int(allow_none=True, validate=validate.Range(min=0, max=100_000_000))
    fit_preferences = fields.Str(allow_none=True, validate=validate.Length(max=255))
    size_preferences = fields.Dict(keys=fields.Str(validate=validate.Length(max=30)),
                                   values=fields.Str(validate=validate.Length(max=30)))

    @validates_schema
    def check_budget(self, data, **kwargs):
        lo, hi = data.get("budget_min_minor"), data.get("budget_max_minor")
        if lo is not None and hi is not None and lo > hi:
            raise ValidationError("Minimum budget cannot exceed maximum.", "budget_min_minor")


class ForgotSchema(Schema):
    email = fields.Email(required=True)


class ResetSchema(Schema):
    token = fields.Str(required=True)
    password = fields.Str(required=True)


class TokenSchema(Schema):
    token = fields.Str(required=True)


class DeleteAccountSchema(Schema):
    password = fields.Str(required=True)
    confirm = fields.Str(required=True)
