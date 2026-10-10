from config import supabase
from database import DatabaseError
from logic.helpers import _safe_int


def _stopps_string(wert) -> str:
    """Robust: akzeptiert String ODER Liste, liefert immer 'A,B,C' als String."""
    if wert is None:
        return ""
    if isinstance(wert, str):
        return wert.strip()
    if isinstance(wert, (list, tuple)):
        teile = [str(x).strip() for x in wert if str(x).strip()]
        return ",".join(teile)
    return str(wert).strip()


def save_hu_corrections(username, corrections_list) -> bool:
    """Überschreibt ALLE HU-Einträge des Users (Delete + Insert)."""
    try:
        supabase.table("hu_corrections").delete().eq("username", username).execute()
        if not corrections_list:
            return True
        rows = []
        for c in corrections_list:
            rows.append({
                "username": username,
                "fahrzeug_id": _safe_int(c.get("fahrzeug_id"), default=None),
                "datum": str(c["datum"]) if c.get("datum") else None,
                "km_at_hu": _safe_int(c.get("km_at_hu")),
                "werkstattort": str(c.get("werkstattort", "")).strip(),
                "stopps_vor_hu": _stopps_string(c.get("stopps_vor_hu")),
                "stopps_nach_hu": _stopps_string(c.get("stopps_nach_hu")),
            })
        rows = [r for r in rows if r["fahrzeug_id"] is not None]
        for i in range(0, len(rows), 500):
            supabase.table("hu_corrections").insert(rows[i:i + 500]).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"HU-Korrekturen speichern fehlgeschlagen: {e}") from e


def load_hu_raw(username) -> list:
    """Rohdaten: Stopps als String 'A,B,C'."""
    try:
        r = supabase.table("hu_corrections").select("*").eq("username", username).execute()
        return r.data or []
    except Exception as e:
        raise DatabaseError(f"HU-Korrekturen laden fehlgeschlagen: {e}") from e
