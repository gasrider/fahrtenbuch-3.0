import pandas as pd

from config import supabase
from database import DatabaseError
from logic.helpers import _safe_int
from logic.constants import DEFAULT_VEHICLES_COLUMNS


def _clean(value) -> str:
    if value is None or str(value).strip().lower() in ("", "none", "nan"):
        return ""
    return str(value).strip()


def save_fahrzeuge(username, df) -> pd.DataFrame:
    """Speichert Fahrzeuge OHNE die IDs zu veraendern:
    Vorhandene IDs werden aktualisiert, neue eingefuegt, entfernte geloescht.
    Wichtig, damit die fahrzeug_id in den generierten Fahrten gueltig bleibt!"""
    try:
        alt = supabase.table("fahrzeuge").select("id").eq("username", username).execute()
        alte_ids = {int(r["id"]) for r in (alt.data or []) if r.get("id") is not None}

        behalten = set()
        updates, inserts = [], []
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                bez = _clean(row.get("bezeichnung"))
                if not bez:
                    continue
                clean = {
                    "username": username,
                    "bezeichnung": bez,
                    "kennzeichen": _clean(row.get("kennzeichen")),
                    "start_km_vorjahr": _safe_int(row.get("start_km_vorjahr")),
                    "privat_km_min": _safe_int(row.get("privat_km_min")),
                    "privat_km_max": _safe_int(row.get("privat_km_max")),
                    "dienstlich_quote": _safe_int(row.get("dienstlich_quote"), 90),
                }
                fid_raw = row.get("id")
                fid = None
                if fid_raw is not None and pd.notna(fid_raw):
                    try:
                        fid = int(fid_raw)
                    except (ValueError, TypeError):
                        fid = None
                if fid is not None and fid in alte_ids:
                    updates.append({**clean, "id": fid})
                    behalten.add(fid)
                else:
                    inserts.append(clean)

        for fid in (alte_ids - behalten):
            supabase.table("fahrzeuge").delete().eq("id", fid).eq("username", username).execute()

        for u in updates:
            try:
                supabase.table("fahrzeuge").update(u).eq("id", u["id"]).execute()
            except Exception as e:
                if "dienstlich_quote" in str(e):
                    u.pop("dienstlich_quote", None)
                    supabase.table("fahrzeuge").update(u).eq("id", u["id"]).execute()
                else:
                    raise
        if inserts:
            try:
                supabase.table("fahrzeuge").insert(inserts).execute()
            except Exception as e:
                if "dienstlich_quote" in str(e):
                    fallback = [{k: v for k, v in r.items() if k != "dienstlich_quote"}
                                for r in inserts]
                    supabase.table("fahrzeuge").insert(fallback).execute()
                    raise DatabaseError(
                        "Gespeichert, ABER: Spalte 'dienstlich_quote' fehlt in der "
                        "DB (INTEGER, Default 90) - bitte anlegen.") from e
                raise
        return load_fahrzeuge(username)
    except DatabaseError:
        raise
    except Exception as e:
        raise DatabaseError(f"Fahrzeuge speichern fehlgeschlagen: {e}") from e


def load_fahrzeuge(username) -> pd.DataFrame:
    try:
        r = (supabase.table("fahrzeuge").select("*")
             .eq("username", username).order("id").execute())
        if r.data:
            df = pd.DataFrame(r.data)
            if "dienstlich_quote" not in df.columns:
                df["dienstlich_quote"] = 90
            return df
    except Exception as e:
        raise DatabaseError(f"Fahrzeuge laden fehlgeschlagen: {e}") from e
    return pd.DataFrame(columns=DEFAULT_VEHICLES_COLUMNS)
