import json
import urllib.error
import urllib.request

from flask import current_app

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def send_email(to_email, subject, text, html=None):
    """Send a transactional email through Brevo. Returns True on success, never raises.

    Under TESTING the message is appended to app.extensions["outbox"] instead of being sent.
    """
    app = current_app
    if app.config.get("TESTING"):
        app.extensions.setdefault("outbox", []).append({"to": to_email, "subject": subject, "text": text})
        return True

    api_key = app.config.get("BREVO_API_KEY")
    sender = app.config.get("BREVO_SENDER_EMAIL")
    if not api_key or not sender:
        app.logger.error("Brevo is not configured (BREVO_API_KEY / BREVO_SENDER_EMAIL); email not sent")
        return False

    payload = {
        "sender": {"name": app.config.get("BREVO_SENDER_NAME") or "BloodLink", "email": sender},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": text,
    }
    if html:
        payload["htmlContent"] = html
    req = urllib.request.Request(
        BREVO_URL,
        data=json.dumps(payload).encode(),
        headers={"api-key": api_key, "accept": "application/json", "content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        # Brevo's error body describes the problem (e.g. unverified sender); it never contains our key.
        app.logger.error("Brevo rejected email (HTTP %s): %s", e.code, e.read()[:300])
    except Exception as e:  # network error, timeout...
        app.logger.error("Brevo request failed: %s", e)
    return False
