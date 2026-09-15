from config import supabase
from database import DatabaseError


def load_system_config() -> dict:
    try:
        r = supabase.table("system_config").select("*").eq("id", 1).execute()
        if r.data:
            return r.data[0]
    except Exception:
        pass
    return {}


def save_system_config(config_data: dict) -> bool:
    try:
        config_data["id"] = 1
        supabase.table("system_config").upsert(config_data).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"Systemkonfiguration speichern fehlgeschlagen: {e}") from e