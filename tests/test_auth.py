"""Anmeldung, Pflicht-Passwortwechsel, Einladungen, Rechte, Schutzmechanismen."""
from fastapi.testclient import TestClient

from conftest import ADMIN_PW, H


def test_unauthenticated_is_rejected(app):
    c = TestClient(app)
    assert c.get("/api/projects").status_code == 401
    assert c.get("/api/me").json()["user"] is None


def test_csrf_header_required(app, admin):
    r = admin.post("/api/projects", json={"name": "x"})  # ohne X-Requested-With
    assert r.status_code == 403
    r = admin.post("/api/projects", json={"name": "x"}, headers={**H, "Origin": "https://boese.example"})
    assert r.status_code == 403


def test_forced_password_change_blocks_everything(app):
    # Ein frisch zurueckgesetzter Admin-Zustand laesst sich nicht nachstellen – daher eigener Nutzer mit
    # must_change_pw ueber die Datenbank.
    from app import auth, db
    h = auth.hash_pw("Initial-Passwort-9")
    db.ex("INSERT INTO users(username,pw_hash,role,status,must_change_pw,initial_pw_hash,created_at) "
          "VALUES ('pflicht','%s','user','active',1,'%s',?)" % (h, h), (db.now(),))
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "pflicht", "password": "Initial-Passwort-9"}, headers=H)
    assert r.status_code == 200 and r.json()["user"]["must_change_pw"] == 1
    assert c.get("/api/projects").status_code == 403
    assert c.get("/api/me").status_code == 200
    r = c.post("/api/auth/change-password", json={"current": "Initial-Passwort-9", "new": "Initial-Passwort-9"}, headers=H)
    assert r.status_code == 400 and "Initialpasswort" in r.json()["detail"]
    r = c.post("/api/auth/change-password", json={"current": "Initial-Passwort-9", "new": "kurz"}, headers=H)
    assert r.status_code == 400
    r = c.post("/api/auth/change-password", json={"current": "Initial-Passwort-9", "new": "Fraeskopf-Stahl-2026"}, headers=H)
    assert r.status_code == 200
    assert c.get("/api/projects").status_code == 200


def test_admin_default_must_change(admin):
    me = admin.get("/api/me").json()["user"]
    assert me["username"] == "admin" and me["role"] == "admin" and me["must_change_pw"] == 0


def test_password_policy():
    from app import auth
    assert auth.check_policy("kurz")
    assert auth.check_policy("password1234")
    assert auth.check_policy("max.mustermann-2026", "max.mustermann")
    assert auth.check_policy("Fraeskopf-Stahl-2026", "bob") == []


def test_invite_single_use_and_email_binding(app, admin):
    r = admin.post("/api/admin/invites", json={"email": "gebunden@example.org", "role": "user", "days": 1}, headers=H)
    token = r.json()["link"].rsplit("/", 1)[1]
    info = TestClient(app).get(f"/api/invite/{token}").json()
    assert info["email"] == "gebunden@example.org" and info["invited_by"] == "admin"
    c = TestClient(app)
    r = c.post(f"/api/invite/{token}", json={"username": "gebunden", "email": "anders@example.org",
                                              "password": "Schieblehre-Messing-7"}, headers=H)
    assert r.status_code == 200 and r.json()["user"]["email"] == "gebunden@example.org"
    r = TestClient(app).post(f"/api/invite/{token}", json={"username": "zweiter", "password": "Schieblehre-Messing-7"}, headers=H)
    assert r.status_code == 404


def test_invite_revoked(app, admin):
    r = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H).json()
    admin.delete(f"/api/admin/invites/{r['id']}", headers=H)
    token = r["link"].rsplit("/", 1)[1]
    assert TestClient(app).get(f"/api/invite/{token}").status_code == 404


def test_registration_only_by_invite(app):
    r = TestClient(app).post("/api/invite/erfunden", json={"username": "x", "password": "Schieblehre-Messing-7"}, headers=H)
    assert r.status_code == 404


def test_user_cannot_use_admin_routes(user):
    for path in ("/api/admin/users", "/api/admin/invites", "/api/admin/audit", "/api/admin/status"):
        assert user.get(path).status_code == 403
    assert user.post("/api/admin/invites", json={}, headers=H).status_code == 403


def test_users_cannot_see_each_other(app, user, admin):
    other = user
    pid = other.post("/api/projects", json={"name": "privat"}, headers=H).json()["id"]
    r = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H)
    token = r.json()["link"].rsplit("/", 1)[1]
    intruder = TestClient(app)
    intruder.post(f"/api/invite/{token}", json={"username": "neugierig", "password": "Schieblehre-Messing-7"}, headers=H)
    assert intruder.get(f"/api/projects/{pid}").status_code == 404
    assert intruder.patch(f"/api/projects/{pid}", json={"name": "x"}, headers=H).status_code == 404
    assert intruder.get(f"/api/projects/{pid}/measurements.csv").status_code == 404
    assert admin.get(f"/api/projects/{pid}").status_code == 200  # Admin darf


def test_last_admin_protection(admin):
    me = admin.get("/api/me").json()["user"]
    assert admin.patch(f"/api/admin/users/{me['id']}", json={"role": "user"}, headers=H).status_code == 400
    assert admin.patch(f"/api/admin/users/{me['id']}", json={"status": "disabled"}, headers=H).status_code == 400
    assert admin.delete(f"/api/admin/users/{me['id']}", headers=H).status_code == 400


def test_reset_link(app, admin, user):
    uid = user.get("/api/me").json()["user"]["id"]
    link = admin.post(f"/api/admin/users/{uid}/reset", headers=H).json()["link"]
    token = link.rsplit("/", 1)[1]
    c = TestClient(app)
    assert c.get(f"/api/reset/{token}").json()["username"] == user.username
    assert c.post(f"/api/reset/{token}", json={"password": "Neues-Passwort-Lang-1"}, headers=H).status_code == 200
    assert user.get("/api/projects").status_code == 401  # alte Sitzung beendet
    assert c.post(f"/api/reset/{token}", json={"password": "Nochmal-Passwort-Lang-2"}, headers=H).status_code == 404


def test_disabled_user_logged_out(app, admin, user):
    uid = user.get("/api/me").json()["user"]["id"]
    admin.patch(f"/api/admin/users/{uid}", json={"status": "disabled"}, headers=H)
    assert user.get("/api/projects").status_code == 401
    r = TestClient(app).post("/api/auth/login", json={"username": user.username, "password": "Schieblehre-Messing-7"}, headers=H)
    assert r.status_code == 403


def test_login_lockout(app, admin):
    r = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H)
    token = r.json()["link"].rsplit("/", 1)[1]
    TestClient(app).post(f"/api/invite/{token}", json={"username": "sperrtest", "password": "Schieblehre-Messing-7"}, headers=H)
    c = TestClient(app)
    codes = [c.post("/api/auth/login", json={"username": "sperrtest", "password": "falsch"}, headers=H).status_code
             for _ in range(6)]
    assert codes[:4] == [401] * 4 and codes[-1] == 429
    # auch mit richtigem Passwort gesperrt
    assert c.post("/api/auth/login", json={"username": "sperrtest", "password": "Schieblehre-Messing-7"},
                  headers=H).status_code == 429


def test_email_validation(admin):
    assert admin.patch("/api/me", json={"email": "keine-mail"}, headers=H).status_code == 400
    assert admin.post("/api/admin/invites", json={"email": "x"}, headers=H).status_code == 400


def test_security_headers(app):
    r = TestClient(app).get("/api/me")
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"


def test_session_cookie_flags(app):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PW, "remember": True}, headers=H)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
