from config import supabase
from database import DatabaseError


def load_orte(username) -> list:
    try:
        r = (supabase.table("orte").select("ort")
             .eq("username", username).order("ort").execute())
        return [row["ort"] for row in (r.data or [])]
    except Exception as e:
        raise DatabaseError(f"Orte laden fehlgeschlagen: {e}") from e


def save_orte(username, orte_list) -> bool:
    try:
        supabase.table("orte").delete().eq("username", username).execute()
        clean = [{"username": username, "ort": str(o).strip()}
                 for o in orte_list if str(o).strip()]
        for i in range(0, len(clean), 500):
            supabase.table("orte").insert(clean[i:i + 500]).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"Orte speichern fehlgeschlagen: {e}") from e