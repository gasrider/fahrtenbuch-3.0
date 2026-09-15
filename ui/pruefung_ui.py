import streamlit as st

from database import DatabaseError
from database.fahrten import load_month, save_month
from database.fahrzeuge import load_fahrzeuge
from logic.validation import scan_for_red_flags
from logic.fahrten import recalc_abfahrt_km
from logic.helpers import _parse_date_iso, _safe_int
from ui.fahrten_spalten import FAHRTEN_COLUMN_CONFIG


def render(username):
    st.subheader("🔍 Plausibilitätsprüfung (Red Flags)")
    st.caption("Findet unplausible Einträge (z. B. unrealistische Geschwindigkeiten, "
               "Zeitreisen, 0-km-Fahrten). Korrekturen macht ihr hier manuell – "
               "der Fahrtenbuch-Inhalt muss immer der Realität entsprechen.")

    c1, c2 = st.columns(2)
    jahr = c1.number_input("Jahr", min_value=2000, max_value=2100,
                           value=st.session_state.get("pruef_jahr", 2024), step=1, key="pruef_jahr")
    monat = c2.selectbox("Monat", range(1, 13), key="pruef_monat")

    try:
        df = load_month(username, jahr, monat)
    except DatabaseError as e:
        st.error(str(e)); return

    if df is None or df.empty:
        st.info("Keine Fahrten für diesen Monat gespeichert.")
        return

    flags = scan_for_red_flags(df)
    if flags:
        st.error(f"{len(flags)} Auffälligkeit(en) gefunden:")
        for f in flags:
            st.markdown(f"- {f}")
    else:
        st.success("Keine Auffälligkeiten gefunden. ✅")

    df = df.copy()
    df["datum"] = pd_to_date(df["datum"])
    cols = ["datum", "fahrzeug", "route", "abf", "ank", "dauer", "km_d", "km_p", "abfahrt_km"]
    edited = st.data_editor(df[[c for c in cols if c in df.columns]],
                            column_config=FAHRTEN_COLUMN_CONFIG,
                            num_rows="dynamic", use_container_width=True,
                            key=f"pruef_editor_{jahr}_{monat}")

    if st.button("💾 Korrekturen speichern"):
        try:
            fahrzeuge = load_fahrzeuge(username)
            clean = edited.copy()
            clean = clean[clean["datum"].notna()]
            name_to_id = {str(r["bezeichnung"]).strip(): _safe_int(r["id"])
                          for _, r in fahrzeuge.iterrows() if pd_notna(r["id"])}
            clean["fahrzeug_id"] = clean["fahrzeug"].map(lambda n: name_to_id.get(str(n).strip()))
            clean = clean[clean["fahrzeug_id"].notna()]
            clean["datum"] = clean["datum"].map(lambda d: _parse_date_iso(d))
            clean = recalc_abfahrt_km(clean, fahrzeuge)
            save_month(username, jahr, monat, clean)
            st.success("Korrekturen gespeichert.")
            st.rerun()
        except DatabaseError as e:
            st.error(str(e))


def pd_to_date(col):
    import pandas as pd
    return pd.to_datetime(col).dt.date


def pd_notna(v):
    import pandas as pd
    return pd.notna(v)