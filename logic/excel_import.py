"""Excel/CSV-Import für Fahrzeuge, Zeiträume und Orte (tolerante Spaltenerkennung)."""
import pandas as pd

from logic.helpers import normalize_df_cols, _safe_int, _parse_date_iso

FAHRZEUG_KANDIDATEN = {
    "bezeichnung": ["bezeichnung", "fahrzeug", "name", "auto"],
    "kennzeichen": ["kennzeichen"],
    "start_km_vorjahr": ["start_km_vorjahr", "start_km", "kilometerstand", "km_stand", "startkilometer"],
    "privat_km_min": ["privat_km_min", "privat_min"],
    "privat_km_max": ["privat_km_max", "privat_max"],
    "dienstlich_quote": ["dienstlich_quote", "dienstlich", "quote"],
}
ZEITRAUM_KANDIDATEN = {
    "fahrzeug": ["fahrzeug", "bezeichnung", "name"],
    "von": ["von", "ab", "beginn", "start"],
    "bis": ["bis", "ende", "end"],
}
ORTE_KANDIDATEN = {
    "ort": ["ort", "ortsname", "adresse", "ziel", "kunde", "werkstattort"],
}


def _lese_datei(uploaded_file) -> dict:
    """Liest Excel (alle Sheets) oder CSV. Rückgabe: {sheet_name: DataFrame}."""
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        try:
            return {"daten": pd.read_csv(uploaded_file, sep=None, engine="python")}
        except UnicodeDecodeError:
            uploaded_file.seek(0)
            return {"daten": pd.read_csv(uploaded_file, sep=None, engine="python",
                                         encoding="latin-1")}
    xls = pd.ExcelFile(uploaded_file)
    return {n: xls.parse(n) for n in xls.sheet_names}


def _zuordnen(df, kandidaten):
    """Ordnet Spalten zu: erst exakte Treffer, dann Teilstring-Treffer."""
    df = normalize_df_cols(df)
    ergebnis = {}
    for ziel, kands in kandidaten.items():
        for k in kands:
            if k in df.columns:
                ergebnis[ziel] = k
                break
        else:
            for col in df.columns:
                if any(k in col for k in kands):
                    ergebnis[ziel] = col
                    break
    return df, ergebnis


def lade_fahrzeuge(uploaded_file) -> pd.DataFrame:
    sheets = _lese_datei(uploaded_file)
    rows = []
    for _, df in sheets.items():
        if df.empty:
            continue
        df, m = _zuordnen(df, FAHRZEUG_KANDIDATEN)
        if "bezeichnung" not in m:
            continue
        for _, r in df.iterrows():
            bez = str(r.get(m["bezeichnung"], "") or "").strip()
            if not bez or bez.lower() in ("none", "nan"):
                continue
            rows.append({
                "bezeichnung": bez,
                "kennzeichen": str(r.get(m.get("kennzeichen"), "") or "").strip()
                               if m.get("kennzeichen") else "",
                "start_km_vorjahr": _safe_int(r.get(m.get("start_km_vorjahr")))
                                    if m.get("start_km_vorjahr") else 0,
                "privat_km_min": _safe_int(r.get(m.get("privat_km_min")))
                                 if m.get("privat_km_min") else 0,
                "privat_km_max": _safe_int(r.get(m.get("privat_km_max")))
                                 if m.get("privat_km_max") else 0,
                "dienstlich_quote": _safe_int(r.get(m.get("dienstlich_quote")), 90)
                                    if m.get("dienstlich_quote") else 90,
            })
    if not rows:
        raise ValueError("Keine Fahrzeuge erkannt – benötigt wird mindestens eine Spalte "
                         "'Bezeichnung' (oder 'Fahrzeug'/'Name').")
    return pd.DataFrame(rows)


def lade_zeitraeume(uploaded_file) -> pd.DataFrame:
    sheets = _lese_datei(uploaded_file)
    rows = []
    for _, df in sheets.items():
        if df.empty:
            continue
        df, m = _zuordnen(df, ZEITRAUM_KANDIDATEN)
        if not all(k in m for k in ("fahrzeug", "von", "bis")):
            continue
        for _, r in df.iterrows():
            fzg = str(r.get(m["fahrzeug"], "") or "").strip()
            von = _parse_date_iso(r.get(m["von"]))
            bis = _parse_date_iso(r.get(m["bis"]))
            if not fzg or fzg.lower() in ("none", "nan") or not von or not bis:
                continue
            rows.append({"fahrzeug": fzg, "von": von, "bis": bis})
    if not rows:
        raise ValueError("Keine Zeiträume erkannt – benötigt werden Spalten "
                         "'Fahrzeug', 'Von', 'Bis'.")
    return pd.DataFrame(rows)


def lade_orte(uploaded_file) -> pd.DataFrame:
    sheets = _lese_datei(uploaded_file)
    rows = []
    for _, df in sheets.items():
        if df.empty:
            continue
        df, m = _zuordnen(df, ORTE_KANDIDATEN)
        if "ort" not in m:
            continue
        for _, r in df.iterrows():
            val = str(r.get(m["ort"], "") or "").strip()
            if val and val.lower() not in ("none", "nan"):
                rows.append({"ort": val})
    if not rows:
        raise ValueError("Keine Orte erkannt – benötigt wird eine Spalte "
                         "'Ort' (oder 'Adresse'/'Ziel').")
    return pd.DataFrame(rows).drop_duplicates(subset=["ort"]).reset_index(drop=True)