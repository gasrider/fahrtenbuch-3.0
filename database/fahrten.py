import pandas as pd

from config import supabase
from database import DatabaseError
from logic.helpers import _safe_int


def _clean_row(username, jahr, monat, row) -> dict:
    return {
        "username": username, "jahr": int(jahr), "monat": int(monat),
        "datum": str(row.get("datum", "")),
        "fahrzeug_id": _safe_int(row.get("fahrzeug_id"), default=None),
        "fahrzeug": str(row.get("fahrzeug", "") or ""),
        "route": str(row.get("route", "") or ""),
        "km_d": _safe_int(row.get("km_d")),
        "km_p": _safe_int(row.get("km_p")),
        "abf": str(row.get("abf", "00:00") or "00:00"),
        "ank": str(row.get("ank", "00:00") or "00:00"),
        "dauer": str(row.get("dauer", "00:00") or "00:00"),
        "abfahrt_km": _safe_int(row.get("abfahrt_km")),
    }


def _insert_batched(rows):
    for i in range(0, len(rows), 500):
        supabase.table("fahrten").insert(rows[i:i + 500]).execute()


def save_month(username, jahr, monat, df) -> bool:
    try:
        supabase.table("fahrten").delete().eq("username", username) \
            .eq("jahr", int(jahr)).eq("monat", int(monat)).execute()
        if df is None or df.empty:
            return True
        rows = [_clean_row(username, jahr, monat, row) for _, row in df.iterrows()]
        _insert_batched(rows)
        return True
    except Exception as e:
        raise DatabaseError(f"Fahrten speichern fehlgeschlagen ({jahr}-{monat}): {e}") from e


def save_year(username, jahr, monate_dict: dict) -> bool:
    """monate_dict: {(jahr, monat): DataFrame}"""
    for (j, m), df in monate_dict.items():
        save_month(username, j, m, df)
    return True


def load_month(username, jahr, monat) -> pd.DataFrame:
    try:
        r = (supabase.table("fahrten").select("*").eq("username", username)
             .eq("jahr", int(jahr)).eq("monat", int(monat)).order("datum").execute())
        if r.data:
            return pd.DataFrame(r.data)
    except Exception as e:
        raise DatabaseError(f"Fahrten laden fehlgeschlagen ({jahr}-{monat}): {e}") from e
    return pd.DataFrame()


def load_year(username, jahr) -> dict:
    """Liefert {(jahr, monat): DataFrame} für alle Monate mit Daten."""
    result = {}
    for monat in range(1, 13):
        df = load_month(username, jahr, monat)
        if not df.empty:
            result[(jahr, monat)] = df
    return result


def load_verfuegbare_jahre(username) -> list:
    """Alle Jahre, für die Fahrten gespeichert sind (für die Jahres-Auswahl)."""
    try:
        r = (supabase.table("fahrten").select("jahr")
             .eq("username", username).execute())
        return sorted({int(row["jahr"]) for row in (r.data or [])})
    except Exception as e:
        raise DatabaseError(f"Verfügbare Jahre laden fehlgeschlagen: {e}") from e


def delete_year(username, jahr) -> bool:
    """Löscht alle Fahrten eines Jahres aus der DB."""
    try:
        supabase.table("fahrten").delete().eq("username", username) \
            .eq("jahr", int(jahr)).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"Jahr {jahr} löschen fehlgeschlagen: {e}") from e
