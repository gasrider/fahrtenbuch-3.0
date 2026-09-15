import streamlit as st

from database import DatabaseError
from database.settings import load_settings, save_settings
from logic.taggeld import berechne_taggeld_betrag


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
        entfernung = c1.number_input("Entfernung Wohnung ↔ Arbeitsplatz (km)", 0, 300,
                                     int(s.get("entfernung") or 25))
        km_geld = c2.number_input("Kilometergeld PKW amtlich (EUR)", 0.0, 2.0,
                                  float(s.get("km_geld") or 0.42), 0.01)
        st.markdown("**💶 Finanzielle Eckwerte:**")
        st.caption("Taggeld linear: ab Mindeststunden Basis-Betrag, pro weitere Stunde "
                   "+Stufung, gedeckelt bei Max.")
        t1, t2 = st.columns(2)
        with t1:
            tg_min = st.number_input("Taggeld ab Std. (Mindestdauer)", 1.0, 12.0,
                                     float(s.get("taggeld_min_stunden") or 5), 0.5)
            tg_basis = st.number_input("Taggeld Basis-Betrag (EUR)", 0.0, 50.0,
                                       float(s.get("taggeld_basis") or 10.0), 0.5)
            tg_stufe = st.number_input("Zuschlag pro weitere Stunde (EUR)", 0.0, 20.0,
                                       float(s.get("taggeld_stufung") or 2.5), 0.1)
        with t2:
            tg_max = st.number_input("Taggeld Maximalbetrag (EUR)", 0.0, 100.0,
                                     float(s.get("taggeld_max_betrag") or 30.0), 0.5)
            tg_max_h = st.number_input("Taggeld Max ab Std. (Deckelung)", 1.0, 24.0,
                                       float(s.get("taggeld_max_stunden") or 13), 0.5)
        if st.form_submit_button("💾 Stammdaten speichern"):
            data = {"name": name, "pnr": pnr, "wohnort": wohnort, "dienstort": dienstort,
                    "entfernung": int(entfernung), "km_geld": float(km_geld),
                    "taggeld_min_stunden": float(tg_min), "taggeld_basis": float(tg_basis),
                    "taggeld_stufung": float(tg_stufe), "taggeld_max_betrag": float(tg_max),
                    "taggeld_max_stunden": float(tg_max_h)}
            try:
                save_settings(username, data)
                st.toast("Gespeichert!")
            except DatabaseError as e:
                st.error(str(e))
    # Taggeld-Vorschau (wie Original)
    prev = []
    for h in range(int(tg_min), int(tg_max_stunden := tg_max_h) + 2):
        b = min(tg_basis + (h - tg_min) * tg_stufe, tg_max)
        prev.append(f"**{h}h**={b:.2f}€")
    st.caption("Vorschau: " + " | ".join(prev))