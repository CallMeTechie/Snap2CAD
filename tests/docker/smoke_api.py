"""End-to-End gegen den laufenden Docker-Stack (nur Standardbibliothek).
Aufruf: python tests/docker/smoke_api.py http://127.0.0.1:8000"""
import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1].rstrip("/")
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"X-Requested-With": "fetch", "Content-Type": "application/json"})
    with opener.open(req, timeout=60) as r:
        raw = r.read()
        return json.loads(raw) if r.headers.get("content-type", "").startswith("application/json") else raw


me = call("GET", "/api/me")
assert me["sandbox"], "Sandbox-Worker meldet keinen Herzschlag"
# Frische Installation: kein Konto, Einrichtungsassistent aktiv
assert me["setup"]["required"] and me["setup"]["allowed"], me.get("setup")
u = call("POST", "/api/setup", {"username": "ci-admin", "display_name": "CI", "password": "CI-Testpasswort-Lang-1",
                                "api_key": ""})["user"]
assert u["role"] == "admin" and not u["must_change_pw"], u
assert "setup" not in call("GET", "/api/me")
try:
    call("POST", "/api/setup", {"username": "zweiter", "password": "CI-Testpasswort-Lang-2"})
    raise AssertionError("zweite Einrichtung darf nicht moeglich sein")
except urllib.error.HTTPError as e:
    assert e.code == 409, e.code
assert call("GET", "/api/mat.pdf?format=A4")[:4] == b"%PDF"
html = opener.open(BASE + "/", timeout=30).read()
assert b"Snap2CAD" in html
pid = call("POST", "/api/projects", {"name": "CI"})["id"]
job = call("POST", "/api/jobs", {"project_id": pid, "name": "CI-Platte", "request": "Montageplatte"})
for _ in range(240):
    job = call("GET", f"/api/jobs/{job['id']}")
    if job["status"] not in ("queued", "running"):
        break
    time.sleep(1)
print("Auftrag:", job["status"], "Version", job["current_version"], "Maße", job["bbox"])
for line in job["log"]:
    print("  ", line["level"], line["msg"])
assert job["status"] == "done" and job["bbox"] == [80.0, 50.0, 6.0], job.get("error")
step = call("GET", f"/api/jobs/{job['id']}/v/{job['current_version']}/model.step")
assert b"ISO-10303" in step[:200]
print("Smoke-Test bestanden")
