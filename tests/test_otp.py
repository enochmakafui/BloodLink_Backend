import re
from datetime import timedelta

from app.extensions import db
from app.models import OtpCode, User, utcnow

DONOR = {"email": "otp@test.com", "password": "password123", "full_name": "Ama", "phone": "0241234567",
         "blood_type": "O+", "city": "Accra", "region": "Greater Accra"}


def last_code(app, to="otp@test.com"):
    mails = [m for m in app.extensions.get("outbox", []) if m["to"] == to]
    assert mails, "no email was sent"
    return re.search(r"\b(\d{6})\b", mails[-1]["text"]).group(1)


def expire_cooldown():
    """Pretend the last code was issued long ago so the resend cooldown has passed."""
    for o in OtpCode.query.all():
        o.created_at = utcnow() - timedelta(minutes=5)
    db.session.commit()


def register(client):
    r = client.post("/api/auth/register/donor", json=DONOR)
    assert r.status_code == 201
    return r.get_json()


def test_register_sends_otp_and_marks_unverified(client, app):
    body = register(client)
    assert body["verification_required"] is True
    assert body["email_verified"] is False
    code = last_code(app)
    assert len(code) == 6
    assert code not in OtpCode.query.one().code_hash  # stored hashed, never plain


def test_login_blocked_until_verified(client, app):
    register(client)
    r = client.post("/api/auth/login", json={"email": DONOR["email"], "password": "password123"})
    assert r.status_code == 403 and r.get_json()["code"] == "email_not_verified"


def test_verify_email_then_login(client, app):
    register(client)
    r = client.post("/api/auth/verify-email", json={"email": "OTP@test.com", "otp": last_code(app)})
    assert r.status_code == 200
    assert r.get_json()["user"]["email_verified"] is True and r.get_json()["access_token"]
    assert client.post("/api/auth/login", json={"email": DONOR["email"], "password": "password123"}).status_code == 200


def test_wrong_code_rejected_and_attempts_limited(client, app):
    register(client)
    good = last_code(app)
    bad = "000000" if good != "000000" else "111111"
    for _ in range(5):
        assert client.post("/api/auth/verify-email", json={"email": DONOR["email"], "otp": bad}).status_code == 400
    # code is now locked, even the right one fails
    r = client.post("/api/auth/verify-email", json={"email": DONOR["email"], "otp": good})
    assert r.status_code == 400 and r.get_json()["error"] == "Invalid or expired code"


def test_code_is_single_use(client, app):
    register(client)
    code = last_code(app)
    assert client.post("/api/auth/verify-email", json={"email": DONOR["email"], "otp": code}).status_code == 200
    assert client.post("/api/auth/verify-email", json={"email": DONOR["email"], "otp": code}).status_code == 400


def test_expired_code_rejected(client, app):
    register(client)
    o = OtpCode.query.one()
    o.expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    assert client.post("/api/auth/verify-email",
                       json={"email": DONOR["email"], "otp": last_code(app)}).status_code == 400


def test_resend_cooldown_and_new_code_invalidates_old(client, app):
    register(client)
    first = last_code(app)
    client.post("/api/auth/resend-otp", json={"email": DONOR["email"]})
    assert len(app.extensions["outbox"]) == 1  # inside cooldown: nothing sent, same generic reply
    expire_cooldown()
    r = client.post("/api/auth/resend-otp", json={"email": DONOR["email"]})
    assert r.status_code == 200 and len(app.extensions["outbox"]) == 2
    second = last_code(app)
    if first != second:
        assert client.post("/api/auth/verify-email", json={"email": DONOR["email"], "otp": first}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"email": DONOR["email"], "otp": second}).status_code == 200


def test_no_user_enumeration(client, app):
    unknown = client.post("/api/auth/forgot-password", json={"email": "nobody@test.com"})
    register(client)
    known = client.post("/api/auth/forgot-password", json={"email": DONOR["email"]})
    assert unknown.status_code == known.status_code == 200
    assert unknown.get_json() == known.get_json()
    assert client.post("/api/auth/resend-otp", json={"email": "nobody@test.com"}).status_code == 200
    assert client.post("/api/auth/verify-email",
                       json={"email": "nobody@test.com", "otp": "123456"}).status_code == 400


def test_reset_password_flow(client, app):
    register(client)
    expire_cooldown()
    client.post("/api/auth/forgot-password", json={"email": DONOR["email"]})
    code = last_code(app)
    short = client.post("/api/auth/reset-password",
                        json={"email": DONOR["email"], "otp": code, "new_password": "short"})
    assert short.status_code == 400
    ok = client.post("/api/auth/reset-password",
                     json={"email": DONOR["email"], "otp": code, "new_password": "brandnew123"})
    assert ok.status_code == 200
    assert client.post("/api/auth/login", json={"email": DONOR["email"], "password": "password123"}).status_code == 401
    # resetting also verified the email, so the new password logs in directly
    assert client.post("/api/auth/login", json={"email": DONOR["email"], "password": "brandnew123"}).status_code == 200


def test_verify_code_not_valid_for_password_reset(client, app):
    register(client)
    code = last_code(app)  # a verify_email code
    r = client.post("/api/auth/reset-password",
                    json={"email": DONOR["email"], "otp": code, "new_password": "brandnew123"})
    assert r.status_code == 400
    assert User.query.filter_by(email=DONOR["email"]).one().check_password("password123")


def test_missing_email_rejected(client):
    assert client.post("/api/auth/verify-email", json={"otp": "123456"}).status_code == 400
