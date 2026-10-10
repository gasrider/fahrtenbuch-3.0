"""Orte (Kundenstopps, Werkstätten) und deren Distanzen vom Wohnort."""
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


def lade_distanzen(username) -> dict:
    """Liefert {ort: km_einfach} für alle gepflegten Distanzen."""
    try:
        r = (supabase.table("orte_distanz").select("ort, km_einfach")
             .eq("username", username).execute())
        return {row["ort"]: int(row["km_einfach"] or 0) for row in (r.data or [])}
    except Exception as e:
        raise DatabaseError(f"Distanzen laden fehlgeschlagen: {e}") from e


def speichere_distanzen(username, distanzen: dict) -> bool:
    """Überschreibt alle Distanzen. distanzen: {ort: km_einfach}"""
    try:
        supabase.table("orte_distanz").delete().eq("username", username).execute()
        rows = [{"username": username, "ort": str(o).strip(),
                 "km_einfach": int(k or 0)}
                for o, k in distanzen.items() if str(o).strip()]
        for i in range(0, len(rows), 500):
            supabase.table("orte_distanz").insert(rows[i:i + 500]).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"Distanzen speichern fehlgeschlagen: {e}") from e
