"""Privat-Kilometer verteilen: Fuer Fahrzeuge mit ungenau gefuehrter privater
Nutzung wird eine eingegebene Jahres-Summe realistisch auf das Jahr verteilt
(inkl. weniger grosser Fahrten). Es handelt sich um REAL gefahrene km, die
nachtraeglich pauschal erfasst werden."""
import random
from datetime import date

import pandas as pd

from logic.helpers import _safe_int


def _dauer_fuer_km(km, rng):
    dauer = int(km / 70 * 60) + int(rng.randint(5, 30))
    return max(min(dauer, 840), 15)


def _zeiten_fuer(km, rng, gross=False):
    dauer = _dauer_fuer_km(km, rng)
    if gross:
        start_min = 6 * 60 + int(rng.randint(0, 120))
    else:
        start_min = 8 * 60 + int(rng.randint(0, 9 * 60))
    start_min = min(start_min, 20 * 60)
    ank_min = min(start_min + dauer, 23 * 60 + 59)
    abf = f"{start_min // 60:02d}:{start_min % 60:02d}"
    ank = f"{ank_min // 60:02d}:{ank_min % 60:02d}"
    dauer_str = f"{dauer // 60:02d}:{dauer % 60:02d}"
    return abf, ank, dauer_str


def verteile_privat_km(year_data, fahrzeug_id, total_km, fzg_name,
                       anzahl_gross=4, gross_min=300, gross_max=800,
                       normal_min=5, normal_max=45, anchor=None, seed=None):
    """Verteilt total_km als km_p auf das Jahr. Gibt (year_data, km_ende,
    meldungen) zurueck - Speichern macht die UI."""
    rng = random.Random(seed)
    meldungen = []
    fahrzeug_id = int(fahrzeug_id)
    total_km = int(total_km)
    if not year_data:
        raise ValueError("Keine Fahrten vorhanden - zuerst generieren.")
    if total_km <= 0:
        raise ValueError("Privat-KM Summe muss groesser 0 sein.")

    for key in year_data:
        df = year_data[key]
        if df is not None and not df.empty:
            df['datum'] = pd.to_datetime(df['datum']).dt.date
            year_data[key] = df

    alle_datum = set()
    fz_rows = {}
    hu_tage = set()
    fz_arbeitstage = set()
    for key in sorted(year_data.keys()):
        df = year_data[key]
        for idx, row in df.iterrows():
            d = row.get('datum')
            d = d if isinstance(d, date) else pd.to_datetime(d).date()
            alle_datum.add(d)
            if _safe_int(row.get('fahrzeug_id'), default=None) == fahrzeug_id:
                fz_rows[d] = (key, idx)
                if '(HU)' in str(row.get('route', '')):
                    hu_tage.add(d)
                if _safe_int(row.get('km_d')) > 0:
                    fz_arbeitstage.add(d)

    if hu_tage:
        meldungen.append(f"- {len(hu_tage)} HU-Tag(e) bleiben von der Verteilung ausgenommen.")

    # 1) Bestehende Privat-KM des Fahrzeugs auf 0 (HU-Tag bleibt)
    for d, (key, idx) in fz_rows.items():
        if d not in hu_tage:
            year_data[key].at[idx, 'km_p'] = 0

    # 2) Grosse Fahrten (nur Tage ohne Dienstfahrt dieses Fahrzeugs)
    kandidaten_gross = sorted(
        d for d in alle_datum
        if d not in hu_tage and d not in fz_arbeitstage
    )
    if len(kandidaten_gross) < 20:
        kandidaten_gross = sorted(d for d in alle_datum if d not in hu_tage)

    grosse = {}
    min_abstand = 21
    versuche = 0
    while len(grosse) < anzahl_gross and versuche < 800:
        versuche += 1
        d = rng.choice(kandidaten_gross)
        if all(abs((d - o).days) >= min_abstand for o in grosse):
            grosse[d] = int(rng.randint(gross_min, gross_max))

    sum_gross = sum(grosse.values())
    if sum_gross > total_km:
        meldungen.append(f"- HINWEIS: Gesamt-Summe ({total_km:,} km) reicht fuer "
                         f"{len(grosse)} grosse Fahrten (~{sum_gross:,} km) nicht - "
                         "Anzahl wurde reduziert.")
        while sum_gross > total_km and grosse:
            d_max = max(grosse, key=lambda x: grosse[x])
            sum_gross -= grosse.pop(d_max)
    rest = total_km - sum_gross
    meldungen.append(f"- {len(grosse)} grosse Privatfahrten (Urlaub/Ausfluege) "
                     f"mit zusammen {sum_gross:,} km.")

    # 3) Rest auf normale Tage (proportional -> Summe exakt)
    verteilt = dict(grosse)
    if rest > 0:
        frei = [d for d in sorted(alle_datum)
                if d not in hu_tage and d not in verteilt]
        rng.shuffle(frei)
        ziel = max((normal_min + normal_max) / 2.0, 1)
        n = max(1, min(len(frei), int(round(rest / ziel)) + 1))
        werte = {}
        for d in frei[:n]:
            lo = normal_min
            hi = max(normal_min + 1, normal_max)
            werte[d] = int(rng.randint(lo, hi))
        s = sum(werte.values())
        if s == 0:
            for d in werte:
                werte[d] = 1
            s = len(werte)
        faktor = rest / s
        zuteil = {d: int(round(v * faktor)) for d, v in werte.items()}
        diff = rest - sum(zuteil.values())
        tage = list(zuteil.keys())
        guard = 0
        while diff != 0 and tage and guard < 100000:
            guard += 1
            d = rng.choice(tage)
            if diff > 0:
                zuteil[d] += 1
                diff -= 1
            elif zuteil[d] > 0:
                zuteil[d] -= 1
                diff += 1
        for d, km in zuteil.items():
            if km > 0:
                verteilt[d] = km

    meldungen.append(f"- {len(verteilt) - len(grosse)} weitere Tage mit privaten Fahrten.")

    # 4a) Vorhandene Zeilen des Fahrzeugs aktualisieren
    for d, km in verteilt.items():
        km = int(km)
        if km <= 0 or d not in fz_rows:
            continue
        gross = d in grosse
        key, idx = fz_rows[d]
        row = year_data[key].loc[idx]
        if _safe_int(row.get('km_d')) == 0:
            route_alt = str(row.get('route', ''))
            if ('Keine Fahrt' in route_alt or route_alt.strip() == ''
                    or str(row.get('abf', '00:00')) == '00:00'):
                abf, ank, dauer = _zeiten_fuer(km, rng, gross)
                year_data[key].at[idx, 'route'] = ("Privatfahrt (Urlaub)" if gross
                                                   else "Privatfahrt")
                year_data[key].at[idx, 'abf'] = abf
                year_data[key].at[idx, 'ank'] = ank
                year_data[key].at[idx, 'dauer'] = dauer
        year_data[key].at[idx, 'km_p'] = km

    # 4b) Neue Zeilen fuer Tage ohne Fahrzeug-Eintrag
    neue_zeilen = {}
    for d, km in sorted(verteilt.items()):
        km = int(km)
        if km <= 0 or d in fz_rows:
            continue
        gross = d in grosse
        abf, ank, dauer = _zeiten_fuer(km, rng, gross)
        neuer = {"datum": d, "fahrzeug_id": fahrzeug_id, "fahrzeug": fzg_name,
                 "route": "Privatfahrt (Urlaub)" if gross else "Privatfahrt",
                 "km_d": 0, "km_p": km, "abf": abf, "ank": ank,
                 "dauer": dauer, "abfahrt_km": 0}
        key = (d.year, d.month)
        neue_zeilen.setdefault(key, []).append(neuer)
    for key, zeilen in neue_zeilen.items():
        if key in year_data:
            df = year_data[key]
            df = pd.concat([df, pd.DataFrame(zeilen)], ignore_index=True)
            df = df.sort_values('datum', kind='stable').reset_index(drop=True)
            year_data[key] = df

    # 5) Kilometerkette neu aufbauen
    km = dict(anchor) if anchor else {}
    for key in sorted(year_data.keys()):
        df = year_data[key].copy()
        df = df.sort_values('datum', kind='stable').reset_index(drop=True)
        rows = []
        for _, row in df.iterrows():
            r = row.to_dict()
            fz = r.get('fahrzeug_id')
            if fz is not None and not pd.isna(fz):
                fz = int(fz)
                r['abfahrt_km'] = km.get(fz, 0)
                km[fz] = km.get(fz, 0) + _safe_int(r.get('km_d')) + _safe_int(r.get('km_p'))
            else:
                r['abfahrt_km'] = 0
            rows.append(r)
        year_data[key] = pd.DataFrame(rows)

    # 6) Zusammenfassung
    summe = 0
    tage = 0
    for key in year_data:
        df = year_data[key]
        d = df[df['fahrzeug_id'] == fahrzeug_id]
        if not d.empty:
            summe += _safe_int(pd.to_numeric(d['km_p'], errors='coerce').fillna(0).sum())
            tage += int((pd.to_numeric(d['km_p'], errors='coerce').fillna(0) > 0).sum())
    meldungen.append(f"- Jahres-Summe privat {fzg_name}: **{summe:,} km** "
                     f"auf {tage} Tagen (inkl. HU-Tag, falls vorhanden).")
    return year_data, km, meldungen
