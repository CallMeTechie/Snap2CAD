"""Ablauf Projekt -> Foto -> Masse -> Claude-Vorschlaege -> CAD-Auftrag (KI im Testmodus, Sandbox lokal)."""
import io
import time
import zipfile

import pytest

from conftest import H


def wait_job(client, jid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.5)
    raise AssertionError(f"Auftrag {jid} nicht fertig: {j['status']}")


@pytest.fixture()
def project(user, photo_a4):
    pid = user.post("/api/projects", json={"name": "Halteplatte Ä"}, headers=H).json()["id"]
    r = user.post(f"/api/projects/{pid}/photos", files={"file": ("foto.jpg", photo_a4, "image/jpeg")},
                  data={"view": "top"}, headers=H)
    assert r.status_code == 200, r.text
    return {"client": user, "id": pid, "photo": r.json()}


def test_mat_pdf_and_preview(admin):
    r = admin.get("/api/mat.pdf?format=A3&pages=mat,guide&header=Test")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    r = admin.get("/api/mat/preview.png?format=A4&page=1")
    assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert admin.get("/api/mat.pdf?format=A5").status_code == 400
    assert admin.get("/api/prompt.md").status_code == 404


def test_photo_analysis(project):
    ph = project["photo"]
    assert ph["status"] == "gut" and ph["format"] == "A4"
    assert set(ph["files"]) >= {"orig", "overlay", "rect", "thumb"}
    assert ph["rect"]["w_mm"] == 190
    c = project["client"]
    r = c.get(f"/api/photos/{ph['id']}/rect.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert c.get(f"/api/photos/{ph['id']}/../../etc.jpg").status_code == 404


def test_photo_rejects_garbage(user):
    pid = user.post("/api/projects", json={"name": "x"}, headers=H).json()["id"]
    r = user.post(f"/api/projects/{pid}/photos", files={"file": ("x.jpg", b"kein bild", "image/jpeg")}, headers=H)
    assert r.status_code == 400


def test_upload_size_limit(user):
    pid = user.post("/api/projects", json={"name": "gross"}, headers=H).json()["id"]
    big = b"x" * (10 * 1024 * 1024)
    r = user.post(f"/api/projects/{pid}/photos", files={"file": ("x.jpg", big, "image/jpeg")}, headers=H)
    assert r.status_code == 413


def test_measurements_and_factors(project):
    c, pid, ph = project["client"], project["id"], project["photo"]
    m = c.post(f"/api/projects/{pid}/measurements", json={"photo_id": ph["id"], "kind": "length",
                                                          "points": [[10, 10], [110, 10]]}, headers=H).json()
    assert m["value"] == pytest.approx(100) and m["id_label"] == "M1" and m["unc"] > 0
    d = c.post(f"/api/projects/{pid}/measurements", json={"photo_id": ph["id"], "kind": "diameter", "critical": True,
                                                          "points": [[60, 50], [50, 60], [40, 50]]}, headers=H).json()
    assert d["value"] == pytest.approx(20)
    r = c.patch(f"/api/measurements/{d['id']}", json={"kind": "radius"}, headers=H).json()
    assert r["value"] == pytest.approx(10)
    p = c.patch(f"/api/projects/{pid}", json={"ctrl_x": 99.5}, headers=H).json()
    vals = {x["id"]: x["value"] for x in p["measurements"]}
    assert vals[m["id"]] == pytest.approx(99.5)
    assert c.patch(f"/api/projects/{pid}", json={"ctrl_x": 50}, headers=H).status_code == 400
    assert c.post(f"/api/projects/{pid}/measurements", json={"kind": "length", "points": [[1], [2, 3]]},
                  headers=H).status_code == 400
    man = c.post(f"/api/projects/{pid}/measurements", json={"kind": "length", "value": 6.1, "label": "=SUMME(A1)"},
                 headers=H).json()
    assert man["source"] == "manual"
    csv = c.get(f"/api/projects/{pid}/measurements.csv")
    assert csv.status_code == 200 and "filename*=UTF-8''" in csv.headers["content-disposition"]
    assert "'=SUMME" in csv.text  # Formel-Injektion entschaerft




def test_statische_dateien_immer_nachfragen(admin):
    """Nach einem Update keine Mischung aus alten und neuen JS-Modulen: der Browser fragt jedes Mal per ETag nach."""
    r = admin.get("/static/js/app.js")
    assert r.status_code == 200 and r.headers.get("cache-control") == "no-cache"
    assert admin.get("/static/js/app.js", headers={"If-None-Match": r.headers["etag"]}).status_code == 304

def test_csv_quelle_im_klartext(project):
    """Quelle in CSV und KI-Masstabelle als Klartext statt der internen Werte user/manual."""
    from app import jobs
    c, pid, ph = project["client"], project["id"], project["photo"]
    c.post(f"/api/projects/{pid}/measurements", json={"photo_id": ph["id"], "kind": "length",
                                                      "points": [[10, 10], [110, 10]]}, headers=H)
    c.post(f"/api/projects/{pid}/measurements", json={"kind": "length", "value": 6.1, "label": "Dicke"}, headers=H)
    rows = [r.split(";") for r in c.get(f"/api/projects/{pid}/measurements.csv").text.lstrip("\ufeff").splitlines()]
    col = rows[0].index("Quelle")
    assert [r[col] for r in rows[1:]] == ["Foto", "manuell"]
    table, _ = jobs.measurement_table(pid)
    assert "| Foto |" in table and "| manuell |" in table

def test_claude_suggestions(project):
    c, pid = project["client"], project["id"]
    r = c.post(f"/api/projects/{pid}/suggest", json={}, headers=H)
    assert r.status_code == 200, r.text
    sugg = r.json()["suggestions"]
    assert len(sugg) == 3 and all(s["source"] == "claude" and not s["accepted"] for s in sugg)
    c.patch(f"/api/measurements/{sugg[0]['id']}", json={"accepted": True}, headers=H)
    c.post(f"/api/projects/{pid}/measurements/discard-suggestions", headers=H)
    ms = c.get(f"/api/projects/{pid}").json()["measurements"]
    assert [m["source"] for m in ms] == ["claude"] and ms[0]["accepted"]



def test_parse_suggestions_nur_text_uebernehmen():
    from app import ai
    items = ai.parse_suggestions('[{"label": ["Dicke"], "value": 6, "reason": {"x": 1}}, {"label": " Breite ", "value": 4}]')
    assert [(m["label"], m["reason"]) for m in items] == [("Maß", ""), ("Breite", "")]

def test_cad_job_autofix_iterate_quota(project):
    c, pid = project["client"], project["id"]
    c.post(f"/api/projects/{pid}/measurements", json={"kind": "length", "value": 80, "label": "Länge"}, headers=H)
    r = c.post("/api/jobs", json={"project_id": pid, "name": "Platte Ö", "request": "Montageplatte", "process": "fdm"},
               headers=H)
    assert r.status_code == 200, r.text
    j = wait_job(c, r.json()["id"])
    assert j["status"] == "done", j
    v1, v2 = j["versions"]
    assert v1["status"] == "failed" and v1["error"]["line"] == 15  # absichtlich fehlerhafter Testcode
    assert v2["trigger"] == "autofix" and v2["status"] == "ok"
    assert {c_["id"]: c_["state"] for c_ in v2["checks"]}["watertight"] == "ok"
    assert v2["result"]["bbox"] == [80.0, 50.0, 6.0]
    base = f"/api/jobs/{j['id']}/v/2"
    step = c.get(f"{base}/model.step?download=1")
    assert step.status_code == 200 and b"ISO-10303" in step.content[:200]
    assert c.get(f"{base}/model.stl").status_code == 200
    z = zipfile.ZipFile(io.BytesIO(c.get(f"{base}/bundle.zip").content))
    names = z.namelist()
    assert any(n.endswith(".step") for n in names) and "LIESMICH.txt" in names
    assert c.get(f"{base}/../../../etc/passwd").status_code == 404
    # Aenderungswunsch -> v3
    r = c.post(f"/api/jobs/{j['id']}/iterate", json={"text": "Dicke 8 mm"}, headers=H)
    assert r.status_code == 200
    assert c.post(f"/api/jobs/{j['id']}/iterate", json={"text": "nochmal"}, headers=H).status_code == 409
    j = wait_job(c, j["id"])
    assert j["status"] == "done" and j["current_version"] == 3 and j["bbox"] == [80.0, 50.0, 8.0]
    # Kontingent: DEFAULT_QUOTA=3 -> create + iterate = 2, ein weiterer erlaubt, dann Schluss
    r = c.post("/api/jobs", json={"project_id": pid, "name": "drei", "request": "x"}, headers=H)
    assert r.status_code == 200
    wait_job(c, r.json()["id"])
    r = c.post("/api/jobs", json={"project_id": pid, "name": "vier", "request": "x"}, headers=H)
    assert r.status_code == 429


def test_job_isolation(project, app, admin):
    from fastapi.testclient import TestClient
    c, pid = project["client"], project["id"]
    jid = c.post("/api/jobs", json={"project_id": pid, "name": "geheim", "request": "x"}, headers=H).json()["id"]
    wait_job(c, jid)
    r = admin.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H)
    other = TestClient(app)
    other.post(f"/api/invite/{r.json()['link'].rsplit('/', 1)[1]}",
               json={"username": "fremder", "password": "Schieblehre-Messing-7"}, headers=H)
    assert other.get(f"/api/jobs/{jid}").status_code == 404
    assert other.get(f"/api/jobs/{jid}/v/2/model.step").status_code == 404
    assert other.post(f"/api/jobs/{jid}/cancel", headers=H).status_code == 404
    assert jid not in [x["id"] for x in other.get("/api/jobs").json()]


def test_cancel_job(project):
    c, pid = project["client"], project["id"]
    jid = c.post("/api/jobs", json={"project_id": pid, "name": "abbruch", "request": "x"}, headers=H).json()["id"]
    c.post(f"/api/jobs/{jid}/cancel", headers=H)
    j = wait_job(c, jid)
    assert j["status"] == "cancelled"


def test_spa_fallback(app):
    from fastapi.testclient import TestClient
    c = TestClient(app)
    r = c.get("/einladung/irgendwas")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert c.get("/api/gibtsnicht").status_code == 404
