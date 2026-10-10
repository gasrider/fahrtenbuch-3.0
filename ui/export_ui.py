"""PDF-Export mit Jahres-Auswahl (automatisch das letzte Jahr mit Daten)."""
from datetime import date

import streamlit as st

from database import DatabaseError
from database.fahrten import load_month, load_year, load_verfuegbare_jahre
from database.settings import load_settings
from database.fahrzeuge import load_fahrzeuge
from logic.constants import MONATE
from pdf.monats_pdf import create_monats_pdf
from pdf.jahres_pdf import create_jahres_pdf
from ui.hu_ui import render as render_hu


def _zeige_pdf(username):
    st.markdown("### PDF-Export")
    try:
        jahre = load_verfuegbare_jahre(username)
    except DatabaseError:
        jahre = []
    heute = date.today().year
    optionen = sorted(set(jahre) | {heute, heute - 1})
    if jahre:
        standard = max(jahre)
        index = optionen.index(standard)
    else:
        index = len(optionen) - 1
    c1, c2 = st.columns(2)
    jahr = int(c1.selectbox("Jahr", optionen, index=index))
    monat = int(c2.selectbox("Monat", range(1, 13),
                             format_func=lambda m: MONATE[m - 1]))
    if jahre:
        st.caption(f"Gefundene Jahre mit Fahrten: {', '.join(map(str, jahre))}")
    try:
        settings = load_settings(username)
        fahrzeuge = load_fahrzeuge(username)

        st.markdown("**Monats-PDF**")
        if st.button("Monats-PDF erzeugen"):
            df = load_month(username, jahr, monat)
            if df is None or df.empty:
                st.warning(f"Keine Fahrten fuer {MONATE[monat - 1]} {jahr} gespeichert. "
                           "Jahr wechseln oder im Generator-Tab generieren.")
            else:
                buf = create_monats_pdf(df, monat, jahr, settings, fahrzeuge)
                st.download_button(
                    f"Download PDF {MONATE[monat - 1]} {jahr}", data=buf,
                    file_name=f"Fahrtenbuch_{jahr}_{monat:02d}.pdf",
                    mime="application/pdf")

        st.markdown("**Jahres-PDF**")
        if st.button("Jahres-PDF erzeugen"):
            year_data = load_year(username, jahr)
            if not year_data:
                st.warning(f"Keine Fahrten im Jahr {jahr} gespeichert.")
            else:
                gen = {k: {"data": v} for k, v in year_data.items()}
                buf = create_jahres_pdf(gen, jahr, settings, fahrzeuge)
                st.download_button(f"Download Jahres-PDF {jahr}", data=buf,
                                   file_name=f"Fahrtenbuch_Jahr_{jahr}.pdf",
                                   mime="application/pdf")
    except DatabaseError as e:
        st.error(str(e))


def render(username):
    st.subheader("Export & HU")
    _zeige_pdf(username)
    st.divider()
    render_hu(username)
