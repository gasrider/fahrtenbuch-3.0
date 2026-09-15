import pandas as pd

from config import supabase
from database import DatabaseError
from logic.helpers import _safe_int, _parse_date_iso


def save_zeitraeume(username, df) -> bool:
    """df mit Spalten: fahrzeug_id, von, bis (Datum/ISO-String)."""
    try:
        supabase.table("zeitraeume").delete().eq("username", username).execute()
        rows = []
        for _, row in df.iterrows():
            von = _parse_date_iso(row.get("von"))
            bis = _parse_date_iso(row.get("bis"))
            fid = _safe_int(row.get("fahrzeug_id"), default=None)
            if not von or not bis or fid is None:
                continue
            rows.append({"username": username, "fahrzeug_id": fid, "von": von, "bis": bis})
        if rows:
            supabase.table("zeitraeume").insert(rows).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"Zeiträume speichern fehlgeschlagen: {e}") from e


def load_zeitraeume(username) -> pd.DataFrame:
    try:
        r = (supabase.table("zeitraeume").select("fahrzeug_id, von, bis")
             .eq("username", username).execute())
        if r.data:
            return pd.DataFrame(r.data)
    except Exception as e:
        raise DatabaseError(f"Zeiträume laden fehlgeschlagen: {e}") from e
    return pd.DataFrame(columns=["fahrzeug_id", "von", "bis"])