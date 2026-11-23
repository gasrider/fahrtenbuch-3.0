"""Kilometerkette eines Jahres neu aufbauen - IMMER ab dem Jahres-Anker.

Eine zentrale Funktion fuer alle Stellen, die Fahrten aendern (Generator,
manuelle Bearbeitung, Plausibilitaetspruefung). So startet jeder Monat
genau beim Tacho-Stand, mit dem der Vormonat endet."""
import pandas as pd

from logic.helpers import _safe_int


def baue_kette_neu(year_data: dict, anchor: dict):
    """year_data: {(jahr, monat): DataFrame}, anchor: {fahrzeug_id: start_km}.
    Rueckgabe: (year_data_neu, end_km_pro_fahrzeug)."""
    km = {int(k): _safe_int(v) for k, v in (anchor or {}).items()}
    neu = {}
    for key in sorted(year_data.keys()):
        dfm = year_data[key]
        if dfm is None or dfm.empty:
            neu[key] = dfm
            continue
        dfm = dfm.copy()
        dfm["_sort"] = pd.to_datetime(dfm["datum"], errors="coerce")
        dfm = dfm.sort_values("_sort", kind="stable").drop(columns="_sort")
        rows = []
        for _, row in dfm.iterrows():
            r = row.to_dict()
            fz = _safe_int(r.get("fahrzeug_id"), default=None)
            if fz is not None:
                r["fahrzeug_id"] = fz
                r["abfahrt_km"] = km.get(fz, 0)
                km[fz] = km.get(fz, 0) + _safe_int(r.get("km_d")) + _safe_int(r.get("km_p"))
            else:
                r["fahrzeug_id"] = None
                r["abfahrt_km"] = 0
            rows.append(r)
        neu[key] = pd.DataFrame(rows).reset_index(drop=True)
    return neu, km
