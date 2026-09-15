import streamlit as st

from database import DatabaseError
from database.settings import load_settings, save_settings


def render(username):
    st.subheader("📋 Stammdaten")
    try:
        s = load_settings(username)
    except DatabaseError as e:
        st.error(str(e)); return

    with st.form("stammdaten_form"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name", value=s.get("name", ""))
        pnr = c2.text_input("PNR", value=s.get("pnr", ""))
        wohnort = c1.text_input("Wohnort", value=s.get("wohnort", ""))
        dienstort = c2.text_input("Dienstort", value=s.get("dienstort", ""))
        entfernung = c1.number_input("Entfernung Wohnung–Dienstort (km, einfach)",
                                     min_value=0, value=int(s.get("entfernung") or 0))
        km_geld = c2.number_input("km-Geld Satz (EUR/km)", min_value=0.0, step=0.01,
                                  value=float(s.get("km_geld") or 0.42))
        st.markdown("**Taggeld-Berechnung**")
        t1, t2, t3 = st.columns(3)
        tg_min = t1.number_input("Mindeststunden", 0.0, 24.0, float(s.get("taggeld_min_stunden") or 5), 0.5)
        tg_basis = t2.number_input("Grundbetrag (EUR)", 0.0, 100.0, float(s.get("taggeld_basis") or 10.0), 0.5)
        tg_stufe = t3.number_input("Zuschlag pro Stunde (EUR)", 0.0, 20.0, float(s.get("taggeld_stufung") or 2.5), 0.25)
        t4, t5, _ = st.columns(3)
        tg_max = t4.number_input("Höchstbetrag (EUR)", 0.0, 100.0, float(s.get("taggeld_max_betrag") or 30.0), 0.5)
        tg_max_h = t5.number_input("Ab diesen Stunden: Höchstbetrag", 0.0, 24.0, float(s.get("taggeld_max_stunden") or 13), 0.5)

        if st.form_submit_button("💾 Stammdaten speichern", type="primary"):
            data = {"name": name, "pnr": pnr, "wohnort": wohnort, "dienstort": dienstort,
                    "entfernung": int(entfernung), "km_geld": float(km_geld),
                    "taggeld_min_stunden": float(tg_min), "taggeld_basis": float(tg_basis),
                    "taggeld_stufung": float(tg_stufe), "taggeld_max_betrag": float(tg_max),
                    "taggeld_max_stunden": float(tg_max_h)}
            try:
                save_settings(username, data)
                st.success("Stammdaten gespeichert!")
            except DatabaseError as e:
                st.error(str(e))