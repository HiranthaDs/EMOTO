def test_initial_admin_login_logout(client):
    assert client.get("/api/v1/auth/setup-status").status_code == 404
    assert client.post("/api/v1/auth/bootstrap", json={}).status_code in {404, 405}
    assert client.post("/api/v1/auth/login", json={"email": "admin@gmail.com", "password": "wrong"}).status_code == 401
    login = client.post("/api/v1/auth/login", json={"email": "admin@gmail.com", "password": "admin@123"})
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "Super Admin"
    csrf = login.json()["csrf_token"]
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_csrf_is_required(admin):
    response = admin["client"].post("/api/v1/customers", json={"full_name": "Blocked", "phone": "1"})
    assert response.status_code == 403

