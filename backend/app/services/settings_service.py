"""Admin-configurable credit rules, stored in platform_settings. Every value here is a PLACEHOLDER default for
business decisions that are still open (spec section 17); admins change them at runtime via /admin/settings/credits."""
import copy
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..extensions import db
from ..models import PlatformSetting
from .errors import ShopError

KNOWN_SERVICES = {"ai_chat": "AI stylist chat message", "consultation_text": "Text consultation with a stylist"}

DEFAULT_CREDITS = {
    "daily_allowance": 10,               # example value from the original concept, not a fixed rule
    "reset_timezone": "Asia/Kolkata",    # daily period boundary timezone
    "reset_hour": 0,                     # local hour at which the daily period rolls over (0 = midnight)
    "spend_priority": "daily_first",     # daily_first | super_first
    "services": {
        "ai_chat": {"cost": 0, "credit_types": ["daily", "super"]},  # cost 0 = free until decided
        # Super-only: Daily Credits would lapse before a booked session happens. Per-stylist prices can override cost.
        "consultation_text": {"cost": 30, "credit_types": ["super"]},
    },
}
KEY = "credits"


def get_credit_settings():
    row = db.session.get(PlatformSetting, KEY)
    cfg = copy.deepcopy(DEFAULT_CREDITS)
    if row:
        stored = row.value or {}
        for k, v in stored.items():
            if k == "services":
                for name, sv in v.items():
                    if name in cfg["services"]:
                        cfg["services"][name].update(sv)
            else:
                cfg[k] = v
    return cfg


def _is_int(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def validate_credit_settings(data):
    """Returns a cleaned full settings dict or raises ShopError(400)."""
    errs, out = {}, copy.deepcopy(get_credit_settings())
    msg = lambda lo, hi: [f"Must be a whole number between {lo} and {hi}."]

    for key, lo, hi in (("daily_allowance", 0, 1000), ("reset_hour", 0, 23)):
        if key in data:
            if _is_int(data[key], lo, hi):
                out[key] = data[key]
            else:
                errs[key] = msg(lo, hi)
    if "reset_timezone" in data:
        try:
            ZoneInfo(str(data["reset_timezone"]))
            out["reset_timezone"] = str(data["reset_timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            errs["reset_timezone"] = ["Unknown timezone (use an IANA name such as Asia/Kolkata)."]
    if "spend_priority" in data:
        if data["spend_priority"] in ("daily_first", "super_first"):
            out["spend_priority"] = data["spend_priority"]
        else:
            errs["spend_priority"] = ["Must be daily_first or super_first."]
    services = data.get("services") or {}
    if not isinstance(services, dict):
        errs["services"] = ["Must be an object."]
        services = {}
    for name, sv in services.items():
        if name not in KNOWN_SERVICES or not isinstance(sv, dict):
            errs[f"services.{name}"] = ["Unknown service."]
            continue
        if "cost" in sv:
            if _is_int(sv["cost"], 0, 1000):
                out["services"][name]["cost"] = sv["cost"]
            else:
                errs[f"services.{name}.cost"] = msg(0, 1000)
        if "credit_types" in sv:
            ct = sv["credit_types"]
            if isinstance(ct, list) and ct and set(ct) <= {"daily", "super"}:
                out["services"][name]["credit_types"] = list(dict.fromkeys(ct))
            else:
                errs[f"services.{name}.credit_types"] = ["Choose daily, super or both."]
    for k in set(data) - {"daily_allowance", "reset_hour", "reset_timezone", "spend_priority", "services"}:
        errs[k] = ["Unknown setting."]
    if errs:
        raise ShopError("Validation failed", 400, errs)
    return out


def save_credit_settings(cleaned):
    row = db.session.get(PlatformSetting, KEY)
    if row:
        row.value = cleaned
    else:
        db.session.add(PlatformSetting(key=KEY, value=cleaned))


# ---- Consultation and rewards policies (generic integer sections) -------------------------------------
DEFAULT_CONSULTATIONS = {
    "stylist_share_percent": 70,       # share of the credit cost recorded as the stylist's earnings (a record, not a payout)
    "cancel_full_refund_hours": 24,    # customer cancels at least this long before the start: full refund
    "late_cancel_refund_percent": 50,  # ...later than that: this percentage is refunded
    "request_expiry_hours": 24,        # unanswered requests expire (full refund) after this long
    "min_notice_hours": 2,             # slots starting sooner than this can't be booked
    "reminder_minutes": 60,            # in-app reminder this long before an accepted session
}
CONSULTATION_RANGES = {"stylist_share_percent": (0, 100), "cancel_full_refund_hours": (0, 720),
                       "late_cancel_refund_percent": (0, 100), "request_expiry_hours": (1, 168),
                       "min_notice_hours": (0, 168), "reminder_minutes": (5, 1440)}
DEFAULT_REWARDS = {
    "points_per_100_inr": 1,       # points earned per full INR 100 of a delivered, paid order
    "referrer_points": 100,        # to the referrer when the referred friend's first order is delivered
    "referred_points": 50,         # to the referred friend at the same moment
    "max_rewarded_referrals": 20,  # anti-abuse cap per referrer
}
REWARD_RANGES = {"points_per_100_inr": (0, 100), "referrer_points": (0, 10000), "referred_points": (0, 10000),
                 "max_rewarded_referrals": (0, 1000)}
SECTIONS = {"consultations": (DEFAULT_CONSULTATIONS, CONSULTATION_RANGES), "rewards": (DEFAULT_REWARDS, REWARD_RANGES)}


def get_section(key):
    defaults, _ = SECTIONS[key]
    row = db.session.get(PlatformSetting, key)
    out = dict(defaults)
    if row:
        out.update({k: v for k, v in (row.value or {}).items() if k in defaults})
    return out


def validate_section(key, data):
    defaults, ranges = SECTIONS[key]
    out, errs = get_section(key), {}
    for k, v in data.items():
        if k not in defaults:
            errs[k] = ["Unknown setting."]
        elif not _is_int(v, *ranges[k]):
            errs[k] = [f"Must be a whole number between {ranges[k][0]} and {ranges[k][1]}."]
        else:
            out[k] = v
    if errs:
        raise ShopError("Validation failed", 400, errs)
    return out


def save_section(key, cleaned):
    row = db.session.get(PlatformSetting, key)
    if row:
        row.value = cleaned
    else:
        db.session.add(PlatformSetting(key=key, value=cleaned))
