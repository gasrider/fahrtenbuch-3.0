"""Plausibilitätsprüfung (Red Flags) + legitime Fahrzeiten-Korrektur.

Grundsatz: Die Kilometer sind die Realität und werden NIE automatisch verändert.
Bei unrealistischer Geschwindigkeit wird ausschließlich die FAHRZEIT angepasst,
sodat Kilometer und Dauer wieder zusammenpassen."""
import pandas as pd

from logic.constants import IGNORE_ROUTES
from logic.helpers import _safe_int, _safe_dauer_min


def _ist_ignore_route(route) -> bool:
    s = str(route)
    return any(s == ign or s.startswith(ign + ":") or s.startswith(ign + " ")
               for ign in IGNORE_ROUTES)


def scan_for_red_flags(df) -> list:
    """Prüft eine Monats-Tabelle auf unplausible Einträge."""
    flags = []
    if df is None or df.empty:
        return flags

    for _, row in df.iterrows():
        datum = str(row.get("datum", ""))[:10]
        km_d = _safe_int(row.get("km_d"))
        km_p = _safe_int(row.get("km_p"))
        total = km_d + km_p

        if total > 0:
            dauer_min = _safe_dauer_min(row.get("dauer"))
            if dauer_min > 0:
                speed = (total / dauer_min) * 60
                if speed > 130:
                    flags.append(f"🚨 {datum}: Unrealistische Geschwindigkeit! "
                                 f"{total} km in {row.get('dauer')} (~{speed:.0f} km/h).")

        if total == 0 and not _ist_ignore_route(row.get("route")):
            flags.append(f"🚨 {datum}: Dienstreise '{str(row.get('route'))[:30]}…' "
                         f"eingetragen, aber 0 km.")

        try:
            h1, m1 = map(int, str(row.get("abf")).split(':'))
            h2, m2 = map(int, str(row.get("ank")).split(':'))
            if (h2 * 60 + m2) < (h1 * 60 + m1) and total > 0:
                flags.append(f"🚨 {datum}: Ankunft ({row.get('ank')}) liegt vor der "
                             f"Abfahrt ({row.get('abf')}).")
        except (ValueError, TypeError, AttributeError):
            pass

    for datum, group in df.groupby("datum"):
        if len(group) > 1 and group["abf"].nunique() < len(group):
            flags.append(f"🚨 {str(datum)[:10]}: Mehrere Fahrten mit exakt gleicher "
                         f"Abfahrtszeit ({group['abf'].iloc[0]}).")
    return flags


def korrigiere_geschwindigkeiten_df(df, max_avg_speed=100):
    """LEGITIME Auto-Korrektur: Kilometer bleiben unverändert. Bei unrealistisch
    hoher Durchschnittsgeschwindigkeit wird nur die Dauer verlängert und die
    Ankunftszeit neu berechnet. Gibt (df, anzahl_korrekturen) zurück."""
    if df is None or df.empty:
        return df, 0
    df = df.copy().reset_index(drop=True)
    korrekturen = 0
    for idx, row in df.iterrows():
        total = _safe_int(row.get("km_d")) + _safe_int(row.get("km_p"))
        if total <= 0:
            continue
        dauer_min = _safe_dauer_min(row.get("dauer"))
        if dauer_min <= 0:
            continue
        speed = (total / dauer_min) * 60
        if speed > max_avg_speed:
            new_dauer = int(total / max_avg_speed * 60) + 20   # +20 Min Puffer
            new_dauer = min(new_dauer, 840)                    # max 14 h
            try:
                h, m = map(int, str(row.get("abf", "07:00")).split(':'))
                ank_min = min(h * 60 + m + new_dauer, 23 * 60 + 59)
                df.at[idx, "ank"] = f"{ank_min // 60:02d}:{ank_min % 60:02d}"
                df.at[idx, "dauer"] = f"{new_dauer // 60:02d}:{new_dauer % 60:02d}"
                korrekturen += 1
            except (ValueError, TypeError):
                pass
    return df, korrekturen


def korrigiere_geschwindigkeiten_generated(generated, max_avg_speed=100):
    """Fahrzeiten-Korrektur über alle generierten Monate.
    Gibt (generated, gesamt_korrekturen) zurück."""
    total = 0
    if not generated:
        return generated, 0
    for key in generated:
        df, n = korrigiere_geschwindigkeiten_df(generated[key]["data"], max_avg_speed)
        generated[key]["data"] = df
        total += n
    return generated, total


def pruefe_alle_monate(generated):
    """Führt scan_for_red_flags über alle Monate aus.
    Rückgabe: {monat_key: [flags]} – nur Monate MIT Auffälligkeiten."""
    result = {}
    if not generated:
        return result
    for key, data in generated.items():
        df = data["data"] if isinstance(data, dict) and "data" in data else data
        flags = scan_for_red_flags(df)
        if flags:
            result[key] = flags
    return result
