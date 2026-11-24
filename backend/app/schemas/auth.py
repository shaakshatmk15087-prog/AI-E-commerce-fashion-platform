from marshmallow import Schema, ValidationError, fields, validate, validates


def validate_password(value):
    if len(value) < 8:
        raise ValidationError("Password must be at least 8 characters.")
    if value.lower() == value or not any(c.isdigit() for c in value):
        raise ValidationError("Password needs an uppercase letter and a digit.")


class RegisterSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=120))
    email = fields.Email(required=True)
    password = fields.Str(required=True, load_only=True)
    phone = fields.Str(load_default=None, validate=validate.Length(max=20))
    referral_code = fields.Str(load_default=None, validate=validate.Length(max=12))

    @validates("password")
    def check_password(self, value, **kwargs):
        validate_password(value)


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True)
