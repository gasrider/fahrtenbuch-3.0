"""Zentrale Konfiguration – liest Zugangsdaten aus Streamlit Secrets (Cloud)
oder Umgebungsvariablen/.env (lokal, optional)."""
import os
from supabase import create_client, Client


def _get_secret(key, fallback=None):
    """Sucht den Wert zuerst in Umgebungsvariablen, dann in Streamlit Secrets."""
    val = os.environ.get(key)
    if val:
        return val
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return fallback


SUPABASE_URL = _get_secret("SUPABASE_URL")
SUPABASE_KEY = _get_secret("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL / SUPABASE_KEY fehlen! "
        "Bitte in den Streamlit Cloud Settings unter 'Secrets' eintragen."
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)