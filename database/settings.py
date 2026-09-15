from config import supabase
from database import DatabaseError
from logic.helpers import _safe_int, _safe_float


def save_settings(username, d) -> bool:
    try:
        supabase.table("settings").upsert({
            "username": str(username),
            "name": str(d.get('name', '') or ''),
            "pnr": str(d.get('pnr', '') or ''),
            "wohnort": str(d.get('wohnort', '') or ''),
            "dienstort": str(d.get('dienstort', '') or ''),
            "entfernung": _safe_int(d.get('entfernung')),
            "taggeld_min_stunden": _safe_float(d.get('taggeld_min_stunden'), 5),
            "taggeld_basis": _safe_float(d.get('taggeld_basis'), 10.00),
            "taggeld_stufung": _safe_float(d.get('taggeld_stufung'), 2.50),
            "taggeld_max_betrag": _safe_float(d.get('taggeld_max_betrag'), 30.00),
            "taggeld_max_stunden": _safe_float(d.get('taggeld_max_stunden'), 13),
            "km_geld": _safe_float(d.get('km_geld'), 0.42),
        }).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"Stammdaten speichern fehlgeschlagen: {e}") from e


def load_settings(username) -> dict:
    try:
        r = supabase.table("settings").select("*").eq("username", username).execute()
        return r.data[0] if r.data else {}
    except Exception as e:
        raise DatabaseError(f"Stammdaten laden fehlgeschlagen: {e}") from e