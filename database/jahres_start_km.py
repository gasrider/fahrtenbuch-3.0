"""Jahres-Startkilometer (Anker): Pro Jahr + Fahrzeug wird EINMAL der
Tachostand zum 1.1. gesperrt. Alle Neuberechnungen lesen diesen Anker."""
from config import supabase
from database import DatabaseError
from logic.helpers import _safe_int


def get_start_km_map(username, jahr) -> dict:
    try:
        r = (supabase.table("jahres_start_km").select("fahrzeug_id, start_km")
             .eq("username", username).eq("jahr", int(jahr)).execute())
        return {int(row["fahrzeug_id"]): int(row["start_km"]) for row in (r.data or [])}
    except Exception:
        return {}


def set_start_km(username, jahr, km_map: dict) -> bool:
    try:
        supabase.table("jahres_start_km").delete() \
            .eq("username", username).eq("jahr", int(jahr)).execute()
        rows = [{"username": username, "jahr": int(jahr),
                 "fahrzeug_id": int(f), "start_km": int(k)}
                for f, k in km_map.items() if f is not None]
        for i in range(0, len(rows), 500):
            supabase.table("jahres_start_km").insert(rows[i:i + 500]).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"Jahres-Startkm speichern fehlgeschlagen: {e}") from e


def delete_anchor(username, jahr) -> bool:
    try:
        supabase.table("jahres_start_km").delete() \
            .eq("username", username).eq("jahr", int(jahr)).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"Jahres-Startkm loeschen fehlgeschlagen: {e}") from e


def get_or_create_anchor(username, jahr, fahrzeuge_df) -> dict:
    """Liest den Anker. Fehlende Fahrzeuge werden aus 'Start-KM (Vorjahr)'
    der Fahrzeug-Tabelle uebernommen und SOFORT gesperrt."""
    anchor = get_start_km_map(username, jahr)
    fehlend = {}
    if fahrzeuge_df is not None and not fahrzeuge_df.empty:
        for _, fz in fahrzeuge_df.iterrows():
            fid = _safe_int(fz.get('id'), default=None)
            if fid is None:
                continue
            if fid not in anchor:
                fehlend[fid] = _safe_int(fz.get('start_km_vorjahr'))
    if fehlend:
        anchor.update(fehlend)
        try:
            set_start_km(username, jahr, anchor)
        except Exception:
            pass
    return anchor
