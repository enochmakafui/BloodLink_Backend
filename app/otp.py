import hashlib
import hmac
import secrets
from datetime import timedelta

from flask import current_app

from .extensions import db
from .mailer import send_email
from .models import OtpCode, utcnow
from .utils import ApiError

VERIFY_EMAIL = "verify_email"
RESET_PASSWORD = "reset_password"

_COPY = {
    VERIFY_EMAIL: ("Verify your BloodLink email", "Your BloodLink verification code is {code}."),
    RESET_PASSWORD: ("Reset your BloodLink password", "Your BloodLink password reset code is {code}."),
}


def _hash(user_id, purpose, code):
    key = current_app.config["SECRET_KEY"].encode()
    return hmac.new(key, f"{user_id}:{purpose}:{code}".encode(), hashlib.sha256).hexdigest()


def issue_otp(user, purpose):
    """Create and email a fresh code. Returns False (silently) if still inside the resend cooldown.

    Callers must not reveal the return value to unauthenticated clients (avoids user enumeration).
    """
    cfg = current_app.config
    now = utcnow()
    latest = (OtpCode.query.filter_by(user_id=user.id, purpose=purpose)
              .order_by(OtpCode.id.desc()).first())
    if latest and latest.created_at > now - timedelta(seconds=cfg["OTP_RESEND_SECONDS"]):
        return False

    # A new code replaces any earlier unused ones
    OtpCode.query.filter_by(user_id=user.id, purpose=purpose, used=False).update({"used": True})
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.session.add(OtpCode(
        user_id=user.id, purpose=purpose, code_hash=_hash(user.id, purpose, code),
        expires_at=now + timedelta(minutes=cfg["OTP_TTL_MINUTES"]),
    ))
    db.session.commit()

    subject, template = _COPY[purpose]
    minutes = cfg["OTP_TTL_MINUTES"]
    text = (f"{template.format(code=code)}\n\nIt expires in {minutes} minutes. "
            "If you didn't request it, ignore this email.")
    sent = send_email(user.email, subject, text)
    if cfg.get("DEV_LOG_OTP"):
        current_app.logger.warning("DEV_LOG_OTP: %s code for %s is %s", purpose, user.email, code)
    return sent


def check_otp(user, purpose, code):
    """Validate a code and mark it used; raises one generic error for every failure mode."""
    invalid = ApiError("Invalid or expired code", 400)
    if user is None or not isinstance(code, str) or not code.strip():
        raise invalid
    now = utcnow()
    otp = (OtpCode.query.filter_by(user_id=user.id, purpose=purpose, used=False)
           .order_by(OtpCode.id.desc()).first())
    if otp is None or otp.expires_at < now or otp.attempts >= current_app.config["OTP_MAX_ATTEMPTS"]:
        raise invalid
    if not hmac.compare_digest(otp.code_hash, _hash(user.id, purpose, code.strip())):
        otp.attempts += 1
        db.session.commit()
        raise invalid
    otp.used = True
    db.session.flush()
