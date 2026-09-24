"""Speichert die Generierungs-Einstellungen PRO JAHR (JSON), damit ein
gespeichertes Jahr mit denselben Einstellungen wieder geöffnet werden kann."""
import json

from config import supabase
from database import DatabaseError


def save_generation_settings(username, jahr, settings: dict) -> bool:
    try:
        supabase.table("generation_settings").upsert({
            "username": username,
            "jahr": int(jahr),
            "settings_json": json.dumps(settings, ensure_ascii=False, default=str),
        }).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"Generierungs-Einstellungen speichern fehlgeschlagen: {e}") from e


def load_generation_settings(username, jahr) -> dict:
    try:
        r = (supabase.table("generation_settings").select("settings_json")
             .eq("username", username).eq("jahr", int(jahr)).execute())
        if r.data:
            return json.loads(r.data[0]["settings_json"])
    except Exception as e:
        raise DatabaseError(f"Generierungs-Einstellungen laden fehlgeschlagen: {e}") from e
    return {}
