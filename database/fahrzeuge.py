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
    """Speichert Fahrzeuge (Delete+Insert) und liefert die frisch geladenen
    Datensätze (mit neuen IDs) zurück – wichtig für die Zeitraum-Zuordnung."""
    try:
        supabase.table("fahrzeuge").delete().eq("username", username).execute()
        df = df.dropna(how='all')
        rows = []
        for _, row in df.iterrows():
            rows.append({
                "username": username,
                "bezeichnung": _clean(row.get("bezeichnung")),
                "kennzeichen": _clean(row.get("kennzeichen")),
                "start_km_vorjahr": _safe_int(row.get("start_km_vorjahr")),
                "privat_km_min": _safe_int(row.get("privat_km_min")),
                "privat_km_max": _safe_int(row.get("privat_km_max")),
                "dienstlich_quote": _safe_int(row.get("dienstlich_quote"), 90),
            })
        rows = [r for r in rows if r["bezeichnung"]]
        if rows:
            try:
                supabase.table("fahrzeuge").insert(rows).execute()
            except Exception as e:
                if "dienstlich_quote" in str(e):
                    fallback = [{k: v for k, v in r.items() if k != "dienstlich_quote"}
                                for r in rows]
                    supabase.table("fahrzeuge").insert(fallback).execute()
                    raise DatabaseError(
                        "Gespeichert, ABER: Spalte 'dienstlich_quote' fehlt in der "
                        "DB-Tabelle 'fahrzeuge' (INTEGER, Default 90) – bitte anlegen."
                    ) from e
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