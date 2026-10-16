"""Projektbibliothek: Modellbild aus der STL, Vorschau-Route, Bibliotheksfelder der Projektliste."""
import struct
import time

import cv2
import numpy as np

from conftest import H

BG = (0xf7, 0xf5, 0xf3)  # #f3f5f7 als BGR


def _cube_tris(s=10.0):
    v = [(x, y, z) for x in (0, s) for y in (0, s) for z in (0, s)]
    idx = lambda x, y, z: x * 4 + y * 2 + z  # noqa: E731
    quads = [  # je Flaeche vier Ecken (x,y,z) in Umlaufrichtung, Normale nach aussen
        ((0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)),
        ((1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 1, 0)),
        ((0, 0, 0), (0, 0, 1), (1, 0, 1), (1, 0, 0)),
        ((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)),
        ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)),
        ((0, 0, 1), (0, 1, 1), (1, 1, 1), (1, 0, 1)),
    ]
    tris = []
    for a, b, c, d in quads:
        for t in ((a, b, c), (a, c, d)):
            tris.append([v[idx(*p)] for p in t])
    return tris


def _normal(t):
    n = np.cross(np.subtract(t[1], t[0]), np.subtract(t[2], t[0]))
    ln = np.linalg.norm(n)
    return n / ln if ln else n


def _write_bin(path, tris):
    b = bytearray(80) + struct.pack("<I", len(tris))
    for t in tris:
        b += struct.pack("<3f", *_normal(t)) + b"".join(struct.pack("<3f", *p) for p in t) + b"\0\0"
    path.write_bytes(bytes(b))


def _write_ascii(path, tris):
    out = ["solid cube"]
    for t in tris:
        out.append("facet normal %f %f %f\n outer loop" % tuple(_normal(t)))
        out += ["  vertex %f %f %f" % tuple(p) for p in t]
        out.append(" endloop\nendfacet")
    out.append("endsolid cube")
    path.write_text("\n".join(out))


def test_render_stl_png_wuerfel(tmp_path):
    from app import preview
    stl, png = tmp_path / "w.stl", tmp_path / "w.png"
    _write_bin(stl, _cube_tris())
    assert preview.render_stl_png(stl, png) is True
    img = cv2.imread(str(png))
    assert img is not None and img.shape[:2] == (360, 480)
    assert tuple(int(c) for c in img[2, 2]) == BG
    diff = np.abs(img.astype(int) - np.array(BG)).sum(axis=2) > 12
    assert diff.mean() >= 0.10
    # iso sieht drei Flaechen: drei deutlich verschiedene Helligkeiten
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)[diff]
    hist = np.bincount(grey // 8, minlength=32)
    big = [i for i in range(32) if hist[i] > 0.05 * grey.size]
    assert len(big) >= 3, hist
    assert max(big) - min(big) >= 2


def test_render_stl_ascii_und_kaputt(tmp_path):
    from app import preview
    a, png = tmp_path / "a.stl", tmp_path / "a.png"
    _write_ascii(a, _cube_tris())
    assert preview.render_stl_png(a, png) is True and cv2.imread(str(png)) is not None
    leer, muell = tmp_path / "leer.stl", tmp_path / "muell.stl"
    leer.write_bytes(b"")
    muell.write_bytes(b"\x00\x01garbage" * 50)
    for f in (leer, muell, tmp_path / "gibtsnicht.stl"):
        out = tmp_path / "x.png"
        assert preview.render_stl_png(f, out) is False
        assert not out.exists()


def test_render_stl_ausduennen(tmp_path, monkeypatch):
    from app import preview
    monkeypatch.setattr(preview, "MAX_TRIS", 8)
    stl, png = tmp_path / "w.stl", tmp_path / "w.png"
    _write_bin(stl, _cube_tris())
    assert preview.render_stl_png(stl, png) is True


# ------------------------------------------------------------------ Hilfen

def _uid(c):
    from app import db
    return db.q1("SELECT id FROM users WHERE username=?", (c.username,))["id"]


def _proj(c, name="Bib"):
    return c.post("/api/projects", json={"name": name}, headers=H).json()["id"]


def _photo(pid, view="top", thumb=True):
    from app import config, db
    phid = db.ex("INSERT INTO photos(project_id,filename,view,status,created_at) VALUES (?,?,?,?,?)",
                 (pid, "f.jpg", view, "gut", db.now()))
    if thumb:
        d = config.DATA_DIR / "photos" / str(phid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "thumb.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    return phid


def _job(c, pid, status="done", ver_status="ok", stl=True, updated=None, name="Teil"):
    from app import config, db
    ts = updated or db.now()
    jid = db.ex("INSERT INTO jobs(user_id,project_id,name,request,status,messages,current_version,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)", (_uid(c), pid, name, "{}", status, "[]",
                                              1 if ver_status else None, ts, ts))
    if ver_status:
        db.ex("INSERT INTO job_versions(job_id,version,trigger,request_text,code,claude_text,meta,status,result,checks,"
              "usage,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
              (jid, 1, "create", "", "X=1\n", "", "{}", ver_status, "{}", "[]", "{}", ts))
        d = config.DATA_DIR / "jobs" / str(jid) / "v1"
        d.mkdir(parents=True, exist_ok=True)
        if stl:
            _write_bin(d / "model.stl", _cube_tris())
    return jid


# ------------------------------------------------------------------ Route

def test_preview_route(user, monkeypatch):
    from app import config, main, preview
    pid = _proj(user)
    jid = _job(user, pid)
    calls = []
    real = preview.render_stl_png

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)
    monkeypatch.setattr(preview, "render_stl_png", counting)
    url = f"/api/jobs/{jid}/v/1/preview.png"
    r = user.get(url)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "private, max-age=86400"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    f = config.DATA_DIR / "jobs" / str(jid) / "v1" / "preview.png"
    assert f.is_file()
    r2 = user.get(url)
    assert r2.status_code == 200 and r2.content == r.content == f.read_bytes()
    assert len(calls) == 1
    assert not list(f.parent.glob("*.tmp"))
    # bestehender Pfad fuer model.stl
    assert user.get(f"/api/jobs/{jid}/v/1/model.stl").status_code == 200
    assert main.FILE_TYPES["model.stl"] == "model/stl"


def test_preview_route_fremd_und_fehler(user, app):
    from fastapi.testclient import TestClient
    pid = _proj(user)
    jid = _job(user, pid)
    from app import config
    # zweiter Nutzer: per Admin-Einladung
    adm = TestClient(app)
    adm.__enter__()
    try:
        from conftest import ADMIN_PW
        adm.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PW}, headers=H)
        tok = adm.post("/api/admin/invites", json={"role": "user", "days": 1}, headers=H).json()["link"].rsplit("/", 1)[1]
        fremd = TestClient(app)
        r = fremd.post(f"/api/invite/{tok}", json={"username": "fremdling", "display_name": "F",
                                                    "password": "Schieblehre-Messing-7"}, headers=H)
        assert r.status_code == 200, r.text
        assert fremd.get(f"/api/jobs/{jid}/v/1/preview.png").status_code == 404
    finally:
        adm.__exit__(None, None, None)
    assert user.get(f"/api/jobs/{jid}/v/2/preview.png").status_code == 404           # Version fehlt
    j_ohne = _job(user, pid, stl=False)
    r = user.get(f"/api/jobs/{j_ohne}/v/1/preview.png")
    assert r.status_code == 404 and "Kein Modellbild" in r.text
    j_fail = _job(user, pid, status="failed", ver_status="failed")
    assert user.get(f"/api/jobs/{j_fail}/v/1/preview.png").status_code == 404
    # kaputte STL -> 404, nicht 500
    j_kaputt = _job(user, pid, stl=False)
    (config.DATA_DIR / "jobs" / str(j_kaputt) / "v1" / "model.stl").write_bytes(b"muell")
    assert user.get(f"/api/jobs/{j_kaputt}/v/1/preview.png").status_code == 404


# ------------------------------------------------------------------ Projektliste

def _entry(c, pid):
    return next(p for p in c.get("/api/projects").json() if p["id"] == pid)


def test_projects_bibliothek_felder(user):
    from app import db
    pid = _proj(user)
    e = _entry(user, pid)
    assert e["thumb"] is None and e["last_job"] is None and e["updated_at"] == e["created_at"]

    ph_front = _photo(pid, "front")
    ph_top = _photo(pid, "top")
    e = _entry(user, pid)
    assert e["thumb"] == {"kind": "photo", "url": f"/api/photos/{ph_top}/thumb.jpg"}
    assert e["updated_at"] >= e["created_at"]
    assert ph_front < ph_top

    ohne_thumb = _proj(user, "ohne")
    _photo(ohne_thumb, "top", thumb=False)
    assert _entry(user, ohne_thumb)["thumb"] is None

    t1 = "2026-10-01T10:00:00+00:00"
    jid = _job(user, pid, updated=t1)
    e = _entry(user, pid)
    assert e["thumb"] == {"kind": "model", "url": f"/api/jobs/{jid}/v/1/preview.png"}
    assert e["last_job"] == {"id": jid, "name": "Teil", "status": "done", "current_version": 1, "updated_at": t1}
    assert e["updated_at"] >= t1

    t2 = "2099-01-01T00:00:00+00:00"
    j2 = _job(user, pid, status="failed", ver_status=None, updated=t2)
    e = _entry(user, pid)
    assert e["last_job"]["id"] == j2 and e["last_job"]["status"] == "failed" and e["last_job"]["current_version"] is None
    assert e["thumb"]["url"] == f"/api/jobs/{jid}/v/1/preview.png"
    assert e["updated_at"] == t2

    # Detailantwort unveraendert
    d = user.get(f"/api/projects/{pid}").json()
    assert "thumb" not in d and "last_job" not in d
    assert db.q1("SELECT id FROM projects WHERE id=?", (pid,))


def test_projects_fremde_nicht_in_liste(user):
    from app import db
    pid = _proj(user, "meins")
    admin_id = db.q1("SELECT id FROM users WHERE username='admin'")["id"]
    fremd = db.ex("INSERT INTO projects(user_id,name,created_at) VALUES (?,?,?)", (admin_id, "fremd", db.now()))
    _photo(fremd)
    ids = [p["id"] for p in user.get("/api/projects").json()]
    assert ids == [pid] and fremd not in ids


def test_projects_liste_schnell(user):
    pids = [_proj(user, f"P{i}") for i in range(30)]
    for p in pids:
        _photo(p)
        _job(user, p)
    t = time.time()
    r = user.get("/api/projects")
    assert r.status_code == 200 and len(r.json()) == 30
    assert time.time() - t < 2
