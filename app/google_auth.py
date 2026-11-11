"""Verify Google Sign-In ID tokens (the `credential` returned by Google Identity Services)."""
from flask import current_app
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from .utils import ApiError

_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def verify_google_token(token):
    """Return the verified claims ({email, name, sub, ...}) or raise ApiError(401)."""
    client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    if not client_id:
        raise ApiError("Google sign-in is not configured", 503)
    try:
        claims = id_token.verify_oauth2_token(token, google_requests.Request(), client_id)
    except Exception:  # bad signature, expired, wrong audience, network failure...
        raise ApiError("Invalid Google credential", 401)
    if claims.get("iss") not in _ISSUERS or not claims.get("email") or not claims.get("email_verified"):
        raise ApiError("Google account email is not verified", 401)
    return claims
