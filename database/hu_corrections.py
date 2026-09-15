from config import supabase
from database import DatabaseError
from logic.helpers import _safe_int


def save_hu_corrections(username, corrections_list) -> bool:
    """Überschreibt alle HU-Korrekturen des Users. Einträge:
    {fahrzeug_id, datum, km_at_hu, werkstattort, stopps_vor_hu: [..], stopps_nach_hu: [..]}"""
    try:
        supabase.table("hu_corrections").delete().eq("username", username).execute()
        if not corrections_list:
            return True
        rows = [{
            "username": username,
            "fahrzeug_id": _safe_int(c.get("fahrzeug_id"), default=None),
            "datum": str(c["datum"]) if c.get("datum") else None,
            "km_at_hu": _safe_int(c.get("km_at_hu")),
            "werkstattort": str(c.get("werkstattort", "")).strip(),
            "stopps_vor_hu": ",".join(c.get("stopps_vor_hu", []) or []),
            "stopps_nach_hu": ",".join(c.get("stopps_nach_hu", []) or []),
        } for c in corrections_list]
        for i in range(0, len(rows), 500):
            supabase.table("hu_corrections").insert(rows[i:i + 500]).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"HU-Korrekturen speichern fehlgeschlagen: {e}") from e


def load_hu_raw(username) -> list:
    """Rohdaten (für Bearbeitung/Anhängen neuer Einträge)."""
    try:
        r = supabase.table("hu_corrections").select("*").eq("username", username).execute()
        return r.data or []
    except Exception as e:
        raise DatabaseError(f"HU-Korrekturen laden fehlgeschlagen: {e}") from e


def load_hu_corrections(username, fahrzeuge_df=None) -> list:
    """Aufbereitete Zeilen für die Anzeige (Fahrzeugname aufgelöst)."""
    try:
        raw = load_hu_raw(username)
        id_to_name = {}
        if fahrzeuge_df is not None and not fahrzeuge_df.empty:
            for _, row in fahrzeuge_df.iterrows():
                if pd_notna(row.get('id')) and pd_notna(row.get('bezeichnung')):
                    id_to_name[int(row['id'])] = str(row['bezeichnung']).strip()
        out = []
        for r in raw:
            fid = r.get("fahrzeug_id")
            out.append({
                "Fahrzeug": id_to_name.get(int(fid), "") if fid is not None else "",
                "Datum der HU": r.get("datum"),
                "Kilometerstand bei HU": _safe_int(r.get("km_at_hu")),
                "Werkstattort (Dropdown)": r.get("werkstattort", ""),
                "Kundenstopps vor HU (mehrere möglich)": r.get("stopps_vor_hu", ""),
                "Kundenstopps nach HU (mehrere möglich)": r.get("stopps_nach_hu", ""),
            })
        return out
    except DatabaseError:
        raise


def pd_notna(v):
    import pandas as pd
    return pd.notna(v)