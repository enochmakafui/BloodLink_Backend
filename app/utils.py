import re
from datetime import date
from functools import wraps

from flask import g
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

from .extensions import db

BLOOD_TYPES = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")
URGENCIES = ("critical", "urgent", "normal")
URGENCY_RANK = {"critical": 0, "urgent": 1, "normal": 2}
REQUEST_STATUSES = ("open", "fulfilled", "cancelled")
RESPONSE_STATUSES = ("accepted", "declined")

# donor blood type -> recipient blood types they can donate to
DONOR_COMPATIBILITY = {
    "O-": ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"],
    "O+": ["O+", "A+", "B+", "AB+"],
    "A-": ["A-", "A+", "AB-", "AB+"],
    "A+": ["A+", "AB+"],
    "B-": ["B-", "B+", "AB-", "AB+"],
    "B+": ["B+", "AB+"],
    "AB-": ["AB-", "AB+"],
    "AB+": ["AB+"],
}


def donor_types_for(requested_type):
    """Donor blood types that can donate to `requested_type`."""
    return [d for d, targets in DONOR_COMPATIBILITY.items() if requested_type in targets]


def same_text(a, b):
    return (a or "").strip().lower() == (b or "").strip().lower()


def donor_matches_request(donor, blood_request):
    """True if `donor` is eligible to see/respond to `blood_request` (MVP matching rules)."""
    return bool(
        donor.is_available
        and blood_request.blood_type in DONOR_COMPATIBILITY[donor.blood_type]
        and same_text(donor.region, blood_request.hospital.region)
    )


# ---------------------------------------------------------------- errors

class ApiError(Exception):
    """Raise anywhere in a route; rendered as {"error": message}."""

    def __init__(self, message, status=400, code=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code  # optional machine-readable code for the frontend


# ---------------------------------------------------------------- auth

def role_required(*roles):
    """Protect a route: valid JWT, active user, and role in `roles`."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from .models import User

            verify_jwt_in_request()
            if get_jwt().get("role") not in roles:
                raise ApiError("You do not have permission to access this resource", 403)
            user = db.session.get(User, int(get_jwt_identity()))
            if user is None or not user.is_active or user.role not in roles:
                raise ApiError("Account not found or deactivated", 401)
            g.current_user = user
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def login_required(fn):
    """Any logged-in, active user."""
    return role_required("donor", "hospital", "admin")(fn)


# ---------------------------------------------------------------- validation

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_LOCAL_RE = re.compile(r"^0\d{9}$")
PHONE_INTL_RE = re.compile(r"^\+233\d{9}$")


def json_body(request):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object")
    return data


def clean_str(data, key, required=True, max_len=255):
    value = data.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ApiError(f"'{key}' is required")
        return None
    if not isinstance(value, str):
        raise ApiError(f"'{key}' must be a string")
    value = value.strip()
    if len(value) > max_len:
        raise ApiError(f"'{key}' must be at most {max_len} characters")
    return value


def valid_email(data):
    email = clean_str(data, "email").lower()
    if not EMAIL_RE.match(email):
        raise ApiError("Invalid email address")
    return email


def valid_password(data):
    password = data.get("password")
    if not isinstance(password, str) or len(password) < 8:
        raise ApiError("Password must be at least 8 characters")
    return password


def valid_phone(data, key="phone"):
    phone = clean_str(data, key).replace(" ", "")
    if not (PHONE_LOCAL_RE.match(phone) or PHONE_INTL_RE.match(phone)):
        raise ApiError("Phone must be a Ghana number: 0XXXXXXXXX or +233XXXXXXXXX")
    return phone


def valid_choice(data, key, choices, upper=False, lower=False):
    value = clean_str(data, key)
    if upper:
        value = value.upper()
    if lower:
        value = value.lower()
    if value not in choices:
        raise ApiError(f"'{key}' must be one of: {', '.join(choices)}")
    return value


def valid_bool(data, key):
    if not isinstance(data[key], bool):
        raise ApiError(f"'{key}' must be true or false")
    return data[key]


def valid_date(data, key):
    value = data[key]
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ApiError(f"'{key}' must be a date in YYYY-MM-DD format")
    if parsed > date.today():
        raise ApiError(f"'{key}' cannot be in the future")
    return parsed


# ---------------------------------------------------------------- notifications / sms

def notify(user_id, message):
    """Add a notification to the session (caller commits)."""
    from .models import Notification

    db.session.add(Notification(user_id=user_id, message=message))
    # TODO: also call send_sms() once an SMS provider is chosen.


def send_sms(phone, message):
    """STUB - SMS is out of scope for the MVP.

    TODO: integrate a Ghana SMS provider (to be decided) and call this from notify().
    """
    return None
