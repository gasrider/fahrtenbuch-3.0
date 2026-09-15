"""Fahrten-Vorlagen und Kilometerstands-Berechnung (transparent, manuell korrigierbar)."""
from datetime import date
import calendar

import pandas as pd

from logic.constants import FAHRTEN_COLUMNS, WOCHENTAGE_KURZ
from logic.helpers import _safe_int, to_date, dauer_string
from logic.kalender import ist_arbeitstag


def recalc_abfahrt_km(df, fahrzeuge_df):
    """Berechnet abfahrt_km neu: pro Fahrzeug fortlaufend ab start_km_vorjahr."""
    if df is None or df.empty:
        return df
    df = df.copy()
    df["datum"] = df["datum"].astype(str)
    df = df.sort_values("datum").reset_index(drop=True)

    km = {}
    for _, r in fahrzeuge_df.iterrows():
        fid = _safe_int(r.get("id"), default=None)
        if fid is not None:
            km[fid] = _safe_int(r.get("start_km_vorjahr"))

    rows = []
    for _, row in df.iterrows():
        row = row.to_dict()
        fid = _safe_int(row.get("fahrzeug_id"), default=None)
        if fid in km:
            row["abfahrt_km"] = km[fid]
            km[fid] += _safe_int(row.get("km_d")) + _safe_int(row.get("km_p"))
        rows.append(row)
    return pd.DataFrame(rows)


def fahrzeug_fuer_datum(d: date, fahrzeuge_df, zeitraeume_df):
    """Liefert (id, bezeichnung) des Fahrzeugs, dessen Zeitraum d abdeckt – sonst das erste."""
    for _, z in zeitraeume_df.iterrows() if zeitraeume_df is not None and not zeitraeume_df.empty else []:
        if _safe_int(z.get("fahrzeug_id"), default=None) is None:
            continue
        von, bis = to_date(z.get("von")), to_date(z.get("bis"))
        if von and bis and von <= d <= bis:
            fid = _safe_int(z.get("fahrzeug_id"))
            match = fahrzeuge_df[fahrzeuge_df["id"] == fid]
            if not match.empty:
                return fid, str(match.iloc[0]["bezeichnung"])
    if fahrzeuge_df is not None and not fahrzeuge_df.empty:
        r = fahrzeuge_df.iloc[0]
        return _safe_int(r.get("id")), str(r.get("bezeichnung"))
    return None, ""


def baue_monats_vorlage(jahr, monat, settings, fahrzeuge_df, zeitraeume_df,
                        default_abf="07:00", default_ank="17:00"):
    """Erzeugt eine EDITIERBARE Vorlage für alle Tage eines Monats.

    Wichtig: Das ist nur eine Vorlage! Die Werte müssen mit den realen
    Fahrten abgeglichen und in der UI korrigiert werden, bevor gespeichert wird.
    """
    entfernung = _safe_int(settings.get("entfernung"))
    wohnort = str(settings.get("wohnort", "") or "")
    dienstort = str(settings.get("dienstort", "") or "")
    route_work = f"{wohnort} - {dienstort} - {wohnort}".strip(" -") or "Dienstreise"

    rows = []
    tage_im_monat = calendar.monthrange(jahr, monat)[1]
    for tag in range(1, tage_im_monat + 1):
        d = date(jahr, monat, tag)
        fid, fzg_name = fahrzeug_fuer_datum(d, fahrzeuge_df, zeitraeume_df)

        if not ist_arbeitstag(d):
            grund = "Wochenende" if d.weekday() >= 5 else "Feiertag"
            rows.append({"datum": d, "fahrzeug": fzg_name, "route": f"Keine Fahrt ({grund})",
                         "abf": "00:00", "ank": "00:00", "dauer": "00:00",
                         "km_d": 0, "km_p": 0, "abfahrt_km": None})
            continue

        km_d = entfernung * 2 if entfernung > 0 else 0
        rows.append({"datum": d, "fahrzeug": fzg_name, "route": route_work,
                     "abf": default_abf, "ank": default_ank,
                     "dauer": dauer_string(default_abf, default_ank),
                     "km_d": km_d, "km_p": 0, "abfahrt_km": None})

    return pd.DataFrame(rows, columns=["datum"] + FAHRTEN_COLUMNS[1:])