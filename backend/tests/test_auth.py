def test_setup_login_logout(client):
    assert client.get("/api/v1/auth/setup-status").json() == {"needs_setup": True}
    setup = client.post("/api/v1/auth/bootstrap", json={"token": "test-bootstrap-token", "email": "owner@emoto.example.com", "full_name": "EMOTO Owner", "password": "CorrectHorse123!"})
    assert setup.status_code == 201
    csrf = setup.json()["csrf_token"]
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "owner@emoto.example.com", "password": "wrong"}).status_code == 401
    login = client.post("/api/v1/auth/login", json={"email": "owner@emoto.example.com", "password": "CorrectHorse123!"})
    assert login.status_code == 200


def test_csrf_is_required(admin):
    response = admin["client"].post("/api/v1/customers", json={"full_name": "Blocked", "phone": "1"})
    assert response.status_code == 403

