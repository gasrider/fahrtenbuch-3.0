"""Excel-Import exakt nach Original: process_fahrzeuge (inkl. Endkilometer-Erkennung),
process_zeitraeume (Fahrzeug-Zuordnung über Kennzeichen ODER Bezeichnung), Keywords."""
import pandas as pd

from logic.helpers import normalize_df_cols, coalesce, drop_empty_rows, _safe_int


def process_fahrzeuge(file) -> pd.DataFrame:
    df = normalize_df_cols(pd.read_excel(file))
    df = coalesce(df, ["id", "fahrzeug_id", "id"], "id")
    df = coalesce(df, ["bezeichnung", "fahrzeug", "name", "modell"], "bezeichnung")
    df = coalesce(df, ["kennzeichen", "kennz", "kennzeichen"], "kennzeichen")

    # Endkilometer-Spalten erkennen (endkilometer_YYYY, endkm_YYYY, endkm, kilometerstand_ende …)
    _endkm_col = None
    for c in df.columns:
        cl = str(c).lower()
        if (cl.startswith("endkilometer") or cl.startswith("endkm")
                or cl.startswith("kilometerstand_ende") or cl.startswith("km_stand_ende")):
            _endkm_col = c
            break
    _startkm_candidates = ["start_km_vorjahr", "startkmvorjahr", "start_km", "startkm",
                           "vorjahr_km", "start_km_jahr"]
    df = coalesce(df, _startkm_candidates, "start_km_vorjahr")
    if "start_km_vorjahr" not in df.columns:
        df["start_km_vorjahr"] = 0
    if _endkm_col and _endkm_col in df.columns:
        df["start_km_vorjahr"] = pd.to_numeric(df["start_km_vorjahr"], errors="coerce").fillna(0)
        df["_endkm_vals"] = pd.to_numeric(df[_endkm_col], errors="coerce").fillna(0)
        # Nur überschreiben, wo start_km_vorjahr 0/leer ist
        df["start_km_vorjahr"] = df["start_km_vorjahr"].where(df["start_km_vorjahr"] != 0,
                                                              df["_endkm_vals"])
        df.drop(columns=["_endkm_vals"], inplace=True, errors="ignore")

    df = coalesce(df, ["privat_km_min", "privatkmmmin", "min_privat_km", "privatkmin"], "privat_km_min")
    df = coalesce(df, ["privat_km_max", "privatkmmmax", "max_privat_km", "privatkmax"], "privat_km_max")
    df = coalesce(df, ["dienstlich_quote", "dienstlichquote", "dienstl_quote", "nutzungsprofil"],
                  "dienstlich_quote")
    if "privat_km_min" not in df.columns:
        df["privat_km_min"] = 5
    if "privat_km_max" not in df.columns:
        df["privat_km_max"] = 20
    if "dienstlich_quote" not in df.columns:
        df["dienstlich_quote"] = 90

    df["id"] = pd.to_numeric(df["id"], errors="coerce").astype("Int64")
    df["start_km_vorjahr"] = pd.to_numeric(df["start_km_vorjahr"], errors="coerce").fillna(0).astype(int)
    df["privat_km_min"] = pd.to_numeric(df["privat_km_min"], errors="coerce").fillna(5).astype(int)
    df["privat_km_max"] = pd.to_numeric(df["privat_km_max"], errors="coerce").fillna(20).astype(int)
    df["dienstlich_quote"] = pd.to_numeric(df["dienstlich_quote"], errors="coerce").fillna(90).astype(int)
    return df


def process_zeitraeume(file, fahrzeuge_df) -> pd.DataFrame:
    raw = pd.read_excel(file)
    raw = drop_empty_rows(raw)
    df = normalize_df_cols(raw)
    df = coalesce(df, ["fahrzeug_id", "id", "kfz_id"], "fahrzeug_id")
    df = coalesce(df, ["kennzeichen", "kennz", "kennzeichen"], "kennzeichen")
    df = coalesce(df, ["bezeichnung", "fahrzeug", "name", "modell"], "bezeichnung")
    df = coalesce(df, ["von", "beginn", "start", "from"], "von")
    df = coalesce(df, ["bis", "ende", "end", "to"], "bis")
    for col in ["von", "bis"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

    if "fahrzeug_id" in df.columns:
        id_coerced = pd.to_numeric(df["fahrzeug_id"], errors="coerce")
        if id_coerced.notna().mean() < 0.5:
            mapped = pd.Series([pd.NA] * len(df), dtype="Int64")
            if "kennzeichen" in df.columns and "kennzeichen" in fahrzeuge_df.columns:
                m = df["kennzeichen"].astype(str).str.strip().str.upper()
                fk = fahrzeuge_df.set_index(
                    fahrzeuge_df["kennzeichen"].astype(str).str.strip().str.upper())["id"]
                mapped = m.map(fk).astype("Int64")
            if mapped.isna().any() and "bezeichnung" in df.columns:
                m = df["bezeichnung"].astype(str).str.strip().str.upper()
                fk = fahrzeuge_df.set_index(
                    fahrzeuge_df["bezeichnung"].astype(str).str.strip().str.upper())["id"]
                mapped = mapped.fillna(m.map(fk).astype("Int64"))
            df["fahrzeug_id"] = mapped
        else:
            df["fahrzeug_id"] = id_coerced.astype("Int64")
    else:
        mapped = pd.Series([pd.NA] * len(df), dtype="Int64")
        if "kennzeichen" in df.columns and "kennzeichen" in fahrzeuge_df.columns:
            m = df["kennzeichen"].astype(str).str.strip().str.upper()
            fk = fahrzeuge_df.set_index(
                fahrzeuge_df["kennzeichen"].astype(str).str.strip().str.upper())["id"]
            mapped = m.map(fk).astype("Int64")
        if mapped.isna().any() and "bezeichnung" in df.columns:
            m = df["bezeichnung"].astype(str).str.strip().str.upper()
            fk = fahrzeuge_df.set_index(
                fahrzeuge_df["bezeichnung"].astype(str).str.strip().str.upper())["id"]
            mapped = mapped.fillna(m.map(fk).astype("Int64"))
        df["fahrzeug_id"] = mapped

    keep = [c for c in ["fahrzeug_id", "von", "bis"] if c in df.columns]
    df = df[keep].dropna(subset=["fahrzeug_id", "von", "bis"]).reset_index(drop=True)
    return df


def lade_keywords(file) -> pd.DataFrame:
    df = normalize_df_cols(pd.read_excel(file))
    df = coalesce(df, ["ort", "ziel", "stadt"], "ort")
    df = coalesce(df, ["zweck", "grund"], "zweck")
    if "ort" in df.columns:
        df = df.rename(columns={"ort": "Ort"})
    if "zweck" in df.columns:
        df = df.rename(columns={"zweck": "Zweck"})
    return df[["Ort", "Zweck"]]


def keywords_aus_text(text: str) -> pd.DataFrame:
    kw_list = []
    for line in (text or "").strip().split('\n'):
        parts = line.split(':')
        if len(parts) == 2:
            ort = parts[0].strip()
            zwecke = [z.strip() for z in parts[1].split(',')]
            for z in zwecke:
                kw_list.append({"Ort": ort, "Zweck": z})
    return pd.DataFrame(kw_list, columns=["Ort", "Zweck"])
def lade_orte(file) -> pd.DataFrame:
    """Orte aus Excel/CSV (tolerant: 'Ort', 'Adresse', 'Ziel', 'Kunde', 'Werkstattort')."""
    name = str(getattr(file, "name", "")).lower()
    if name.endswith(".csv"):
        try:
            raw = pd.read_csv(file, sep=None, engine="python")
        except UnicodeDecodeError:
            file.seek(0)
            raw = pd.read_csv(file, sep=None, engine="python", encoding="latin-1")
    else:
        raw = pd.read_excel(file)
    df = normalize_df_cols(raw)
    col = None
    for cand in ["ort", "ortsname", "adresse", "ziel", "kunde", "werkstattort"]:
        if cand in df.columns:
            col = cand
            break
    if col is None:
        for c in df.columns:
            if any(k in c for k in ("ort", "ziel", "kunde")):
                col = c
                break
    if col is None:
        raise ValueError("Keine Ort-Spalte erkannt – benötigt: 'Ort' (oder 'Adresse'/'Ziel').")
    vals = [str(v).strip() for v in df[col].tolist()
            if str(v).strip() and str(v).strip().lower() not in ("none", "nan")]
    return pd.DataFrame({"Ort": list(dict.fromkeys(vals))})