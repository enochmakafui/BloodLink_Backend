import secrets

from flask import Blueprint, g, jsonify, request
from flask_jwt_extended import create_access_token

from ..extensions import db
from ..models import DonorProfile, HospitalProfile, User
from ..google_auth import verify_google_token
from ..otp import RESET_PASSWORD, VERIFY_EMAIL, check_otp, issue_otp
from ..utils import (BLOOD_TYPES, ApiError, clean_str, json_body, login_required,
                     valid_choice, valid_email, valid_password, valid_phone)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _create_user(data, role):
    email = valid_email(data)
    password = valid_password(data)
    if User.query.filter_by(email=email).first():
        raise ApiError("Email is already registered", 409)
    user = User(email=email, role=role)
    user.set_password(password)
    return user


def _user_with_profile(user):
    out = user.to_dict()
    out["profile"] = user.profile.to_dict() if user.profile else None
    return out


def _login_payload(user):
    token = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
    return {"access_token": token, "role": user.role, "user": _user_with_profile(user)}


def _registered(user):
    """201 response for a new account; an email OTP is sent for verification."""
    issue_otp(user, VERIFY_EMAIL)
    out = _user_with_profile(user)
    out["verification_required"] = True
    return jsonify(out), 201


def _user_by_email(data):
    email = data.get("email")
    if not isinstance(email, str) or not email.strip():
        raise ApiError("'email' is required")
    return User.query.filter_by(email=email.strip().lower()).first()


def _donor_profile(data):
    return DonorProfile(
        full_name=clean_str(data, "full_name", max_len=120),
        phone=valid_phone(data),
        blood_type=valid_choice(data, "blood_type", BLOOD_TYPES, upper=True),
        city=clean_str(data, "city", max_len=80),
        region=clean_str(data, "region", max_len=80),
        gps_address=clean_str(data, "gps_address", required=False, max_len=30),
    )


def _hospital_profile(data):
    return HospitalProfile(
        name=clean_str(data, "name", max_len=160),
        phone=valid_phone(data),
        city=clean_str(data, "city", max_len=80),
        region=clean_str(data, "region", max_len=80),
        address=clean_str(data, "address"),
        gps_address=clean_str(data, "gps_address", required=False, max_len=30),
    )


@bp.post("/register/donor")
def register_donor():
    data = json_body(request)
    user = _create_user(data, "donor")
    user.donor_profile = _donor_profile(data)
    db.session.add(user)
    db.session.commit()
    return _registered(user)


@bp.post("/register/hospital")
def register_hospital():
    data = json_body(request)
    user = _create_user(data, "hospital")
    user.hospital_profile = _hospital_profile(data)
    db.session.add(user)
    db.session.commit()
    return _registered(user)


@bp.post("/login")
def login():
    data = json_body(request)
    email = (data.get("email") or "").strip().lower() if isinstance(data.get("email"), str) else ""
    password = data.get("password")
    if not email or not isinstance(password, str):
        raise ApiError("Email and password are required")
    user = User.query.filter_by(email=email).first()
    if user is None or not user.check_password(password):
        raise ApiError("Invalid email or password", 401)
    if not user.is_active:
        raise ApiError("This account has been deactivated", 403)
    if not user.email_verified:
        raise ApiError("Please verify your email before logging in", 403, code="email_not_verified")
    return jsonify(_login_payload(user))


@bp.post("/google")
def google_sign_in():
    """Sign in (or sign up) with a Google ID token.

    Existing account -> signed in (200). New email -> 404 `registration_required` until the client
    resends with `role` + the profile fields, which creates a verified account (201).
    """
    data = json_body(request)
    token = data.get("id_token") or data.get("credential")
    if not isinstance(token, str) or not token:
        raise ApiError("'id_token' is required")
    claims = verify_google_token(token)
    email = claims["email"].strip().lower()

    user = User.query.filter_by(email=email).first()
    if user is not None:
        if not user.is_active:
            raise ApiError("This account has been deactivated", 403)
        if not user.email_verified:
            # Google has proven ownership of the inbox. Rotate the password so whoever
            # pre-registered this address (unverified) can no longer sign in with theirs.
            user.set_password(secrets.token_urlsafe(32))
            user.email_verified = True
            db.session.commit()
        return jsonify(_login_payload(user))

    role = data.get("role")
    if role is None:
        body = {"error": "No account exists for this Google email. Choose a role and complete your profile.",
                "code": "registration_required", "email": email, "name": claims.get("name")}
        return jsonify(body), 404
    if role not in ("donor", "hospital"):
        raise ApiError("'role' must be 'donor' or 'hospital'")

    profile = _donor_profile(data) if role == "donor" else _hospital_profile(data)
    user = User(email=email, role=role, email_verified=True)
    user.set_password(secrets.token_urlsafe(32))  # unusable; they can set one via forgot-password
    if role == "donor":
        user.donor_profile = profile
    else:
        user.hospital_profile = profile
    db.session.add(user)
    db.session.commit()
    return jsonify(_login_payload(user)), 201


@bp.get("/me")
@login_required
def me():
    return jsonify(_user_with_profile(g.current_user))


# ---------------------------------------------------------------- email OTP

GENERIC_SENT = {"message": "If that email is registered, a code has been sent."}


@bp.post("/verify-email")
def verify_email():
    data = json_body(request)
    user = _user_by_email(data)
    check_otp(user, VERIFY_EMAIL, data.get("otp"))
    user.email_verified = True
    db.session.commit()
    return jsonify(_login_payload(user))  # verified -> sign the user straight in


@bp.post("/resend-otp")
def resend_otp():
    user = _user_by_email(json_body(request))
    if user is not None and user.is_active and not user.email_verified:
        issue_otp(user, VERIFY_EMAIL)  # silently skipped inside the cooldown
    return jsonify(GENERIC_SENT)


@bp.post("/forgot-password")
def forgot_password():
    user = _user_by_email(json_body(request))
    if user is not None and user.is_active:
        issue_otp(user, RESET_PASSWORD)
    return jsonify(GENERIC_SENT)


@bp.post("/reset-password")
def reset_password():
    data = json_body(request)
    new_password = data.get("new_password")
    if not isinstance(new_password, str) or len(new_password) < 8:
        raise ApiError("Password must be at least 8 characters")
    user = _user_by_email(data)
    check_otp(user, RESET_PASSWORD, data.get("otp"))
    user.set_password(new_password)
    user.email_verified = True  # they just proved they control the inbox
    db.session.commit()
    return jsonify({"message": "Password updated. You can now sign in."})
