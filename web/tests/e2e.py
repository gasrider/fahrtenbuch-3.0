#!/usr/bin/env python3
"""End-to-End-Test: frische Installation per installieren.php, Supabase-Uebernahme
(nachgebaute Supabase-REST-API), Generator, Kette, Bearbeiten, Privat-KM, HU, PDF,
Import, Benutzer. Braucht: php, MariaDB (mysql -uroot), python3 (+ openpyxl).

    python3 tests/e2e.py
"""
import hashlib, http.server, io, json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OK = 0


def check(cond, text):
    global OK
    if not cond:
        print("FEHLER:", text); sys.exit(1)
    OK += 1
    print("ok  ", text)


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


# ---------- nachgebaute Supabase ----------
U = "christian mayerhofer"
SB = {
    "users": [{"username": U, "password": hashlib.sha256(b"streamlit-alt").hexdigest(), "email": "chef@example.com", "force_pw_change": False},
              {"username": "neuhofer dominik", "password": hashlib.sha256(b"alt123").hexdigest(), "email": "", "force_pw_change": False}],
    "settings": [{"username": U, "name": "Test", "pnr": "1", "wohnort": "Zell am Moos", "dienstort": "Straßwalchen", "entfernung": 20,
                  "taggeld_min_stunden": 5, "taggeld_basis": 10, "taggeld_stufung": 2.5, "taggeld_max_betrag": 30, "taggeld_max_stunden": 13, "km_geld": None}],
    "fahrzeuge": [{"id": 69, "username": U, "bezeichnung": "Audi Etron", "kennzeichen": "A1", "start_km_vorjahr": 24659, "privat_km_min": 5, "privat_km_max": 20, "dienstlich_quote": 90},
                  {"id": 70, "username": U, "bezeichnung": "VW Polo", "kennzeichen": "P1", "start_km_vorjahr": 206371, "privat_km_min": 5, "privat_km_max": 20, "dienstlich_quote": 90},
                  {"id": 71, "username": U, "bezeichnung": "VW T6.1", "kennzeichen": "T1", "start_km_vorjahr": 78607, "privat_km_min": 5, "privat_km_max": 20, "dienstlich_quote": 90}],
    "zeitraeume": [{"id": i, "username": U, "fahrzeug_id": f, "von": "2024-01-01", "bis": "2027-12-31"} for i, f in enumerate([69, 70, 71])],
    "orte": [{"username": U, "ort": o} for o in ["Eugendorf", "Mondsee", "Straßwalchen"]],
    "orte_distanz": [{"username": U, "ort": "Eugendorf", "km_einfach": 8}, {"username": U, "ort": "Mondsee", "km_einfach": 15}],
    "distanz_matrix": [{"username": U, "ort_a": "Eugendorf", "ort_b": "Zell am Moos", "key_a": "eugendorf", "key_b": "zell am moos", "km": 25, "quelle": "osrm"}],
    "jahres_start_km": [{"username": U, "jahr": 2026, "fahrzeug_id": f, "start_km": k} for f, k in [(69, 24659), (70, 206371), (71, 78607)]],
    "generation_settings": [{"username": U, "jahr": 2026, "settings_json": json.dumps({"target_km_min": 1650, "target_km_max": 2000, "modus": "Ganzes Jahr"})}],
    "hu_corrections": [], "ort_koordinaten": [],
    "system_config": [{"id": 1, "smtp_server": "smtp.example.com", "smtp_port": "465", "smtp_user": "x@example.com", "smtp_password": "geheim", "smtp_from_name": "Fahrtenbuch"}],
}
# 365 Fahrten 2026 mit lueckenloser Kette (wie aus der Streamlit-App)
km = {69: 24659, 70: 206371, 71: 78607}
SB["fahrten"] = []
d0 = time.mktime((2026, 1, 1, 12, 0, 0, 0, 0, -1))
for i in range(365):
    t = time.localtime(d0 + i * 86400); f = [69, 70, 71][i % 3]; kd = 0 if t.tm_wday >= 5 else 60 + i % 30
    SB["fahrten"].append({"username": U, "jahr": 2026, "monat": t.tm_mon, "datum": time.strftime("%Y-%m-%d", t), "fahrzeug_id": f,
                          "fahrzeug": {69: "Audi Etron", 70: "VW Polo", 71: "VW T6.1"}[f], "route": "Zell am Moos - Eugendorf (KFZ) - Zell am Moos" if kd else "Sonntag",
                          "km_d": kd, "km_p": 0 if kd else 12, "abf": "08:00", "ank": "17:30" if kd else "10:20", "dauer": "09:30" if kd else "00:20", "abfahrt_km": km[f]})
    km[f] += kd + (0 if kd else 12)


class FakeSupabase(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        t = u.path.split("/")[-1]
        if self.headers.get("apikey") != "SB-KEY":
            self.send_response(401); self.end_headers(); self.wfile.write(b'{"message":"Invalid API key"}'); return
        if t not in SB:
            self.send_response(404); self.end_headers(); self.wfile.write(b'{"message":"relation does not exist"}'); return
        off, lim = int(q.get("offset", ["0"])[0]), int(q.get("limit", ["1000"])[0])
        body = json.dumps(SB[t][off:off + lim]).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)


# ---------- Instanz aufsetzen ----------
subprocess.run(["python3", os.path.join(ROOT, "build", "make_installer.py")], check=True, stdout=subprocess.DEVNULL)
W = tempfile.mkdtemp(); APP = os.path.join(W, "fahrtenbuch"); os.mkdir(APP)
shutil.copy(os.path.join(ROOT, "dist", "installieren.php"), APP)
subprocess.run(["mysql", "-uroot", "-e", "DROP DATABASE IF EXISTS fb_e2e; CREATE DATABASE fb_e2e CHARACTER SET utf8mb4; "
                "CREATE USER IF NOT EXISTS 'fbe2e'@'localhost' IDENTIFIED BY 'fbe2e'; GRANT ALL ON fb_e2e.* TO 'fbe2e'@'localhost';"], check=True)
PORT, SBPORT = free_port(), free_port()
srv = subprocess.Popen(["php", "-S", f"127.0.0.1:{PORT}", "-t", W], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
sb = http.server.ThreadingHTTPServer(("127.0.0.1", SBPORT), FakeSupabase); threading.Thread(target=sb.serve_forever, daemon=True).start()
time.sleep(1)
BASE = f"http://127.0.0.1:{PORT}/fahrtenbuch/"


def req(path, data=None, token=None, form=None, raw=False, files=None):
    headers = {}
    body = None
    if token: headers["X-Auth-Token"] = token
    if form is not None: body = urllib.parse.urlencode(form).encode(); headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif files is not None:
        b = "----fbtest"; name, content = files
        body = (f"--{b}\r\nContent-Disposition: form-data; name=\"datei\"; filename=\"{name}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode() + content + f"\r\n--{b}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={b}"
    elif data is not None: body = json.dumps(data).encode(); headers["Content-Type"] = "application/json"
    r = urllib.request.Request(BASE + path, data=body, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=120) as res: c, b = res.status, res.read()
    except urllib.error.HTTPError as e: c, b = e.code, e.read()
    if raw: return c, b
    try: return c, json.loads(b)
    except Exception: return c, {"_raw": b[:500].decode(errors="replace")}


def api(action, data=None, token=None, **kw):
    q = kw.pop("query", None)
    return req("api.php?action=" + action + ("&" + urllib.parse.urlencode(q) if q else ""), data, token, **kw)


try:
    # ---------- Installation ----------
    c, b = req("installieren.php", raw=True)
    check(c == 200 and b"Fahrtenbuch installieren" in b, "Installer zeigt Formular")
    c, b = req("installieren.php", form={"db_host": "localhost", "db_name": "fb_e2e", "db_user": "fbe2e", "db_pass": "fbe2e",
                                         "admin_user": "Christian Mayerhofer", "admin_email": "chef@example.com", "admin_pw": "geheim123"}, raw=True)
    check(b"ist installiert" in b, "Installation erfolgreich")
    check(not os.path.exists(os.path.join(APP, "installieren.php")), "Installer hat sich selbst gelöscht")
    check(os.path.exists(os.path.join(APP, "server", "config.php")), "server/config.php erzeugt")
    with open(os.path.join(APP, "server", "config.php")) as f: cfg = f.read()
    with open(os.path.join(APP, "server", "config.php"), "w") as f: f.write(cfg.replace(");", "  'test_supabase' => true,\n);"))

    c, d = api("login", {"username": "christian mayerhofer", "password": "falsch"})
    check(c == 401, "falsches Passwort abgelehnt")
    c, d = api("login", {"username": "Christian Mayerhofer", "password": "geheim123"})
    check(c == 200 and d["user"]["is_admin"], "Admin-Login (Groß-/Kleinschreibung egal)")
    T = d["token"]

    # ---------- Supabase-Uebernahme ----------
    tabs = ["users", "settings", "fahrzeuge", "zeitraeume", "fahrten", "hu_corrections", "orte", "ort_koordinaten", "distanz_matrix", "jahres_start_km", "generation_settings", "system_config"]
    c, d = api("supabase_import", {"url": f"http://127.0.0.1:{SBPORT}", "key": "falsch", "tabelle": "users"}, T)
    check(c >= 400 and "Invalid API key" in d.get("error", ""), "falscher Supabase-Key wird gemeldet")
    for t in tabs:
        c, d = api("supabase_import", {"url": f"http://127.0.0.1:{SBPORT}", "key": "SB-KEY", "tabelle": t}, T)
        check(c == 200, f"Supabase-Übernahme {t}: {d.get('anzahl', d)}")
    c, d = api("fz_get", token=T)
    check([f["id"] for f in d["fahrzeuge"]] == [69, 70, 71], "Fahrzeug-IDs 69/70/71 erhalten")
    check(len(d["zeitraeume"]) == 3 and len(d["orte"]) == 3 and len(d["matrix"]) == 1, "Zeiträume, Orte, Matrix übernommen")
    check({o["ort"]: o["km_einfach"] for o in d["orte"]}["Eugendorf"] == 8, "km einfach übernommen")
    c, d = api("login", {"username": "christian mayerhofer", "password": "geheim123"})
    check(c == 200, "Installer-Passwort bleibt nach Übernahme gültig")
    c, d = api("login", {"username": "neuhofer dominik", "password": "alt123"})
    check(c == 200, "alter Streamlit-User meldet sich mit altem Passwort an")
    c, d = api("login", {"username": "neuhofer dominik", "password": "alt123"})
    check(c == 200, "… und nach der Umstellung auf sicheres Verfahren weiterhin")
    c, d = api("jahr_get", query={"jahr": 2026}, token=T)
    check(len(d["monate"]) == 12 and sum(len(v) for v in d["monate"].values()) == 365, "365 Fahrten 2026 übernommen")
    check(d["settings"].get("target_km_min") == 1650, "Generator-Einstellungen übernommen")

    def kette_ok(jahr, anker=None):
        c, d = api("jahr_get", query={"jahr": jahr}, token=T)
        a = {int(k): v for k, v in (anker or d["anker"]).items()}
        k = dict(a); brueche = 0
        for m in sorted(d["monate"], key=int):
            for r in d["monate"][m]:
                f = r["fahrzeug_id"]
                if f is None: continue
                if r["abfahrt_km"] != k[f]: brueche += 1
                k[f] += r["km_d"] + r["km_p"]
        c2, n = api("jahr_get", query={"jahr": jahr + 1}, token=T)
        return brueche, k, {int(x): v for x, v in n["anker"].items()}, d

    # ---------- Generator ----------
    S = {"modus": "Ganzes Jahr", "generierungs_monat": 1, "prob_werktag": 75, "prob_feiertag_urlaub": 5, "target_km_min": 1650, "target_km_max": 2000,
         "hauptfahrzeug_name": "Audi Etron", "hauptfahrzeug_anteil": 70, "anzahl_wochen": 2, "verteilung": "2x2 Wochen", "start_woche_1": "2025-04-07",
         "urlaub_fahrzeug_name": "VW Polo", "urlaub_km_min": 30, "urlaub_km_max": 80, "keyword_text": "Straßwalchen:Büro\nEugendorf:KFZ,Angebot\nMondsee:Antrag\nHenndorf:KB"}
    c, d = api("generieren", {"jahr": 2025, "settings": S}, T)
    check(c == 200 and len(d["monate"]) == 12, "ganzes Jahr 2025 generiert")
    check("Henndorf" in d["fehlende"], "fehlende Distanz (Henndorf) wird gemeldet")
    br, ende, naechst, J = kette_ok(2025)
    check(br == 0, "Kette 2025 lückenlos")
    check(ende == naechst, "Jahresende 2025 = Startwert 2026")
    check({int(k): v for k, v in J["anker"].items()} == {69: 24659, 70: 206371, 71: 78607}, "Jahres-Anker aus Start-KM (Vorjahr)")
    dienst = {int(m): sum(r["km_d"] for r in rows) for m, rows in J["monate"].items()}
    check(all(1000 < v <= 2100 for m, v in dienst.items() if m not in (4, 10)) and all(v <= 2100 for v in dienst.values()) and len(set(dienst.values())) >= 10,
          f"Monate gestreut (Urlaubsmonate Apr/Okt dürfen niedriger sein): {dienst}")
    check(all(len({r['datum'] for r in rows}) == len(rows) for rows in J["monate"].values()), "ein Eintrag pro Tag")
    urlaub = [r for rows in J["monate"].values() for r in rows if r["route"].startswith("Urlaub")]
    check(len(urlaub) >= 20, f"Urlaubstage berücksichtigt ({len(urlaub)})")
    check(any("Eugendorf" in r["route"] for rows in J["monate"].values() for r in rows), "Keywords verwendet")
    c, d = api("jahr_get", query={"jahr": 2025}, token=T)
    check(d["settings"]["start_woche_1"] == "2025-04-07", "Einstellungen pro Jahr gespeichert")

    S2 = dict(S, modus="Einzelner Monat", generierungs_monat=11)
    c, d = api("generieren", {"jahr": 2025, "settings": S2}, T)
    br, ende2, naechst, J2 = kette_ok(2025)
    check(c == 200 and br == 0 and ende2 == naechst, "Einzelmonat Nov nachgeneriert – Kette lückenlos")
    okt_ende = {}
    for r in J2["monate"]["10"]: okt_ende[r["fahrzeug_id"]] = r["abfahrt_km"] + r["km_d"] + r["km_p"]
    nov_start = {}
    for r in J2["monate"]["11"]:
        nov_start.setdefault(r["fahrzeug_id"], r["abfahrt_km"])
    check(all(nov_start[f] >= okt_ende.get(f, 0) for f in nov_start), "November startet nach dem Oktober-Ende, nicht am 1.1.")

    # ---------- Monat bearbeiten ----------
    rows = J2["monate"]["3"]
    rows[0]["km_d"] = rows[0]["km_d"] + 500
    rows[0]["fahrzeug"] = "VW T6.1"
    rows.append({"datum": "2025-03-15", "fahrzeug": "Audi Etron", "route": "Manuell", "abf": "09:00", "ank": "09:30", "km_d": 120, "km_p": 0})
    c, d = api("monat_save", {"jahr": 2025, "monat": 3, "rows": rows}, T)
    check(c == 200, "Monat März gespeichert")
    br, _, _, J3 = kette_ok(2025)
    check(br == 0, "Kette nach Bearbeitung lückenlos")
    check(J3["monate"]["3"][0]["fahrzeug_id"] == 71, "Fahrzeugwechsel über Namen übernommen")
    check(any(any("Geschwindigkeit" in f for f in v) for v in d["flags"].values()), "Prüfung meldet 120 km in 30 Min")
    m = [r for r in J3["monate"]["3"] if r["route"] == "Manuell"][0]
    check(m["dauer"] == "00:30", "Dauer aus Abfahrt/Ankunft berechnet")

    # ---------- Privat-KM ----------
    c, d = api("privat_verteilen", {"jahr": 2025, "fahrzeug_id": 70, "total": 6000, "anzahl_gross": 4, "gross_min": 300, "gross_max": 800, "normal_min": 5, "normal_max": 45}, T)
    check(c == 200, "Privat-KM verteilt: " + " | ".join(d.get("meldungen", [])[-1:]))
    br, _, _, J4 = kette_ok(2025)
    s = sum(r["km_p"] for rows in J4["monate"].values() for r in rows if r["fahrzeug_id"] == 70)
    check(br == 0 and s == 6000, f"Privat-Summe exakt 6000 ({s}), Kette lückenlos")

    # ---------- HU ----------
    anker = {int(k): v for k, v in J4["anker"].items()}
    vor = sum(r["km_d"] + r["km_p"] for rows in J4["monate"].values() for r in rows if r["fahrzeug_id"] == 69 and r["datum"] < "2025-06-10")
    hu_km = anker[69] + int(vor * 1.08)
    c, d = api("hu_save", {"hu": [{"fahrzeug_id": 69, "datum": "2025-06-10", "km_at_hu": hu_km, "werkstattort": "Mondsee", "stopps_vor_hu": "Eugendorf", "stopps_nach_hu": ""}]}, T)
    check(c == 200, "HU gespeichert")
    c, d = api("hu_anwenden", {}, T)
    check(c == 200, "HU angewendet")
    br, _, _, J5 = kette_ok(2025)
    hu = [r for rows in J5["monate"].values() for r in rows if "(HU)" in r["route"]]
    hin = 25 + 15  # Zell->Eugendorf (Matrix 25) + Eugendorf->Mondsee (|8-15| -> min 5 -> 7?)
    abf = hu[0]["abfahrt_km"] if hu else 0
    check(len(hu) == 1 and br == 0, "genau eine HU-Fahrt, Kette lückenlos")
    meld = " ".join(d["meldungen"])
    import re
    m = re.search(r"minus (\d+) km Weg", meld)
    check(m and abf + int(m.group(1)) == hu_km, f"Tacho bei Ankunft Werkstatt = HU-Stand exakt ({abf}+{m.group(1) if m else '?'} = {hu_km})")
    c, d = api("hu_anwenden", {}, T)
    br, _, _, J6 = kette_ok(2025)
    check("Bereits angewendet" in " ".join(d["meldungen"]) and J6["monate"] == J5["monate"], "2. Ausführung übersprungen, nichts verändert")

    # ---------- PDF ----------
    c, b = req("api.php?action=pdf&jahr=2025&monat=3", token=T, raw=True)
    check(c == 200 and b[:4] == b"%PDF" and len(b) > 3000, f"Monats-PDF ({len(b)} Bytes)")
    c, b = req("api.php?action=pdf&jahr=2025", token=T, raw=True)
    check(c == 200 and b[:4] == b"%PDF", f"Jahres-PDF ({len(b)} Bytes)")
    open(os.path.join(tempfile.gettempdir(), "fb_monat.pdf"), "wb").write(req("api.php?action=pdf&jahr=2025&monat=3", token=T, raw=True)[1])
    c, b = req("api.php?action=pdf&jahr=2030&monat=1", token=T, raw=True)
    check(c == 404, "PDF ohne Daten: verständliche Meldung")

    # ---------- Import ----------
    try:
        import openpyxl
        wb = openpyxl.Workbook(); ws = wb.active
        ws.append(["ID", "Bezeichnung", "Kennzeichen", "Endkilometer 2024", "Dienstlich Quote"])
        ws.append([999, "VW Polo", "P1", 210000, 80]); ws.append([998, "Skoda Neu", "S1", 5000, None])
        bio = io.BytesIO(); wb.save(bio)
        c, d = api("import", token=T, files=("Fahrzeugliste.xlsx", bio.getvalue()), query={"art": "fahrzeuge"})
        check(c == 200 and d["fahrzeuge"][0]["start_km_vorjahr"] == 210000 and d["fahrzeuge"][1]["dienstlich_quote"] == 90 and "id" not in d["fahrzeuge"][0], "Excel-Fahrzeugliste gelesen, Excel-IDs ignoriert")
        wb = openpyxl.Workbook(); ws = wb.active
        import datetime
        ws.append(["Kennzeichen", "von", "bis"]); ws.append(["P1", datetime.date(2025, 1, 1), datetime.date(2025, 12, 31)])
        bio = io.BytesIO(); wb.save(bio)
        c, d = api("import", token=T, files=("Zeitraeume.xlsx", bio.getvalue()), query={"art": "zeitraeume"})
        check(c == 200 and d["zeitraeume"] == [{"fahrzeug_id": 70, "von": "2025-01-01", "bis": "2025-12-31"}], "Excel-Zeiträume: Datum + Zuordnung über Kennzeichen")
    except ImportError:
        print("    (openpyxl fehlt – Excel-Test übersprungen)")
    c, d = api("import", token=T, files=("orte.csv", "Ort;PLZ\nHenndorf;5302\nMondsee;5310\n".encode("cp1252")), query={"art": "orte"})
    check(c == 200 and d["orte"] == ["Henndorf", "Mondsee"], "CSV-Orte gelesen")

    # ---------- Fahrzeuge ID-stabil ----------
    c, d = api("fz_get", token=T)
    fz = d["fahrzeuge"] + [{"bezeichnung": "Skoda Neu", "kennzeichen": "S1", "start_km_vorjahr": 5000}]
    fz[1]["id"] = ""  # Zeile ohne ID -> Zuordnung ueber Bezeichnung
    c, d = api("fz_save", {"fahrzeuge": fz}, T)
    check([f["id"] for f in d["fahrzeuge"]][:3] == [69, 70, 71] and len(d["fahrzeuge"]) == 4, "Fahrzeuge speichern hält IDs stabil")
    c, d = api("zr_save", {"zeitraeume": [{"fahrzeug_id": 69, "von": "2025-12-01", "bis": "2025-01-01"}]}, T)
    check(c == 400, "Zeitraum mit Ende vor Beginn abgelehnt")

    # ---------- Benutzer / Passwort ----------
    c, d = api("user_save", {"username": "Test Kollege", "email": "k@example.com", "password": "start123"}, T)
    check(c == 200, "Admin legt Zugang an")
    c, d = api("login", {"username": "test kollege", "password": "start123"})
    T2 = d["token"]
    check(d["user"]["force_pw_change"], "neuer Zugang muss Passwort ändern")
    c, d = api("stamm_get", token=T2)
    check(c == 428, "ohne neues Passwort keine Daten")
    c, d = api("password", {"new": "meins456"}, T2)
    check(c == 200 and not d["user"]["force_pw_change"], "Passwort gesetzt")
    c, d = api("users", token=T2)
    check(c == 403, "Nicht-Admin kommt nicht in die Benutzerverwaltung")
    c, d = api("jahr_get", query={"jahr": 2025}, token=T2)
    check(c == 200 and len(d["monate"]) == 0 and len(d["fahrzeuge"]) == 0, "Benutzer sehen nur ihre eigenen Daten")
    c, d = api("forgot", {"username": "christian mayerhofer"})
    check(c in (502, 503), "Passwort vergessen ohne funktionierende Mail: Fehlermeldung")
    c, d = api("login", {"username": "christian mayerhofer", "password": "geheim123"})
    check(c == 200, "… und das alte Passwort bleibt gültig")
    c, d = api("settings", token=T)
    check(d["settings"]["mail_mode"] == "smtp" and d["settings"]["smtp_pass_set"] and "smtp_pass" not in d["settings"], "SMTP übernommen, Passwort wird nie zurückgegeben")

    # ---------- Sicherheit / Update ----------
    c, b = req("server/config.php", raw=True)
    check(b"fbe2e" not in b, "config.php gibt keine Zugangsdaten aus")
    shutil.copy(os.path.join(ROOT, "dist", "installieren.php"), APP)
    c, b = req("installieren.php", raw=True)
    check(b"aktualisiert" in b, "Update über erneuten Installer")
    c, d = api("login", {"username": "christian mayerhofer", "password": "geheim123"})
    c2, d2 = api("jahr_get", query={"jahr": 2025}, token=d["token"])
    check(c == 200 and len(d2["monate"]) == 12, "nach Update: Login + Daten unverändert")
    print(f"\nALLE {OK} PRÜFUNGEN BESTANDEN")
    print("Instanz:", BASE, "| Ordner:", W)
    if os.environ.get("KEEP"):
        print("läuft weiter (KEEP=1) – Strg+C zum Beenden"); srv.wait()
finally:
    if not os.environ.get("KEEP"):
        srv.terminate(); sb.shutdown()
