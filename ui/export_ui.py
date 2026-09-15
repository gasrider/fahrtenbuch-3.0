import streamlit as st

from database import DatabaseError
from database.fahrten import load_month, load_year
from database.settings import load_settings
from database.fahrzeuge import load_fahrzeuge
from database.hu_corrections import (load_hu_raw, load_hu_corrections, save_hu_corrections)
from pdf.monats_pdf import create_monats_pdf
from pdf.jahres_pdf import create_jahres_pdf


def _render_pdf_export(username):
    st.markdown("### 📄 PDF-Export")
    c1, c2 = st.columns(2)
    jahr = c1.number_input("Jahr", min_value=2000, max_value=2100,
                           value=st.session_state.get("exp_jahr", 2024), step=1, key="exp_jahr")
    monat = c2.selectbox("Monat", range(1, 13), key="exp_monat")

    try:
        settings = load_settings(username)
        fahrzeuge = load_fahrzeuge(username)

        st.markdown("**Monats-PDF**")
        if st.button("Monats-PDF erzeugen"):
            df = load_month(username, jahr, monat)
            if df is None or df.empty:
                st.warning("Keine Daten für diesen Monat.")
            else:
                buf = create_monats_pdf(df, monat, jahr, settings, fahrzeuge)
                st.download_button("⬇️ Download Monats-PDF", data=buf,
                                   file_name=f"Fahrtenbuch_{jahr}_{monat:02d}.pdf",
                                   mime="application/pdf")

        st.markdown("**Jahres-PDF**")
        if st.button("Jahres-PDF erzeugen"):
            year_data = load_year(username, jahr)
            if not year_data:
                st.warning("Keine Daten für dieses Jahr.")
            else:
                gen = {k: {"data": v} for k, v in year_data.items()}
                buf = create_jahres_pdf(gen, jahr, settings, fahrzeuge)
                st.download_button("⬇️ Download Jahres-PDF", data=buf,
                                   file_name=f"Fahrtenbuch_Jahr_{jahr}.pdf",
                                   mime="application/pdf")
    except DatabaseError as e:
        st.error(str(e))


def _render_hu(username):
    st.markdown("### 🔧 HU-Korrekturen")
    try:
        fahrzeuge = load_fahrzeuge(username)
        rows = load_hu_corrections(username, fahrzeuge)
    except DatabaseError as e:
        st.error(str(e)); return

    if rows:
        st.dataframe(rows, use_container_width=True)
    else:
        st.info("Noch keine HU-Korrekturen gespeichert.")

    if fahrzeuge.empty:
        return
    with st.form("hu_form"):
        fzg_names = [str(r["bezeichnung"]) for _, r in fahrzeuge.iterrows()]
        fzg = st.selectbox("Fahrzeug", fzg_names)
        datum = st.date_input("Datum der HU")
        km = st.number_input("Kilometerstand bei HU", min_value=0, step=1)
        werkstatt = st.text_input("Werkstattort")
        stopps_v = st.text_input("Kundenstopps VOR HU (durch Komma getrennt)")
        stopps_n = st.text_input("Kundenstopps NACH HU (durch Komma getrennt)")
        if st.form_submit_button("HU-Eintrag hinzufügen"):
            fid = int(fahrzeuge[fahrzeuge["bezeichnung"] == fzg].iloc[0]["id"])
            try:
                raw = load_hu_raw(username)
                raw.append({
                    "fahrzeug_id": fid,
                    "datum": datum.isoformat(),
                    "km_at_hu": int(km),
                    "werkstattort": werkstatt,
                    "stopps_vor_hu": [s.strip() for s in stopps_v.split(",") if s.strip()],
                    "stopps_nach_hu": [s.strip() for s in stopps_n.split(",") if s.strip()],
                })
                save_hu_corrections(username, raw)
                st.success("HU-Eintrag gespeichert.")
                st.rerun()
            except DatabaseError as e:
                st.error(str(e))


def render(username):
    st.subheader("📄 Export & HU")
    _render_pdf_export(username)
    st.divider()
    _render_hu(username)