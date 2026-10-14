"""Verwaltung von der Kommandozeile im Container – fuer den Notfall, wenn niemand mehr Admin-Zugang hat.

    docker compose exec app python -m app.manage users
    docker compose exec app python -m app.manage reset-link <benutzername>
"""
from __future__ import annotations

import sys

from . import auth, db


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    if cmd == "users":
        rows = db.q("SELECT username, role, status, email, last_login FROM users ORDER BY username")
        if not rows:
            print("Noch keine Benutzer – Snap2CAD im Browser öffnen, um die Einrichtung abzuschließen.")
        for r in rows:
            print(f"{r['username']:<24} {r['role']:<6} {r['status']:<9} {r['email'] or '':<32} {r['last_login'] or '–'}")
        return 0
    if cmd == "reset-link" and len(argv) == 2:
        u = db.q1("SELECT * FROM users WHERE username=?", (argv[1],))
        if not u:
            print(f"Benutzer „{argv[1]}“ nicht gefunden.", file=sys.stderr)
            return 1
        if u["status"] != "active":
            db.ex("UPDATE users SET status='active' WHERE id=?", (u["id"],))
            print("Konto war gesperrt und wurde entsperrt.")
        token = auth.create_reset(None, u)
        url = auth.link("reset", token)
        print(f"Link zum Setzen eines neuen Passworts für „{u['username']}“ (48 Stunden gültig, einmalig):\n{url}")
        if url.startswith("/"):
            print("Die Adresse von Snap2CAD davorsetzen, z. B. http://nas.local:8000" + url)
        return 0
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
