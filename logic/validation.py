"""Plausibilitätsprüfung von Fahrten (Red Flags) – legitime Qualitätskontrolle."""
import pandas as pd

from logic.constants import IGNORE_ROUTES
from logic.helpers import _safe_int, _safe_dauer_min


def _ist_ignore_route(route) -> bool:
    s = str(route)
    return any(s == ign or s.startswith(ign + ":") or s.startswith(ign + " ")
               for ign in IGNORE_ROUTES)


def scan_for_red_flags(df) -> list:
    """Prüft eine Monats-Tabelle auf unplausible Einträge. Gibt Liste von Hinweisen zurück."""
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