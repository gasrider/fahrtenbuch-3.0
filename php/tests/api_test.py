#!/usr/bin/env python3
"""End-to-End-Test: frische Installation per installieren.php + alle wichtigen API-Aktionen.
Braucht: php (CLI), laufende MariaDB/MySQL mit root ohne Passwort, Python 3 (openpyxl optional).
Aufruf:  python3 tests/api_test.py
Prüft vor allem die Fachregeln: Kilometerkette lückenlos ab Anker (auch über die Jahresgrenze),
Distanz-Matrix wird genutzt, HU v5 (Tacho bei Ankunft Werkstatt = HU-Stand, nur einmal),
Privat-KM-Summe exakt, Taggeld nur bei km_d > 0, PDFs, Excel-Import, Supabase-Umzug.
"""
import http.server, json, os, pathlib, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8792
DB = "fb_test"
FAILS = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def sh(cmd):
    return subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True).stdout


# ---------- Supabase-Attrappe (PostgREST-ähnlich) ----------
SUPA = {
    "users": [{"username": "christian mayerhofer", "password": "x" * 64, "email": "admin@example.com", "force_pw_change": False},
              {"username": "neuhofer dominik", "password": __import__("hashlib").sha256(b"altpass").hexdigest(), "email": "d@example.com", "force_pw_change": False}],
    "settings": [{"username": "neuhofer dominik", "name": "Dominik N.", "pnr": "42", "wohnort": "Oberhofen am Irrsee", "dienstort": "Straßwalchen", "entfernung": 18,
                  "taggeld_min_stunden": 5, "taggeld_basis": 10, "taggeld_stufung": 2.5, "taggeld_max_betrag": 30, "taggeld_max_stunden": 13, "km_geld": 0.42}],
    "system_config": [{"id": 1, "smtp_server": "smtp.example.com", "smtp_port": "465", "smtp_user": "fb@example.com", "smtp_password": "geheim", "smtp_from_name": "Fahrtenbuch"}],
    "fahrzeuge": [{"id": 70, "username": "neuhofer dominik", "bezeichnung": "VW Polo", "kennzeichen": "VB-1", "start_km_vorjahr": 206371, "privat_km_min": 5, "privat_km_max": 20, "dienstlich_quote": 90}],
    "zeitraeume": [{"username": "neuhofer dominik", "fahrzeug_id": 70, "von": "2025-01-01", "bis": "2025-12-31"}],
    "orte": [{"username": "neuhofer dominik", "ort": "Eugendorf"}],
    "orte_distanz": [{"username": "neuhofer dominik", "ort": "Eugendorf", "km_einfach": 30}],
    "ort_koordinaten": [],
    "distanz_matrix": [{"username": "neuhofer dominik", "ort_a": "Eugendorf", "ort_b": "Zell am Moos", "key_a": "eugendorf", "key_b": "zell am moos", "km": 25, "quelle": "osrm"}],
    "jahres_start_km": [{"username": "neuhofer dominik", "jahr": 2025, "fahrzeug_id": 70, "start_km": 206371}],
    "generation_settings": [{"username": "neuhofer dominik", "jahr": 2025, "settings_json": "{\"modus\": \"Ganzes Jahr\"}"}],
    "hu_corrections": [{"username": "neuhofer dominik", "fahrzeug_id": 70, "datum": "2025-06-10", "km_at_hu": 215000, "werkstattort": "Eugendorf", "stopps_vor_hu": "", "stopps_nach_hu": ""}],
    "fahrten": [{"username": "neuhofer dominik", "jahr": 2025, "monat": 1, "datum": "2025-01-%02d" % d, "fahrzeug_id": 70, "fahrzeug": "VW Polo", "route": "Test",
                 "km_d": 10, "km_p": 0, "abf": "08:00", "ank": "17:00", "dauer": "09:00", "abfahrt_km": 206371 + 10 * (d - 1)} for d in range(1, 31)] * 40,
}


class Supa(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        t = u.path.rsplit("/", 1)[-1]
        q = urllib.parse.parse_qs(u.query)
        if self.headers.get("apikey") != "service-role-test-key-123456":
            self.send_response(401); self.end_headers(); return
        if t not in SUPA:
            self.send_response(404); self.end_headers(); self.wfile.write(b'{"message":"relation does not exist"}'); return
        if q.get("order", [""])[0].startswith("id.") and t not in ("fahrzeuge", "system_config"):
            self.send_response(400); self.end_headers(); self.wfile.write(b'{"message":"column x.id does not exist"}'); return
        off = int(q.get("offset", ["0"])[0]); lim = int(q.get("limit", ["1000"])[0])
        body = json.dumps(SUPA[t][off:off + lim]).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)


def main():
    sh(f"mysql -uroot -e \"DROP DATABASE IF EXISTS {DB}; CREATE DATABASE {DB} CHARACTER SET utf8mb4; "
       f"CREATE USER IF NOT EXISTS 'fbtest'@'localhost' IDENTIFIED BY 'fbtest'; GRANT ALL ON {DB}.* TO 'fbtest'@'localhost';\"")
    sh(f"python3 {ROOT}/build/make_installer.py")
    work = pathlib.Path(tempfile.mkdtemp())
    app = work / "fahrtenbuch"; app.mkdir()
    shutil.copy(ROOT / "dist" / "installieren.php", app / "installieren.php")
    srv = subprocess.Popen(["php", "-S", f"127.0.0.1:{PORT}", "-t", str(work)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    supa = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Supa)
    threading.Thread(target=supa.serve_forever, daemon=True).start()
    time.sleep(1)
    base = f"http://127.0.0.1:{PORT}/fahrtenbuch/"
    try:
        run(base, app, supa.server_address[1])
    finally:
        srv.terminate(); supa.shutdown()
        shutil.rmtree(work, ignore_errors=True)
    print("\n" + ("ALLES GRÜN" if not FAILS else f"{len(FAILS)} FEHLER"))
    sys.exit(1 if FAILS else 0)


TOKEN = {"t": ""}


def api(base, action, data=None, expect=200, raw=False):
    req = urllib.request.Request(base + "api.php?action=" + action, data=json.dumps(data or {}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Auth-Token": TOKEN["t"]})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            code, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, body = e.code, e.read()
    if code != expect:
        print("    ->", action, code, body[:400])
    check(code == expect, f"{action} -> HTTP {code} (erwartet {expect})")
    return body if raw else (json.loads(body) if body[:1] in (b"{", b"[") else {})


def upload(base, typ, path):
    boundary = "----fbtest"
    content = path.read_bytes()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(base + "api.php?action=import&typ=" + typ, data=body, method="POST",
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary, "X-Auth-Token": TOKEN["t"]})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print("    ->", e.code, e.read()[:300]); FAILS.append("upload " + typ); return {}


def kette_ok(monate, anchor, label):
    """Kilometerkette: pro Fahrzeug lückenlos ab Anker. Liefert Endstände."""
    km = dict(anchor)
    ok = True
    for m in sorted(monate, key=int):
        for r in monate[m]:
            f = r["fahrzeug_id"]
            if f is None:
                continue
            f = str(f)
            if r["abfahrt_km"] != km.get(f, 0):
                ok = False
            km[f] = km.get(f, 0) + r["km_d"] + r["km_p"]
    check(ok, f"Kilometerkette lückenlos ab Anker ({label})")
    return km


def run(base, app, supa_port):
    print("Installation")
    form = urllib.parse.urlencode({"db_host": "localhost", "db_name": DB, "db_user": "fbtest", "db_pass": "fbtest", "admin_name": "Christian Mayerhofer",
                                   "admin_email": "admin@example.com", "admin_pw": "geheim123", "invite_code": "EINLADUNG"}).encode()
    html = urllib.request.urlopen(base + "installieren.php", data=form).read().decode()
    check("Fertig! Das Fahrtenbuch ist installiert." in html, "Installer meldet Erfolg")
    check(not (app / "installieren.php").exists(), "Installer hat sich selbst gelöscht")
    cfg = (app / "server" / "config.php").read_text()
    (app / "server" / "config.php").write_text(cfg.replace("return array (", "return array (\n  'test_any_supabase_url' => true,"))
    check(urllib.request.urlopen(base).status == 200, "Startseite erreichbar")

    print("Anmeldung")
    api(base, "login", {"username": "christian mayerhofer", "password": "falsch"}, 401)
    r = api(base, "login", {"username": "  Christian Mayerhofer ", "password": "geheim123"})
    TOKEN["t"] = r.get("token", "")
    check(r.get("user", {}).get("is_admin") is True, "Admin-Recht gesetzt")
    api(base, "register", {"username": "x", "email": "x@example.com", "password": "abcdef", "invite": "falsch"}, 400)
    api(base, "register", {"username": "Tester", "email": "t@example.com", "password": "abcdef", "invite": "EINLADUNG"})

    print("Stammdaten, Fahrzeuge, Orte")
    api(base, "settings_save", {"settings": {"name": "Christian M.", "pnr": "123", "wohnort": "Oberhofen am Irrsee", "dienstort": "Straßwalchen", "entfernung": 18, "km_geld": 0.42}})
    fz = api(base, "fahrzeuge_save", {"fahrzeuge": [
        {"bezeichnung": "Audi E-Tron", "kennzeichen": "VB-69", "start_km_vorjahr": 24659, "privat_km_min": 5, "privat_km_max": 20, "dienstlich_quote": 90},
        {"bezeichnung": "VW Polo", "kennzeichen": "VB-70", "start_km_vorjahr": 206371, "privat_km_min": 5, "privat_km_max": 20, "dienstlich_quote": 90},
        {"bezeichnung": "VW T6.1", "kennzeichen": "VB-71", "start_km_vorjahr": 78607, "privat_km_min": 5, "privat_km_max": 5, "dienstlich_quote": 80}],
        "zeitraeume": []})["fahrzeuge"]
    ids = {f["bezeichnung"]: f["id"] for f in fz}
    z = [{"fahrzeug_id": i, "von": "2025-01-01", "bis": "2026-12-31"} for i in ids.values()]
    r = api(base, "fahrzeuge_save", {"fahrzeuge": fz, "zeitraeume": z})
    check([f["id"] for f in r["fahrzeuge"]] == [f["id"] for f in fz], "Fahrzeug-IDs bleiben beim Speichern stabil")
    check(len(r["zeitraeume"]) == 3, "3 Zeiträume gespeichert")
    orte = ["Zell am Moos", "Eugendorf", "Mondsee", "Straßwalchen", "Oberhofen am Irrsee", "Henndorf"]
    api(base, "orte_save", {"orte": [{"ort": o, "km_einfach": None} for o in orte]})
    pairs = [("Oberhofen am Irrsee", "Zell am Moos", 5), ("Oberhofen am Irrsee", "Eugendorf", 28), ("Zell am Moos", "Eugendorf", 25),
             ("Oberhofen am Irrsee", "Mondsee", 12), ("Mondsee", "Eugendorf", 20), ("Zell am Moos", "Mondsee", 9), ("Oberhofen am Irrsee", "Straßwalchen", 18),
             ("Straßwalchen", "Eugendorf", 17), ("Straßwalchen", "Zell am Moos", 14), ("Straßwalchen", "Mondsee", 25), ("Oberhofen am Irrsee", "Henndorf", 22),
             ("Henndorf", "Eugendorf", 8), ("Henndorf", "Zell am Moos", 20), ("Henndorf", "Mondsee", 22), ("Henndorf", "Straßwalchen", 10)]
    m = api(base, "matrix_save", {"rows": [{"ort_a": a, "ort_b": b, "km": k} for a, b, k in pairs]})["matrix"]
    check(len(m) == len(pairs) and all(x["quelle"] == "manuell" for x in m), "Distanz-Matrix gespeichert (manuell)")
    r = api(base, "geo_finish")
    check({o["ort"]: o["km_einfach"] for o in r["orte"]}.get("Eugendorf") == 28, "km einfach aus Matrix übernommen")

    print("Generator")
    kw = "Zell am Moos:KB\nEugendorf:Angebot\nMondsee:KFZ\nHenndorf:KB"
    gen = {"modus": "Ganzes Jahr", "keyword_text": kw, "target_km_min": 1650, "target_km_max": 2000, "prob_werktag": 75, "hauptfahrzeug_name": "VW Polo",
           "hauptfahrzeug_anteil": 70, "anzahl_wochen": 2, "verteilung": "2x2 Wochen", "start_woche_1": "2025-04-07", "urlaub_fahrzeug_name": "VW Polo"}
    y = api(base, "generate", {"jahr": 2025, "gen": gen})
    check(sorted(y["monate"], key=int) == [str(i) for i in range(1, 13)], "12 Monate generiert")
    check(sum(len(v) for v in y["monate"].values()) == 365, "365 Tage 2025")
    check(not y["fehlende"], "keine fehlenden Distanzen")
    anchor25 = {str(k): v for k, v in y["anker"].items()}
    check(anchor25 == {str(ids["Audi E-Tron"]): 24659, str(ids["VW Polo"]): 206371, str(ids["VW T6.1"]): 78607}, "Anker 2025 = Start-KM Vorjahr")
    end25 = kette_ok(y["monate"], anchor25, "2025")
    sums = [sum(r["km_d"] for r in y["monate"][str(i)]) for i in range(1, 13)]
    check(all(400 < s < 3000 for s in sums), f"Dienst-km je Monat plausibel {sums}")
    zm = [r for v in y["monate"].values() for r in v if r["route"].startswith("Oberhofen am Irrsee - Zell am Moos (KB) - Oberhofen am Irrsee")]
    check(all(r["km_d"] in range(8, 15) for r in zm) if zm else True, "Matrix genutzt: Oberhofen–Zell–Oberhofen = 10 km (skaliert 8–13)")
    check(all(r["route"] != "Keine Fahrt" or r["km_d"] + r["km_p"] == 0 for v in y["monate"].values() for r in v), "Keine-Fahrt-Tage ohne km")

    y26 = api(base, "generate", {"jahr": 2026, "gen": dict(gen, start_woche_1="2026-04-06")})
    a26 = {str(k): v for k, v in y26["anker"].items()}
    check(a26 == {k: v for k, v in end25.items()}, "Anker 2026 = Endstand 2025 (Kette über Jahresgrenze)")
    kette_ok(y26["monate"], a26, "2026")

    print("Monat bearbeiten -> Kette neu (auch Folgejahr)")
    jan = y["monate"]["1"]
    jan[3]["km_d"] += 111
    y = api(base, "month_save", {"jahr": 2025, "monat": 1, "rows": jan})
    end25b = kette_ok(y["monate"], anchor25, "2025 nach Änderung")
    y26 = api(base, "year_get", {"jahr": 2026})
    a26 = {str(k): v for k, v in y26["anker"].items()}
    check(a26 == end25b, "Folgejahres-Anker nachgezogen")
    kette_ok(y26["monate"], a26, "2026 nach Änderung 2025")

    print("Privat-KM verteilen")
    polo = ids["VW Polo"]
    hu_day = "2025-06-10"
    r = api(base, "privat", {"jahr": 2025, "fahrzeug_id": polo, "total_km": 6000, "anzahl_gross": 4, "gross_min": 300, "gross_max": 800, "normal_min": 5, "normal_max": 45})
    s = sum(x["km_p"] for v in r["monate"].values() for x in v if x["fahrzeug_id"] == polo)
    check(s == 6000, f"Privat-KM Summe exakt 6000 ({s})")
    kette_ok(r["monate"], anchor25, "2025 nach Privat-KM")

    print("HU-Korrektur v5")
    api(base, "hu_save", {"rows": [{"fahrzeug_id": polo, "datum": hu_day, "km_at_hu": 214000, "werkstattort": "Eugendorf", "stopps_vor_hu": "Zell am Moos", "stopps_nach_hu": ""}]})
    r = api(base, "hu_apply", {})
    print("    " + "\n    ".join(r.get("meldungen", [])))
    y = api(base, "year_get", {"jahr": 2025})
    kette_ok(y["monate"], anchor25, "2025 nach HU")
    hu = [x for x in y["monate"]["6"] if x["datum"] == hu_day and x["fahrzeug_id"] == polo]
    check(len(hu) == 1 and "(HU)" in hu[0]["route"], "HU-Fahrt angelegt")
    if hu:
        # Weg zur Werkstatt: Oberhofen -> Zell (5, dienstlich) -> Eugendorf (25, privat) => Tacho bei Ankunft = Abfahrt + 30
        check(hu[0]["abfahrt_km"] + 5 + 25 == 214000, f"Tacho bei Ankunft Werkstatt = HU-Stand ({hu[0]['abfahrt_km']} + 30)")
        check(hu[0]["km_p"] == 25 + 28, f"Weg zur Werkstatt + Heimweg privat ({hu[0]['km_p']})")
    api(base, "hu_apply", {}, 400)

    print("PDF")
    pdf = api(base, "pdf", {"typ": "monat", "jahr": 2025, "monat": 6}, raw=True)
    check(pdf[:5] == b"%PDF-", "Monats-PDF erzeugt")
    pj = api(base, "pdf", {"typ": "jahr", "jahr": 2025}, raw=True)
    check(pj[:5] == b"%PDF-", "Jahres-PDF erzeugt")
    if shutil.which("pdftotext"):
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "m.pdf").write_bytes(pdf); (tmp / "j.pdf").write_bytes(pj)
        tm = sh(f"pdftotext -layout {tmp}/m.pdf -"); tj = sh(f"pdftotext -layout {tmp}/j.pdf -")
        check("Fahrtenbuch Monatsübersicht" in tm and "Juni 2025" in tm and "Einzelsummen:" in tm, "Monats-PDF Text inkl. Umlaute")
        check("Jahresübersicht 2025" in tj and "Arbeitnehmerveranlagung" in tj and "Summen" in tj, "Jahres-PDF Text")

    print("Excel-Import")
    try:
        import openpyxl
        tmp = pathlib.Path(tempfile.mkdtemp())
        wb = openpyxl.Workbook(); ws = wb.active
        ws.append(["ID", "Bezeichnung", "Kennzeichen", "Endkilometer 2024", "Privat KM min", "Privat KM max", "Dienstlich Quote"])
        ws.append([5, "VW Polo", "VB-70", 206371, 5, 25, 85]); ws.append([6, "Škoda Neu", "VB-99", 1000, 3, 9, 70])
        wb.save(tmp / "Fahrzeugliste.xlsx")
        r = upload(base, "fahrzeuge", tmp / "Fahrzeugliste.xlsx")
        f = r.get("fahrzeuge", [])
        check(len(f) == 2 and f[0]["id"] == polo and f[1]["id"] is None and f[0]["start_km_vorjahr"] == 206371 and f[1]["bezeichnung"] == "Škoda Neu",
              "Fahrzeug-Excel: Excel-ID ignoriert, Zuordnung über Bezeichnung")
        import datetime
        wb = openpyxl.Workbook(); ws = wb.active
        ws.append(["Kennzeichen", "von", "bis"]); ws.append(["VB-70", datetime.date(2025, 1, 1), datetime.date(2025, 12, 31)]); ws.append(["XX", "01.02.2025", "31.12.2025"])
        wb.save(tmp / "Zeitraeume.xlsx")
        r = upload(base, "zeitraeume", tmp / "Zeitraeume.xlsx")
        zz = r.get("zeitraeume", [])
        check(len(zz) == 2 and zz[0] == {"fahrzeug_id": polo, "von": "2025-01-01", "bis": "2025-12-31"} and zz[1]["fahrzeug_id"] is None and zz[1]["von"] == "2025-02-01",
              "Zeiträume-Excel: Datum + Zuordnung")
        (tmp / "orte.csv").write_bytes("Ort;Bemerkung\nSt. Gilgen;x\nVöcklabruck;y\n".encode("cp1252"))
        r = upload(base, "orte", tmp / "orte.csv")
        check(r.get("orte") == ["St. Gilgen", "Vöcklabruck"], "Orte-CSV (Windows-Zeichensatz)")
    except ImportError:
        print("  (openpyxl fehlt – Excel-Test übersprungen)")

    print("Admin + Supabase-Umzug")
    r = api(base, "admin_users")
    check(len(r["users"]) == 2, "2 Benutzer")
    for t in ["users", "settings", "system_config", "fahrzeuge", "zeitraeume", "orte", "orte_distanz", "ort_koordinaten", "distanz_matrix",
              "jahres_start_km", "generation_settings", "hu_corrections", "fahrten"]:
        r = api(base, "admin_supabase", {"url": f"http://127.0.0.1:{supa_port}", "key": "service-role-test-key-123456", "table": t})
        check(r.get("gelesen") == len(SUPA[t]), f"Supabase {t}: {r.get('gelesen')} gelesen, {r.get('uebernommen')} übernommen")
    TOKEN["t"] = api(base, "login", {"username": "christian mayerhofer", "password": "geheim123"}).get("token", "")
    check(bool(TOKEN["t"]), "Admin-Passwort bleibt nach Umzug gültig")
    TOKEN["t"] = api(base, "login", {"username": "Neuhofer Dominik", "password": "altpass"}).get("token", "")
    check(bool(TOKEN["t"]), "Alter Supabase-Login (SHA-256) funktioniert")
    TOKEN["t"] = api(base, "login", {"username": "Neuhofer Dominik", "password": "altpass"}).get("token", "")
    check(bool(TOKEN["t"]), "Login nach Umstellung auf neues Passwort-Verfahren")
    i = api(base, "init")
    check(i["fahrzeuge"][0]["id"] == 70 and i["settings"]["entfernung"] == 18, "Fahrzeug-ID 70 + Stammdaten übernommen")
    check(i["orte"] == [{"ort": "Eugendorf", "km_einfach": 30}], "Orte + km einfach zusammengeführt")
    check(i["hu"][0]["angewendet_am"] is not None, "HU als angewendet markiert")
    y = api(base, "year_get", {"jahr": 2025})
    check(sum(len(v) for v in y["monate"].values()) == 1200, "1.200 Fahrten (mehrere Seiten) übernommen")


if __name__ == "__main__":
    main()
