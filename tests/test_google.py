import pytest

from app.models import User
from app.utils import ApiError

DONOR = {"full_name": "Ama Owusu", "phone": "0241234567", "blood_type": "A+",
         "city": "Accra", "region": "Greater Accra"}


@pytest.fixture()
def google(monkeypatch):
    """Fake Google: the token string is the email address (or 'bad')."""
    def fake(token):
        if token == "bad":
            raise ApiError("Invalid Google credential", 401)
        return {"email": token, "email_verified": True, "name": "Ama Owusu"}
    monkeypatch.setattr("app.routes.auth.verify_google_token", fake)


def test_new_google_user_needs_registration(client, google):
    r = client.post("/api/auth/google", json={"id_token": "ama@gmail.com"})
    assert r.status_code == 404
    body = r.get_json()
    assert body["code"] == "registration_required" and body["email"] == "ama@gmail.com"


def test_google_signup_donor_then_signin(client, google):
    r = client.post("/api/auth/google", json={"id_token": "ama@gmail.com", "role": "donor", **DONOR})
    assert r.status_code == 201
    body = r.get_json()
    assert body["role"] == "donor" and body["access_token"] and body["user"]["email_verified"] is True
    assert body["user"]["profile"]["blood_type"] == "A+"
    r = client.post("/api/auth/google", json={"credential": "ama@gmail.com"})
    assert r.status_code == 200 and r.get_json()["role"] == "donor"
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200


def test_google_signup_hospital_and_validation(client, google):
    bad = client.post("/api/auth/google", json={"id_token": "h@gmail.com", "role": "hospital", "name": "X"})
    assert bad.status_code == 400
    assert User.query.count() == 0
    assert client.post("/api/auth/google", json={"id_token": "h@gmail.com", "role": "admin"}).status_code == 400
    ok = client.post("/api/auth/google", json={
        "id_token": "h@gmail.com", "role": "hospital", "name": "Korle Bu", "phone": "0302000000",
        "city": "Accra", "region": "Greater Accra", "address": "Guggisberg Ave"})
    assert ok.status_code == 201 and ok.get_json()["role"] == "hospital"


def test_google_bad_token_and_missing(client, google):
    assert client.post("/api/auth/google", json={"id_token": "bad"}).status_code == 401
    assert client.post("/api/auth/google", json={}).status_code == 400


def test_google_signs_in_existing_and_blocks_deactivated(client, google, make_donor, admin_headers):
    make_donor("d@test.com")
    r = client.post("/api/auth/google", json={"id_token": "d@test.com"})
    assert r.status_code == 200 and r.get_json()["user"]["email"] == "d@test.com"
    uid = r.get_json()["user"]["id"]
    client.patch(f"/api/admin/users/{uid}/active", headers=admin_headers, json={"is_active": False})
    assert client.post("/api/auth/google", json={"id_token": "d@test.com"}).status_code == 403


def test_google_takes_over_unverified_preregistration(client, google):
    # attacker pre-registers the victim's email with their own password
    client.post("/api/auth/register/donor", json={"email": "v@gmail.com", "password": "attackerpass1", **DONOR})
    r = client.post("/api/auth/google", json={"id_token": "v@gmail.com"})
    assert r.status_code == 200
    # the attacker's password no longer works
    login = client.post("/api/auth/login", json={"email": "v@gmail.com", "password": "attackerpass1"})
    assert login.status_code == 401
