def test_donor_cannot_use_hospital_or_admin_routes(client, make_donor):
    h = make_donor()
    assert client.get("/api/requests", headers=h).status_code == 403
    assert client.post("/api/requests", headers=h, json={}).status_code == 403
    assert client.get("/api/hospitals/analytics", headers=h).status_code == 403
    assert client.get("/api/admin/stats", headers=h).status_code == 403


def test_hospital_cannot_use_donor_or_admin_routes(client, make_hospital):
    h = make_hospital()
    assert client.get("/api/donors/me", headers=h).status_code == 403
    assert client.get("/api/donors/requests", headers=h).status_code == 403
    assert client.get("/api/admin/donors", headers=h).status_code == 403


def test_admin_endpoints(client, make_donor, make_hospital, admin_headers):
    make_donor("d1@test.com", blood_type="O+")
    make_donor("d2@test.com", blood_type="A+", region="Ashanti")
    make_hospital()
    assert len(client.get("/api/admin/donors", headers=admin_headers).get_json()) == 2
    assert len(client.get("/api/admin/donors?blood_type=A%2B", headers=admin_headers).get_json()) == 1
    assert len(client.get("/api/admin/donors?region=ashanti", headers=admin_headers).get_json()) == 1
    hospitals = client.get("/api/admin/hospitals", headers=admin_headers).get_json()
    assert hospitals[0]["is_verified"] is False
    r = client.patch(f"/api/admin/hospitals/{hospitals[0]['id']}/verify", headers=admin_headers)
    assert r.get_json()["is_verified"] is True
    stats = client.get("/api/admin/stats", headers=admin_headers).get_json()
    assert stats["total_donors"] == 2 and stats["total_hospitals"] == 1
    assert stats["donors_by_blood_type"]["O+"] == 1
    assert client.get("/api/admin/requests?status=open", headers=admin_headers).status_code == 200
    assert client.get("/api/admin/requests?status=bogus", headers=admin_headers).status_code == 400


def test_admin_deactivate_user(client, make_donor, admin_headers):
    make_donor("d@test.com")
    users = client.get("/api/admin/donors", headers=admin_headers).get_json()
    uid = users[0]["user_id"]
    r = client.patch(f"/api/admin/users/{uid}/active", headers=admin_headers, json={"is_active": False})
    assert r.status_code == 200 and r.get_json()["is_active"] is False
    r = client.post("/api/auth/login", json={"email": "d@test.com", "password": "password123"})
    assert r.status_code == 403


def test_hospital_can_not_self_verify(client, make_hospital):
    h = make_hospital()
    r = client.put("/api/hospitals/me", headers=h, json={"is_verified": True, "name": "New"})
    assert r.get_json()["is_verified"] is False and r.get_json()["name"] == "New"
