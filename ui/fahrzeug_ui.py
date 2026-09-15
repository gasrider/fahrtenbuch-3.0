import streamlit as st
import pandas as pd

from database import DatabaseError
from database.fahrzeuge import load_fahrzeuge, save_fahrzeuge
from database.zeitraeume import load_zeitraeume, save_zeitraeume
from logic.helpers import to_date, _parse_date_iso


def render(username):
    st.subheader("🚗 Fahrzeuge & Nutzungszeiträume")
    try:
        fahrzeuge = load_fahrzeuge(username)
        zeitraeume = load_zeitraeume(username)
    except DatabaseError as e:
        st.error(str(e)); return

    st.markdown("**Fahrzeuge bearbeiten** (Delete+Insert → IDs ändern sich beim Speichern!)")
    edit = st.data_editor(
        fahrzeuge,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "bezeichnung": st.column_config.TextColumn("Bezeichnung"),
            "kennzeichen": st.column_config.TextColumn("Kennzeichen"),
            "start_km_vorjahr": st.column_config.NumberColumn("Start-KM (Vorjahr)", min_value=0, step=1),
            "privat_km_min": st.column_config.NumberColumn("Privat min. KM", min_value=0, step=1),
            "privat_km_max": st.column_config.NumberColumn("Privat max. KM", min_value=0, step=1),
            "dienstlich_quote": st.column_config.NumberColumn("Dienstlich %", min_value=0, max_value=100, step=5),
        },
        num_rows="dynamic", use_container_width=True, key="fzg_editor",
    )
    if st.button("💾 Fahrzeuge speichern", type="primary"):
        try:
            save_fahrzeuge(username, edit)
            st.success("Fahrzeuge gespeichert.")
            st.rerun()
        except DatabaseError as e:
            st.error(str(e))

    st.divider()
    st.markdown("**Nutzungszeiträume** – welches Fahrzeug wird wann gefahren?")
    if fahrzeuge.empty:
        st.info("Zuerst Fahrzeuge anlegen und speichern.")
        return

    zmap = {}
    if not zeitraeume.empty:
        for _, z in zeitraeume.iterrows():
            try:
                zmap[int(z["fahrzeug_id"])] = (to_date(z["von"]), to_date(z["bis"]))
            except (ValueError, TypeError):
                pass

    neue_zeitraeume = []
    for _, fz in fahrzeuge.iterrows():
        fid = int(fz["id"])
        label = f"{fz['bezeichnung']} ({fz['kennzeichen']})"
        with st.expander(f"📅 Zeitraum: {label}"):
            alt = zmap.get(fid, (None, None))
            c1, c2 = st.columns(2)
            von = c1.date_input("Von", value=alt[0], key=f"von_{fid}")
            bis = c2.date_input("Bis", value=alt[1], key=f"bis_{fid}")
            if von and bis:
                neue_zeitraeume.append({"fahrzeug_id": fid, "von": von, "bis": bis})

    if st.button("💾 Zeiträume speichern"):
        try:
            save_zeitraeume(username, pd.DataFrame(neue_zeitraeume))
            st.success("Zeiträume gespeichert.")
        except DatabaseError as e:
            st.error(str(e))