"""Privat-Kilometer verteilen: Jahres-Summe fuer ein Fahrzeug (z. B.
Familienauto) realistisch auf das Jahr verteilen."""
from datetime import date

import pandas as pd
import streamlit as st

from database import DatabaseError
from database.fahrzeuge import load_fahrzeuge
from database.fahrten import load_year, save_month, load_verfuegbare_jahre
from database.jahres_start_km import get_or_create_anchor
from database.jahres_start_km import set_start_km
from logic.helpers import _safe_int
from logic.privat_km import verteile_privat_km


def render(username):
    st.subheader("Privat-Kilometer verteilen")
    st.caption("Fuer Fahrzeuge, deren private Nutzung nicht taeglich erfasst wird "
               "(z. B. Familienauto): Jahres-Summe eingeben, das System verteilt "
               "sie realistisch auf das Jahr - inkl. weniger grosser Fahrten "
               "(Urlaub/Ausfluege) mit mehreren hundert km. Bereits generierte "
               "Privat-KM dieses Fahrzeugs werden ersetzt; HU-Tage bleiben unberuehrt.")
    try:
        fahrzeuge = load_fahrzeuge(username)
    except DatabaseError as e:
        st.error(str(e)); return
    if fahrzeuge.empty:
        st.warning("Zuerst Fahrzeuge anlegen.")
        return

    try:
        jahre = load_verfuegbare_jahre(username)
    except DatabaseError:
        jahre = []
    heute = date.today().year
    optionen = sorted(set(jahre) | set(range(heute - 10, heute + 3)))
    jahr = int(st.selectbox("Jahr", optionen, index=len(optionen) - 1,
                            key="pkm_jahr"))

    fzg_liste = []
    for _, r in fahrzeuge.iterrows():
        if pd.notna(r.get("id")):
            fzg_liste.append((int(r["id"]), str(r["bezeichnung"])))
    sel = st.selectbox("Fahrzeug", fzg_liste,
                       format_func=lambda t: t[1], key="pkm_fzg")
    fid, fzg_name = sel

    try:
        year_data = load_year(username, jahr)
    except DatabaseError as e:
        st.error(str(e)); return

    ist_p = 0
    ist_tage = 0
    if year_data:
        for df in year_data.values():
            if 'fahrzeug_id' not in df.columns or df.empty:
                continue
            d = df[df['fahrzeug_id'] == fid]
            if not d.empty:
                p = pd.to_numeric(d['km_p'], errors='coerce').fillna(0)
                ist_p += _safe_int(p.sum())
                ist_tage += int((p > 0).sum())
        st.info(f"Ist-Zustand {jahr}: **{ist_p:,} km** privat auf {ist_tage} Tagen.")
    else:
        st.warning(f"Fuer {jahr} sind keine Fahrten gespeichert - zuerst generieren.")

    st.markdown("---")
    total_km = st.number_input(
        "Privat-KM gesamt fuer das Jahr", 0, 100000,
        max(ist_p, 5000), 100,
        help="Die reale Jahres-Summe der privaten Kilometer dieses Fahrzeugs.")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Grosse Fahrten (Urlaub/Ausfluege):**")
        anzahl_gross = st.slider("Anzahl", 0, 12, 4, key="pkm_gross_n")
        gross_min = st.number_input("Min km pro grosser Fahrt", 100, 2000, 300, 50)
        gross_max = st.number_input("Max km pro grosser Fahrt", 100, 2000, 800, 50)
    with c2:
        st.markdown("**Normale Tage:**")
        normal_min = st.number_input("Min km pro Tag", 0, 200, 5, 5)
        normal_max = st.number_input("Max km pro Tag", 5, 300, 45, 5)

    gross_min = int(gross_min)
    gross_max = max(int(gross_max), gross_min)

    if st.button("Verteilen und speichern", type="primary",
                 disabled=not year_data or total_km <= 0):
        try:
            anchor = get_or_create_anchor(username, jahr, fahrzeuge)
            with st.spinner("Verteile Privat-Kilometer..."):
                year_data, km_ende, meldungen = verteile_privat_km(
                    year_data, fid, int(total_km), fzg_name,
                    anzahl_gross=anzahl_gross,
                    gross_min=gross_min, gross_max=gross_max,
                    normal_min=int(normal_min), normal_max=int(normal_max),
                    anchor=anchor)
                for m in meldungen:
                    st.write(m)
                for key, dfm in year_data.items():
                    save_month(username, key[0], key[1], dfm)
                set_start_km(username, jahr + 1, km_ende)
            st.success("Privat-KM verteilt und gespeichert! Kilometerkette wurde "
                       "neu aufgebaut.")
        except ValueError as e:
            st.error(f"⚠️ {e}")
        except DatabaseError as e:
            st.error(str(e))
