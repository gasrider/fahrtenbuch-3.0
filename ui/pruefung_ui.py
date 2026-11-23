"""Plausibilitaetspruefung: Red Flags anzeigen + manuelle Korrektur.
Beim Speichern wird die Kilometerkette des GANZEN Jahres ab dem
Jahres-Anker neu aufgebaut (wie im Generator-Tab)."""
from datetime import date

import pandas as pd
import streamlit as st

from database import DatabaseError
from database.fahrten import load_month, load_year, save_month, load_verfuegbare_jahre
from database.fahrzeuge import load_fahrzeuge
from database.jahres_start_km import get_or_create_anchor, set_start_km
from logic.constants import MONATE
from logic.kette import baue_kette_neu
from logic.validation import scan_for_red_flags
from logic.helpers import _parse_date_iso, _safe_int
from ui.fahrten_spalten import FAHRTEN_COLUMN_CONFIG


def render(username):
    st.subheader("🔍 Plausibilitätsprüfung (Red Flags)")
    st.caption("Findet unplausible Einträge (z. B. unrealistische Geschwindigkeiten, "
               "Zeitreisen, 0-km-Fahrten). Korrekturen macht ihr hier manuell – "
               "der Fahrtenbuch-Inhalt muss immer der Realität entsprechen.")

    try:
        jahre = load_verfuegbare_jahre(username)
    except DatabaseError:
        jahre = []
    heute = date.today().year
    optionen = sorted(set(jahre) | {heute})
    standard = max(jahre) if jahre else heute

    c1, c2 = st.columns(2)
    jahr = int(c1.selectbox("Jahr", optionen, index=optionen.index(standard),
                            key="pruef_jahr_sel"))
    monat = int(c2.selectbox("Monat", range(1, 13), format_func=lambda m: MONATE[m - 1],
                             key="pruef_monat"))

    try:
        df = load_month(username, jahr, monat)
    except DatabaseError as e:
        st.error(str(e)); return

    if df is None or df.empty:
        st.info(f"Keine Fahrten für {MONATE[monat - 1]} {jahr} gespeichert.")
        return

    flags = scan_for_red_flags(df)
    if flags:
        st.error(f"{len(flags)} Auffälligkeit(en) gefunden:")
        for f in flags:
            st.markdown(f"- {f}")
    else:
        st.success("Keine Auffälligkeiten gefunden. ✅")

    df = df.copy()
    df["datum"] = pd.to_datetime(df["datum"], errors="coerce").dt.date
    cols = ["datum", "fahrzeug", "route", "abf", "ank", "dauer", "km_d", "km_p", "abfahrt_km"]
    edited = st.data_editor(df[[c for c in cols if c in df.columns]],
                            column_config=FAHRTEN_COLUMN_CONFIG,
                            num_rows="dynamic", use_container_width=True,
                            key=f"pruef_editor_{jahr}_{monat}")
    st.caption("Beim Speichern werden ALLE Kilometerstände des Jahres ab dem "
               "Jahres-Startwert neu berechnet.")

    if st.button("💾 Korrekturen speichern"):
        try:
            fahrzeuge = load_fahrzeuge(username)
            name_to_id = {str(r["bezeichnung"]).strip().lower(): _safe_int(r["id"])
                          for _, r in fahrzeuge.iterrows() if pd.notna(r.get("id"))}
            clean = edited.copy()
            clean = clean[clean["datum"].notna()]
            # Fahrzeug-ID ueber den Namen; Tage ohne Fahrzeug (z. B. 'Keine
            # Fahrt') bleiben erhalten (fahrzeug_id = leer).
            clean["fahrzeug_id"] = clean["fahrzeug"].map(
                lambda n: name_to_id.get(str(n or "").strip().lower()))
            clean["datum"] = clean["datum"].map(_parse_date_iso)
            for c in ("km_d", "km_p"):
                clean[c] = clean[c].map(_safe_int)

            year_data = load_year(username, jahr)
            year_data[(jahr, monat)] = clean
            anchor = get_or_create_anchor(username, jahr, fahrzeuge)
            year_data, km_ende = baue_kette_neu(year_data, anchor)
            for (j, m), dfm in year_data.items():
                save_month(username, j, m, dfm)
            set_start_km(username, jahr + 1, km_ende)
            st.success("Korrekturen gespeichert - Kilometerkette des Jahres neu aufgebaut.")
            st.rerun()
        except DatabaseError as e:
            st.error(str(e))
