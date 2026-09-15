"""Gemeinsame Spaltenkonfiguration für die Fahrten-Editoren (wird von 2 Tabs genutzt)."""
import streamlit as st

from logic.constants import FAHRTEN_COLUMNS


FAHRTEN_COLUMN_CONFIG = {
    "datum": st.column_config.DateColumn("Datum", format="DD.MM.YYYY"),
    "fahrzeug": st.column_config.TextColumn("Fahrzeug", width="small"),
    "route": st.column_config.TextColumn("Reiseweg / Ziel / Zweck", width="large"),
    "abf": st.column_config.TextColumn("Abf.", width="small"),
    "ank": st.column_config.TextColumn("Ank.", width="small"),
    "dauer": st.column_config.TextColumn("Dauer", width="small"),
    "km_d": st.column_config.NumberColumn("km dienstl.", min_value=0, step=1),
    "km_p": st.column_config.NumberColumn("km privat", min_value=0, step=1),
    "abfahrt_km": st.column_config.NumberColumn("KM Abfahrt", min_value=0, step=1),
}


def display_columns():
    return FAHRTEN_COLUMNS