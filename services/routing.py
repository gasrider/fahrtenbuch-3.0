"""Online-Distanzen ueber OpenStreetMap - KEIN API-Key noetig.

Zwei kostenlose Dienste:
- Nominatim (nominatim.openstreetmap.org): Ortsname -> Koordinaten (Geocoding)
- OSRM (router.project-osrm.org): Koordinaten -> echte Fahrstrecke in km (Routing)

Regeln der Dienste beachten: Nominatim max. 1 Anfrage/Sekunde (deswegen
GEO_PAUSE), OSRM gibt sich mit kurzen Pausen zufrieden (OSRM_PAUSE).

Alle Ergebnisse werden in Supabase gecacht (Tabellen ort_koordinaten und
distanz_matrix) - jede Strecke wird also nur EINMAL im Leben berechnet.
Schlaegt eine Route fehl, faellt die Funktion auf eine Haversine-Schaetzung
(Luftlinie x 1,25) zurueck und meldet das.

Dieses Modul ist bewusst frei von Streamlit - es braucht nur 'requests'.
"""
import time

import requests

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_OSRM_URL = "https://router.project-osrm.org/route/v1/driving"

_UA = {"User-Agent": "Fahrtenbuch-App/3.0 (Streamlit Cloud; OpenStreetMap-Distanzen)"}

# Pausen zwischen den Anfragen (Nominatim verlangt max. 1/s)
GEO_PAUSE = 1.1
OSRM_PAUSE = 0.2
TIMEOUT_GEO = 15
TIMEOUT_OSRM = 25

# Haversine-Schaetzung: Luftlinie x FAKTOR_STRASSE als Notfall
FAKTOR_STRASSE = 1.25


def norm_key(name):
    """Ortsname normalisieren (getrimmt, kleingeschrieben) - identisch zur
    Normierung im Generator (_norm_ort), damit Lookups immer greifen."""
    return str(name).strip().lower()


def geocodiere_ort(ort_name, log=None):
    """Ortsname -> {"lat": float, "lon": float, "display_name": str} oder None.

    3-Stufen-Strategie (Austria zuerst, dann D, dann weltweit), damit
    'Neumarkt' nicht in Deutschland landet. Liest die Antwort immer mit
    limit=1 und nimmt den besten Treffer.
    """
    name = str(ort_name).strip()
    if not name:
        return None
    stufen = [(f"{name}, Österreich", "at"),
              (name, "at,de"),
              (name, None)]
    for query, cc in stufen:
        params = {"q": query, "format": "json", "limit": 1}
        if cc:
            params["countrycodes"] = cc
        try:
            r = requests.get(_NOMINATIM_URL, params=params, headers=_UA,
                             timeout=TIMEOUT_GEO)
            data = r.json()
        except Exception:
            data = []
        if data:
            hit = data[0]
            try:
                return {"lat": float(hit["lat"]), "lon": float(hit["lon"]),
                        "display_name": str(hit.get("display_name", ""))}
            except (KeyError, TypeError, ValueError):
                pass
        time.sleep(GEO_PAUSE)
    return None


def routen_km(lat1, lon1, lat2, lon2):
    """Echte Fahrstrecke in km (ganzzahlig) via OSRM - None bei Fehler."""
    url = (f"{_OSRM_URL}/{lon1},{lat1};{lon2},{lat2}"
           "?overview=false&alternatives=false&steps=false")
    try:
        r = requests.get(url, headers=_UA, timeout=TIMEOUT_OSRM)
        data = r.json()
        if data.get("code") == "Ok" and data.get("routes"):
            meter = float(data["routes"][0].get("distance", 0) or 0)
            if meter > 0:
                return int(round(meter / 1000.0))
    except Exception:
        pass
    return None


def haversine_km(lat1, lon1, lat2, lon2):
    """Luftlinie in km x FAKTOR_STRASSE - Notfall-Schaetzung."""
    import math
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return int(round(2 * 6371.0 * math.asin(math.sqrt(a)) * FAKTOR_STRASSE))


def berechne_distanz_matrix(ort_liste, wohnort, dienstort="",
                            zusatz_orte=None, vorhandene=None,
                            progress=None):
    """Geocodiert alle Orte und berechnet die paarweisen Fahrstrecken.

    ort_liste:  Kundenorte (aus Tabelle 'orte')
    wohnort:    Wohnort des Users (wird als eigener Punkt geocodiert)
    dienstort:  Dienstort (optional, wird mitgenommen)
    zusatz_orte: weitere Orte als Liste (z. B. Werkstätten)
    vorhandene: {(ka, kb): km} - bereits gecachte Strecken werden
                uebersprungen (inkrementelles Nachrechnen neuer Orte)
    progress:   callable(fertig, gesamt, text) oder None

    Rueckgabe: (koordinaten, matrix, meldungen)
      koordinaten: {ort_key: {"lat", "lon", "display_name", "ort", "ok"}}
                   (ok=False bei Orten, die nicht gefunden wurden)
      matrix:      {(ka, kb): km} mit ka <= kb (echte Fahrstrecken)
      meldungen:   Liste von Hinweis-Strings fuer die UI
    """
    # --- 1) Ortsliste aufbauen (Dubletten case-insensitive entfernen) ---
    reihenfolge = []
    gesehen = set()
    for o in list(ort_liste or []) + [wohnort, dienstort] + list(zusatz_orte or []):
        o = str(o or "").strip()
        if not o:
            continue
        k = norm_key(o)
        if k and k not in gesehen:
            gesehen.add(k)
            reihenfolge.append(o)

    koordinaten = {}
    meldungen = []
    nicht_gefunden = []

    # --- 2) Geocoding (max 1 Anfrage/Sek) ---
    gesamt_geo = len(reihenfolge)
    for i, o in enumerate(reihenfolge, start=1):
        k = norm_key(o)
        if callable(progress):
            progress(i - 1, gesamt_geo * 2, f"Ort {i}/{gesamt_geo} suchen: {o}")
        res = geocodiere_ort(o)
        if res:
            koordinaten[k] = {"lat": res["lat"], "lon": res["lon"],
                              "display_name": res["display_name"],
                              "ort": o, "ok": True}
        else:
            koordinaten[k] = {"lat": None, "lon": None, "display_name": "",
                              "ort": o, "ok": False}
            nicht_gefunden.append(o)

    if nicht_gefunden:
        meldungen.append(f"Nicht gefunden (keine Online-Distanzen fuer diese "
                         f"Orte): {', '.join(nicht_gefunden)} - bitte "
                         "Schreibweise pruefen oder manuell eintragen.")

    # --- 3) Paarweise Routen (echte Fahrstrecken) ---
    vorhandene = vorhandene or {}
    paare = []
    keys = [k for k in reihenfolge if norm_key(k)]
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = norm_key(keys[i]), norm_key(keys[j])
            if a > b:
                a, b = b, a
            if (a, b) in vorhandene:
                continue  # gecacht - nicht nochmal rechnen
            paare.append((a, b))

    matrix = dict(vorhandene)
    geschaetzt = 0
    fehler_routen = []
    gesamt_routen = len(paare)
    for idx, (a, b) in enumerate(paare, start=1):
        ka, kb = koordinaten.get(a, {}), koordinaten.get(b, {})
        if callable(progress):
            name_a = ka.get("ort") or a
            name_b = kb.get("ort") or b
            progress(gesamt_geo + idx - 1, gesamt_geo * 2,
                     f"Strecke {idx}/{gesamt_routen}: {name_a} -> {name_b}")
        if not ka.get("ok") or not kb.get("ok"):
            continue
        km = routen_km(ka["lat"], ka["lon"], kb["lat"], kb["lon"])
        if km is None:
            km = haversine_km(ka["lat"], ka["lon"], kb["lat"], kb["lon"])
            geschaetzt += 1
            fehler_routen.append(f"{ka.get('ort', a)} - {kb.get('ort', b)}")
        time.sleep(OSRM_PAUSE)
        matrix[(a, b)] = int(km)

    if geschaetzt:
        meldungen.append(
            f"{geschaetzt} Strecke(n) konnten nicht geroutet werden und wurden "
            f"aus der Luftlinie geschaetzt (x {FAKTOR_STRASSE}): "
            f"{', '.join(fehler_routen[:8])}"
            + (" ..." if len(fehler_routen) > 8 else ""))

    if callable(progress):
        progress(gesamt_geo * 2, gesamt_geo * 2, "Fertig.")
    return koordinaten, matrix, meldungen
