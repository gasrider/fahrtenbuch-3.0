#!/usr/bin/env python3
"""End-to-End-Test: frische Installation per installieren.php, Supabase-Uebernahme
(nachgebaute Supabase-REST-API), Generator, Kette, Bearbeiten, Privat-KM, HU, PDF,
Import, Benutzer. Braucht: php, MariaDB (mysql -uroot), python3 (+ openpyxl).

    python3 tests/e2e.py
"""
import re, hashlib, http.server, io, json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request
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
for r in SB["fahrten"]:
    if r["monat"] == 12 and r["km_d"] and time.strptime(r["datum"], "%Y-%m-%d").tm_wday in (1, 3):
        r["route"] = "Zell am Moos - Neumarkt (Schaden) - Zell am Moos"; r["km_d"] = 613
km = {69: 24659, 70: 206371, 71: 78607}
for r in sorted(SB["fahrten"], key=lambda r: r["datum"]):
    r["abfahrt_km"] = km[r["fahrzeug_id"]]; km[r["fahrzeug_id"]] += r["km_d"] + r["km_p"]
SB["fahrten"][40]["route"] = "Feiertag: Zell am Moos - Seekrichen am Wallersee (Angebot) - Zell am Moos"
SB["hu_corrections"] = [{"username": U, "fahrzeug_id": 70, "datum": "2026-12-20", "km_at_hu": 216000, "werkstattort": "Mondsee", "stopps_vor_hu": "", "stopps_nach_hu": ""}]
SB["generation_settings"][0]["settings_json"] = json.dumps({"target_km_min": 1650, "target_km_max": 2000, "modus": "Ganzes Jahr", "keyword_text": "Eugendorf:KFZ\nNeumarkt:Schaden\nSchleedorf:Antrag\nSeekrichen am Wallersee:Angebot\nKirchberg bei Mattighofena:KB"})
ORTE_EXTRA = True


# Falsche Strecke wie aus der alten App: "Neumarkt" wurde als Neumarkt in der Steiermark gefunden
SB["orte"].append({"username": U, "ort": "Neumarkt"})
SB["orte_distanz"].append({"username": U, "ort": "Neumarkt", "km_einfach": 291})
SB["distanz_matrix"].append({"username": U, "ort_a": "Neumarkt", "ort_b": "Zell am Moos", "key_a": "neumarkt", "key_b": "zell am moos", "km": 291, "quelle": "osrm"})

# ---------- nachgebaute OpenStreetMap-Dienste (Nominatim + OSRM) ----------
ORTE = {  # Name -> Liste von Treffern (Reihenfolge wie Nominatim: der "wichtigste" zuerst)
    "zell am moos": [(47.904, 13.315, "Zell am Moos, Oberösterreich")],
    "straßwalchen": [(47.980, 13.257, "Straßwalchen, Salzburg")],
    "eugendorf": [(47.867, 13.125, "Eugendorf, Salzburg")],
    "mondsee": [(47.856, 13.350, "Mondsee, Oberösterreich")],
    "henndorf": [(47.906, 13.188, "Henndorf am Wallersee, Salzburg")],
    "neumarkt": [(47.073, 14.427, "Neumarkt in der Steiermark, Steiermark")],  # wie echt: ohne Zusatz nur Steiermark
    "weitweg": [(47.071, 15.439, "Weitweg, Graz, Steiermark")],
    "weitweg bei salzburg": [(47.810, 13.040, "Weitweg, Salzburg")],
    "schleedorf": [(47.953, 13.150, "Schleedorf, Salzburg")],
    "seekirchen am wallersee": [(47.900, 13.133, "Seekirchen am Wallersee, Salzburg")],
    "frankenmarkt": [(47.986, 13.420, "Frankenmarkt, Oberösterreich")],
}


# Photon: bevorzugt Treffer nahe lat/lon, verzeiht Tippfehler
PHOTON = {
    "neumarkt": [(47.073, 14.427, "Neumarkt in der Steiermark", "Steiermark"), (47.945, 13.225, "Neumarkt am Wallersee", "Salzburg")],
    "seekrichen am wallersee": [(47.900, 13.133, "Seekirchen am Wallersee", "Salzburg")],
    "kirchberg bei mattighofen": [(48.080, 13.130, "Kirchberg bei Mattighofen", "Oberösterreich")],
}


class FakeGeo(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path); q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path.endswith("/api/"):
            name = q["q"].strip().lower()
            if name == "fehlerort":
                self.send_response(503); self.end_headers(); return
            feats = [{"geometry": {"coordinates": [o, a]}, "properties": {"name": nm, "state": stt, "country": "Österreich", "countrycode": "AT"}} for a, o, nm, stt in PHOTON.get(name, [])]
            data = json.dumps({"features": feats}).encode(); self.send_response(200); self.end_headers(); self.wfile.write(data); return
        if u.path.endswith("/search") and q["q"].lower().startswith("fehlerort"):
            self.send_response(429); self.end_headers(); return
        if u.path.endswith("/search"):
            name = q["q"].replace(", Österreich", "").strip().lower()
            res = ORTE.get(name, [])
            if q.get("bounded") == "1":
                l, t, r, b = map(float, q["viewbox"].split(","))
                res = [x for x in res if l <= x[1] <= r and b <= x[0] <= t]
            res = res[:int(q.get("limit", 10))]
            body = [{"lat": str(a), "lon": str(o), "display_name": d} for a, o, d in res]
        else:  # /table/v1/driving/lon,lat;lon,lat?annotations=distance
            import math
            pts = [tuple(map(float, p.split(","))) for p in u.path.split("/")[-1].split(";")]
            def hv(a, b):
                p1, p2 = math.radians(a[1]), math.radians(b[1]); dl = math.radians(b[0] - a[0])
                h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
                return 2 * 6371000 * math.asin(math.sqrt(h)) * 1.3
            src = [int(x) for x in q["sources"].split(";")] if "sources" in q else range(len(pts))
            dst = [int(x) for x in q["destinations"].split(";")] if "destinations" in q else range(len(pts))
            check(len(pts) <= 100, "OSRM-Anfrage mit höchstens 100 Orten")
            body = {"code": "Ok", "distances": [[hv(pts[a], pts[b]) for b in dst] for a in src]}
        data = json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(data)


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
PORT, SBPORT, GEOPORT = free_port(), free_port(), free_port()
srv = subprocess.Popen(["php", "-S", f"127.0.0.1:{PORT}", "-t", W], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
sb = http.server.ThreadingHTTPServer(("127.0.0.1", SBPORT), FakeSupabase); threading.Thread(target=sb.serve_forever, daemon=True).start()
geo = http.server.ThreadingHTTPServer(("127.0.0.1", GEOPORT), FakeGeo); threading.Thread(target=geo.serve_forever, daemon=True).start()
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
    with open(os.path.join(APP, "server", "config.php"), "w") as f: f.write(cfg.replace(");", f"  'test_supabase' => true,\n  'osrm_block' => 3,\n  'nominatim_url' => 'http://127.0.0.1:{GEOPORT}',\n  'osrm_url' => 'http://127.0.0.1:{GEOPORT}',\n  'photon_url' => 'http://127.0.0.1:{GEOPORT}',\n);"))

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
    check(len(d["zeitraeume"]) == 3 and len(d["orte"]) == 4 and len(d["matrix"]) == 2, "Zeiträume, Orte, Matrix übernommen")
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

    # ---------- Gesamt-Abgleich findet die kaputten Neumarkt-Fahrten ----------
    c, A = api("abgleich", {"jahr": 2026}, T)
    neum = [a for a in A["auffaellig"] if "Neumarkt" in a["route"]]
    check(c == 200 and len(neum) >= 6 and all(a["monat"] == 12 for a in A["auffaellig"]), f"Abgleich findet {len(neum)} Neumarkt-Fahrten (nur Dezember)")
    check(any("Neumarkt: 291" in x for x in A["ort_probleme"]), "Abgleich meldet Neumarkt mit 291 km einfach")

    # ---------- Online-Distanzen / Orte-Check ----------
    c, d = api("geo_liste", token=T)
    quellen = {o["ort"]: o["quellen"] for o in d["orte"]}
    check("Schleedorf" in quellen and "Keywords" in quellen["Schleedorf"], "Orte-Check zeigt auch Orte aus den Keywords")
    check("Fahrten" in quellen.get("Neumarkt", []) and "Mondsee" in quellen and "HU" in quellen["Mondsee"], "… und Orte aus Fahrten und HU")
    check(d["orte"][0]["ort"] in ("Neumarkt", "Schleedorf"), f"Problemfälle stehen oben ({d['orte'][0]['ort']})")
    check(any("Neumarkt" in x and "291" in x for x in d["lange_strecken"]), "Orte-Check zeigt die 291-km-Strecke als unplausibel")

    def geo_lauf(alle_neu, zusatz=()):
        c, plan = api("geo_plan", {"alle_neu": alle_neu, "zusatz": list(zusatz)}, T)
        if alle_neu: check(plan["zu_suchen"][0] == "Zell am Moos", "Wohnort wird zuerst gesucht")
        res = {}
        for o in plan["zu_suchen"]:
            c, r = api("geo_one", {"ort": o}, T); res[o] = r
        c, r = api("geo_route", {"orte": plan["orte"], "nur_fehlende": not alle_neu}, T)
        return res, r

    res, r = geo_lauf(True, ["Weitweg"])
    check("Neumarkt am Wallersee" in res["Neumarkt"]["treffer"], f"„Neumarkt“ = Neumarkt am Wallersee ({res['Neumarkt']['treffer']}, {res['Neumarkt']['km']} km)")
    check(not res["Weitweg"]["ok"] and "zu weit" in res["Weitweg"]["hinweis"], "Ort 180 km entfernt wird abgelehnt mit Hinweis")
    s_ = res["Seekrichen am Wallersee"]
    check(s_["ok"] and s_["vorschlag"] == "Seekirchen am Wallersee", f"Tippfehler Seekrichen: Photon findet ihn, Vorschlag {s_['vorschlag']}")
    k_ = res["Kirchberg bei Mattighofena"]
    check(not k_["ok"] and "Tippfehler" in k_["hinweis"], "Mattighofena nicht gefunden - Hinweis auf Tippfehler")
    c, r = api("ort_umbenennen", {"alt": "Kirchberg bei Mattighofena", "neu": "Kirchberg bei Mattighofen"}, T)
    check(c == 200 and r["zaehler"]["keywords"] == 1, "Ort korrigieren: " + r.get("message", str(r)))
    c, r = api("ort_umbenennen", {"alt": "Seekrichen am Wallersee", "neu": "Seekirchen am Wallersee"}, T)
    check(c == 200 and r["zaehler"]["fahrten"] == 1, "Seekrichen korrigiert: " + r.get("message", str(r)))
    c, J = api("jahr_get", query={"jahr": 2026}, token=T)
    r40 = [x for x in J["monate"][str(SB["fahrten"][40]["monat"])] if x["datum"] == SB["fahrten"][40]["datum"]][0]
    check(r40["route"] == "Feiertag: Zell am Moos - Seekirchen am Wallersee (Angebot) - Zell am Moos", "Route einer gespeicherten Fahrt korrigiert (Zweck + Feiertag bleiben)")
    check("Seekirchen am Wallersee:Angebot" in J["settings"]["keyword_text"] and "Mattighofena" not in J["settings"]["keyword_text"], "Keywords korrigiert")
    c, d = api("geo_liste", token=T)
    namen = [o["ort"] for o in d["orte"]]
    check("Seekrichen am Wallersee" not in namen and "Kirchberg bei Mattighofena" not in namen, "falsche Namen verschwinden aus dem Orte-Check")
    res2, r = geo_lauf(False)
    check(res2.get("Kirchberg bei Mattighofen", {}).get("ok") and res2.get("Seekirchen am Wallersee", {}).get("ok"), "korrigierte Orte werden gefunden")
    c, r = api("geo_one", {"ort": "Fehlerort"}, T)
    check(not r["ok"] and r["dienst_fehler"] and "nicht geantwortet" in r["hinweis"], "Ausfall des Kartendienstes wird gemeldet: " + r["hinweis"][:70])
    c, d = api("fz_get", token=T)
    mx = {(m["ort_a"], m["ort_b"]): m["km"] for m in d["matrix"]}
    check(max(mx.values()) < 120 and len(mx) >= 15, f"alle Strecken plausibel, max. {max(mx.values())} km ({len(mx)} Strecken, blockweise berechnet)")
    check(any("Schleedorf" in k for k in mx), "Keyword-Ort Schleedorf hat Strecken bekommen")
    # Abgleich + Korrektur der Dezember-Fahrten 2026
    c, A = api("abgleich", {"jahr": 2026}, T)
    check(len(A["auffaellig"]) >= 6 and not A["ort_probleme"], f"nach Ortssuche: {len(A['auffaellig'])} Fahrten mit zu vielen km erkannt")
    c, R = api("abgleich", {"jahr": 2026, "korrigieren": True}, T)
    check(c == 200 and "Danach keine auffälligen Fahrten mehr." in R["meldungen"], "Korrektur: danach keine auffälligen Fahrten: " + " | ".join(R["meldungen"][:2]))
    c, J26 = api("jahr_get", query={"jahr": 2026}, token=T)
    neum = [r for r in J26["monate"]["12"] if "Neumarkt" in r["route"] and "(HU)" not in r["route"]]
    check(neum and max(r["km_d"] for r in neum) < 80, f"Neumarkt-Fahrten jetzt {sorted({r['km_d'] for r in neum})} km")
    hu = [r for r in J26["monate"]["12"] if "(HU)" in r["route"]][0]
    m = re.search(r"minus (\d+) km Weg", " ".join(R["meldungen"]))
    check(m and hu["abfahrt_km"] + int(m.group(1)) == 216000, "HU 2026 neu ausgerichtet: Tacho bei Werkstatt = 216.000")
    check({o["ort"]: o["km_einfach"] for o in d["orte"]}["Neumarkt"] < 40, "km einfach Neumarkt automatisch korrigiert")
    c, r = api("geo_one", {"ort": "Weitweg", "suche": "Weitweg bei Salzburg"}, T)
    check(r["ok"] and r["km"] < 60, f"eigener Suchbegriff im Orte-Check findet den richtigen Ort ({r['km']} km)")
    c, d = api("geo_liste", token=T)
    check(not d["lange_strecken"] and all(o["luftlinie"] is not None and o["luftlinie"] < 60 for o in d["orte"]), "Orte-Check danach ohne Warnungen")
    # Fuer den Generator-Test die falsche Strecke nochmal hineinschreiben
    c, d = api("fz_get", token=T)
    d["matrix"] = [m for m in d["matrix"] if "Neumarkt" not in (m["ort_a"], m["ort_b"])] + [{"ort_a": "Neumarkt", "ort_b": "Zell am Moos", "km": 291}]
    api("matrix_save", {"matrix": d["matrix"]}, T)

    # ---------- Generator ----------
    S = {"modus": "Ganzes Jahr", "generierungs_monat": 1, "prob_werktag": 75, "prob_feiertag_urlaub": 5, "target_km_min": 1650, "target_km_max": 2000,
         "hauptfahrzeug_name": "Audi Etron", "hauptfahrzeug_anteil": 70, "anzahl_wochen": 2, "verteilung": "2x2 Wochen", "start_woche_1": "2025-04-07",
         "urlaub_fahrzeug_name": "VW Polo", "urlaub_km_min": 30, "urlaub_km_max": 80, "keyword_text": "Straßwalchen:Büro\nEugendorf:KFZ,Angebot\nMondsee:Antrag\nHenndorf:KB\nNeumarkt:Schaden"}
    c, d = api("generieren", {"jahr": 2025, "settings": S}, T)
    check(c == 200 and len(d["monate"]) == 12, "ganzes Jahr 2025 generiert")
    hf = [f for f in d["fehlende"] if f["ort"] == "Henndorf"]
    check(hf and "Keywords" in hf[0]["quellen"], "fehlende Distanz (Henndorf) wird mit Herkunft gemeldet")
    check(any("Neumarkt" in v for v in d["verdacht"]), f"falsche Neumarkt-Strecke (291 km) erkannt: {d['verdacht']}")
    maxd = max(r["km_d"] for rows in d["monate"].values() for r in rows)
    check(maxd < 360, f"keine Fahrt mit hunderten Dienst-km (max. {maxd} km)")
    c, A = api("abgleich", {"jahr": 2025}, T)
    check(not A["auffaellig"] and any("Neumarkt" in x and "291" in x for x in A["ort_probleme"]),
          f"Abgleich: normale Fahrten nicht gemeldet, aber falsche Strecke einmal genannt ({A['ort_probleme']})")
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
    br26, _, _, J26 = kette_ok(2026)
    check(br26 == 0 and {int(k): v for k, v in J26["anker"].items()} == kette_ok(2025)[1], "Folgejahr 2026 schließt nach Änderung 2025 lückenlos an")
    rows = J3["monate"]["3"] + [{"datum": "2025-04-30", "fahrzeug": "VW Polo", "route": "Falscher Monat", "abf": "09:00", "ank": "10:00", "km_d": 20, "km_p": 0}]
    api("monat_save", {"jahr": 2025, "monat": 3, "rows": rows}, T)
    c, Jx = api("jahr_get", query={"jahr": 2025}, token=T)
    check(any(r["route"] == "Falscher Monat" for r in Jx["monate"]["4"]) and not any(r["route"] == "Falscher Monat" for r in Jx["monate"]["3"]), "Fahrt mit April-Datum landet im April")
    c, d = api("monat_save", {"jahr": 2025, "monat": 3, "rows": rows + [{"datum": "2024-03-01", "fahrzeug": "VW Polo", "route": "x", "km_d": 1}]}, T)
    check(c == 400, "Fahrt aus anderem Jahr wird abgelehnt")
    c, d = api("fz_get", token=T)
    c, d = api("fz_save", {"fahrzeuge": d["fahrzeuge"][1:]}, T)
    check(c == 400 and "nicht gelöscht" in d["error"], "Fahrzeug mit Fahrten kann nicht gelöscht werden")

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
    vorher = {(r["datum"], r["fahrzeug_id"]): r for rows in J4["monate"].values() for r in rows}
    c, d = api("hu_anwenden", {}, T)
    check(c == 200, "HU angewendet")
    c, JH = api("jahr_get", query={"jahr": 2025}, token=T)
    geaendert = 0; gesamt = 0
    for rows in JH["monate"].values():
        for r in rows:
            v = vorher.get((r["datum"], r["fahrzeug_id"]))
            if not v or "(HU)" in r["route"] or r["fahrzeug_id"] != 69: continue
            t = r["km_d"] + r["km_p"]; dm = int(r["dauer"][:2]) * 60 + int(r["dauer"][3:])
            vt = v["km_d"] + v["km_p"]; vdm = int(v["dauer"][:2]) * 60 + int(v["dauer"][3:])
            if dm and t / dm * 60 <= 100 and vdm and vt / vdm * 60 <= 100:  # nur Fahrten, die vorher plausibel waren
                gesamt += 1; geaendert += r["dauer"] != v["dauer"]
    check(gesamt > 50 and geaendert == 0, f"HU verändert keine Fahrzeiten ({gesamt} Fahrten geprüft)")
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

    # ---------- Sicherung ----------
    c, B = api("sicherung", token=T)
    check(c == 200 and len(B["fb_fahrten"]) > 700 and B["fb_fahrzeuge"][0]["id"] == 69, f"Sicherung enthält {len(B['fb_fahrten'])} Fahrten")
    api("jahr_delete", {"jahr": 2025}, T)
    c, d = api("sicherung_laden", B, T)
    c2, J = api("jahr_get", query={"jahr": 2025}, token=T)
    check(c == 200 and len(J["monate"]) == 12, "Sicherung wiederhergestellt: gelöschtes Jahr 2025 wieder da")
    check(kette_ok(2025)[0] == 0, "Kette nach Wiederherstellung lückenlos")

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
    c, d = api("sicherung_laden", B, T2)
    check(c == 400 and "anderen Benutzer" in d["error"], "fremde Sicherung kann nicht eingespielt werden")
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
