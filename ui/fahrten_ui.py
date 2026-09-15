"""Generator-Tab: Stammdaten-Slider, Urlaubswochen, Uploads, Keywords, Generator,
Fahrten bearbeiten, Einzelfahrt hinzufügen, kompakten PDF-Export."""
import calendar
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from database import DatabaseError
from database.settings import load_settings
from database.fahrzeuge import load_fahrzeuge, save_fahrzeuge, update_start_km
from database.zeitraeume import load_zeitraeume, save_zeitraeume
from database.fahrten import save_month, load_month
from logic.generator import generiere_monate, urlaubs_tage
from logic.validation import scan_for_red_flags
from logic.excel_import import process_fahrzeuge, process_zeitraeume, lade_keywords, keywords_aus_text
from logic.helpers import _safe_int, _safe_dauer_min, dauer_string
from pdf.monats_pdf import create_monats_pdf
from logic.constants import MONATE

DEFAULT_KEYWORD_TEXT = ("Straßwalchen:Büro\nOberhofen am Irrsee:KB\nStraßwalchen:Schaden,Angebot\n"
    "Mondsee:Antrag,KFZ\nNeumarkt:Angebot,KFZ\nHenndorf:Angebot,KB\nZell am "
    "Moos:KB,Schaden\nKöstendorf:Angebot,KB\nFrankenmarkt:Angebot,KFZ\nEugendorf:KFZ,Angebot\n"
    "Mattighofen:KFZ,Angebot\nObertrum:KFZ\nSeekirchen:Angebot,KB\nLochen:KB,Angebot\n"
    "Friedburg:Angebot,KB\nVöcklamarkt:KFZ,Angebot\nSt. Georgen:Angebot,Schaden\nSt. "
    "Gilgen:Angebot\nUnterach:KB\nOberwang:Angebot\nKirchberg:Antrag,KB\nFornach:Angebot\n"
    "Salzburg:Schaden,Angebot\nMunderfing:KB\nSeeham:KB\nHof bei Salzburg:KFZ,Lamprechtshausen:"
    "Schaden\nOberndorf:Angebot,KB\nHallwang:Angebot,KB\nSchachen:Antrag\nVöcklabruck:Angebot\n"
    "Vöcklabruck:Angebot")


def _init_session():
    st.session_state.setdefault("generated_months_data", {})
    st.session_state.setdefault("fahrten_df", None)
    st.session_state.setdefault("aktuelles_jahr", date.today().year)
    st.session_state.setdefault("aktueller_monat", date.today().month)
    st.session_state.setdefault("show_add_form", False)
    st.session_state.setdefault("fzg_nonce", 0)


def render(username):
    _init_session()
    try:
        user_info = load_settings(username)
        fahrzeuge_df = load_fahrzeuge(username)
        zeitraeume_df = load_zeitraeume(username)
    except DatabaseError as e:
        st.error(str(e)); return

    st.subheader("⚙️ Eckdaten & Keywords für die Generierung")

    # ---- Urlaubswochen ----
    with st.expander("🏖️ Urlaubswochen (optional)"):
        st.markdown("An diesen Tagen werden keine Fahrten generiert.")
        colU1, colU2, colU3 = st.columns(3)
        with colU1:
            anzahl_wochen = st.slider("Anzahl der Urlaubswochen", 0, 4, 0)
        with colU2:
            verteilung = st.selectbox("Verteilung", ["1x4 Wochen", "2x2 Wochen", "4x1 Woche"],
                                      disabled=anzahl_wochen == 0)
        with colU3:
            start_w = st.date_input("Start der 1. Urlaubswoche", value=date(date.today().year, 4, 1),
                                    disabled=anzahl_wochen == 0)
        urlaub_fahrzeug = ""; urlaub_km_min, urlaub_km_max = 30, 80
        if anzahl_wochen > 0:
            st.markdown("**Private Kilometer im Urlaub:**")
            colU4, colU5, colU6 = st.columns(3)
            with colU4:
                fzg_namen = [b for b in fahrzeuge_df.get('bezeichnung', pd.Series(dtype=str)).dropna().tolist()
                             if str(b).strip() and str(b).strip().lower() not in ('none', 'nan')] \
                    if not fahrzeuge_df.empty else []
                urlaub_fahrzeug = st.selectbox("Fahrzeug für private Urlaubs-KM", fzg_namen,
                                               disabled=not fzg_namen)
            with colU5:
                urlaub_km_min = st.number_input("Private KM pro Urlaubstag (Min)", 0, 500, 30, 5)
            with colU6:
                urlaub_km_max = st.number_input("Private KM pro Urlaubstag (Max)", 0, 500, 80, 5)

    st.markdown("**Feinabstimmung für Wochenenden/Feiertage:**")
    colW1, colW2 = st.columns(2)
    with colW1:
        st.slider("Wahrscheinlichkeit für Dienstfahrt am Wochenende/Feiertag (%)", 0, 100, 10,
                  key="wahrscheinlichkeit_dienstfahrt_wochenende")
    with colW2:
        st.info("Restliche Fahrten sind Privatfahrten.")

    colA, colB, colC, colD = st.columns(4)
    with colA:
        modus = st.radio("Generierungs-Modus", ["Einzelner Monat", "Ganzes Jahr"])
        monat_name = st.selectbox("Monat für Generierung", MONATE,
                                  index=date.today().month - 1, disabled=(modus == "Ganzes Jahr"))
        monat = MONATE.index(monat_name) + 1
    with colB:
        st.slider("Ø Fahrten pro Woche", 1, 10, 4)  # wie im Original (ohne Generator-Wirkung)
    with colC:
        st.slider("Ø Privat-KM an Feiertagen/Sonntagen", 10, 500, 50)  # dito
    with colD:
        prob_werktag = st.slider("Wahrscheinlichkeit Dienstfahrt (Werktag %)", 0, 100, 75,
                                 help="Steuert, wie wahrscheinlich eine Dienstfahrt an einem Werktag ist.")
    colKM1, colKM2 = st.columns(2)
    with colKM1:
        target_km_min = st.number_input("Ø Dienst-KM pro Monat (Minimum)", 0, 5000, 1650, 50)
    with colKM2:
        target_km_max = st.number_input("Ø Dienst-KM pro Monat (Maximum)", 0, 5000, 2000, 50)

    st.markdown("**Feinabstimmung für Feiertage/Urlaub:**")
    colF1, colF2 = st.columns(2)
    with colF1:
        prob_feiertag_urlaub = st.slider("Wahrscheinlichkeit für Dienstfahrt an Feiertagen/Urlaubstagen (%)",
                                         0, 100, 5)
    with colF2:
        st.info("Restliche Fahrten sind Privatfahrten.")

    st.markdown("**_ Hauptfahrzeug-Gewichtung:**")
    st.caption("Wie viel Prozent der Fahrten gehen an das Hauptfahrzeug? Rest wird gleichmäßig verteilt.")
    fzg_namen_liste = [str(b).strip() for b in fahrzeuge_df['bezeichnung'].dropna().tolist()
                       if str(b).strip() and str(b).strip().lower() not in ('none', 'nan')] \
        if not fahrzeuge_df.empty else []
    hcol1, hcol2 = st.columns(2)
    with hcol1:
        hauptfahrzeug_name = st.selectbox("Hauptfahrzeug",
                                          ["(keines - gleichmäßig)"] + fzg_namen_liste)
    with hcol2:
        hauptfahrzeug_anteil = st.slider("Anteil Hauptfahrzeug (%)", 0, 100, 70)

    # ---- Uploads & Keywords ----
    st.markdown("---")
    st.subheader("📥 Excel-Dateien hochladen (optional)")
    colU1, colU2, colU3 = st.columns(3)
    fzg_xlsx = colU1.file_uploader("Fahrzeugliste.xlsx", type=["xlsx"], key="upl_fzg")
    zeit_xlsx = colU2.file_uploader("Fahrzeug-Zeiträume.xlsx", type=["xlsx"], key="upl_zeit")
    kw_xlsx = colU3.file_uploader("Keywords.xlsx (optional)", type=["xlsx"], key="upl_kw")

    keyword_text = st.text_area(
        "Oder Orte und Zwecke hier eintragen (Format: 'Ort:Zweck1,Zweck2, ...')",
        value=DEFAULT_KEYWORD_TEXT, height=200)

    if kw_xlsx is not None:
        keywords = lade_keywords(kw_xlsx)
        st.info("✔ Keywords werden aus der hochgeladenen Excel-Datei verwendet.")
    else:
        keywords = keywords_aus_text(keyword_text)

    if fzg_xlsx is not None:
        try:
            fahrzeuge_df = process_fahrzeuge(fzg_xlsx)
        except Exception as e:
            st.error(f"Fahrzeugliste-Import: {e}")
    if zeit_xlsx is not None and not fahrzeuge_df.empty:
        try:
            zeitraeume_df = process_zeitraeume(zeit_xlsx, fahrzeuge_df)
        except Exception as e:
            st.error(f"Zeiträume-Import: {e}")

    # ---- Editoren (wie Original) ----
    st.subheader("✏️ Fahrzeuge & Zeiträume (editierbar)")
    colE1, colE2 = st.columns(2)
    with colE1:
        fahrzeuge_edit = st.data_editor(fahrzeuge_df, num_rows="dynamic",
                                        key="fahrzeuge_editor", use_container_width=True)
    with colE2:
        zeitraeume_edit = st.data_editor(zeitraeume_df, num_rows="dynamic",
                                         key="zeiten_editor", use_container_width=True)
    if st.button("💾 Fahrzeuge & Zeiträume speichern"):
        try:
            save_fahrzeuge(username, fahrzeuge_edit)
            save_zeitraeume(username, zeitraeume_edit)
            st.toast("Gespeichert!")
            st.rerun()
        except DatabaseError as e:
            st.error(str(e))

    # ---- Generator ----
    st.markdown("---")
    jahr = st.number_input("Jahr", min_value=2000, max_value=2100,
                           value=date.today().year, step=1)
    keywords_ok = keywords is not None and not keywords.empty
    ready = (not fahrzeuge_df.empty and not zeitraeume_df.empty and keywords_ok)
    if not ready:
        st.warning("Für die Generierung werden Fahrzeuge + Zeiträume + Keywords benötigt.")
    colG1, colG2 = st.columns([1, 1])
    gen_text = f"🚀 Fahrten für {'Ganzes Jahr' if modus == 'Ganzes Jahr' else monat_name} {jahr} generieren"
    gen_btn = colG1.button(gen_text, type="primary", disabled=not ready)
    clear_btn = colG2.button("🗑️ Alle generierten Daten löschen")

    if clear_btn:
        st.session_state["fahrten_df"] = None
        st.session_state["generated_months_data"] = {}
        st.rerun()

    if gen_btn:
        vacation_days = urlaubs_tage(int(jahr), anzahl_wochen,
                                     verteilung if anzahl_wochen > 0 else "1x4 Wochen",
                                     start_w if anzahl_wochen > 0 else date(int(jahr), 4, 1))
        params = {
            "prob_werktag": prob_werktag,
            "prob_feiertag_urlaub": prob_feiertag_urlaub,
            "vacation_days": vacation_days,
            "urlaub_fahrzeug_name": urlaub_fahrzeug,
            "urlaub_km_min": urlaub_km_min, "urlaub_km_max": urlaub_km_max,
            "target_km_min": target_km_min, "target_km_max": target_km_max,
            "hauptfahrzeug_name": "" if hauptfahrzeug_name.startswith("(keines") else hauptfahrzeug_name,
            "hauptfahrzeug_anteil": hauptfahrzeug_anteil,
        }
        monate_liste = list(range(1, 13)) if modus == "Ganzes Jahr" else [monat]
        progress = st.progress(0, text="Generiere Fahrten…")
        try:
            generated, current_km = generiere_monate(
                int(jahr), monate_liste, user_info, fahrzeuge_df, zeitraeume_df, keywords, params)
            for i, mk in enumerate(monate_liste):
                progress.progress((i + 1) / len(monate_liste),
                                  text=f"Generiere Monat {mk} von {monate_liste[-1]}…")
            progress.empty()
            st.session_state["generated_months_data"] = generated
            st.session_state["aktuelles_jahr"] = int(jahr)
            st.session_state["aktueller_monat"] = monate_liste[-1]
            st.session_state["fahrten_df"] = generated[(int(jahr), monate_liste[-1])]["data"]

            # Endkilometer anzeigen + als start_km_vorjahr speichern (wie Original)
            lines = []
            for _, fz in fahrzeuge_df.iterrows():
                fz_id = _safe_int(fz['id']) if pd.notna(fz.get('id')) else None
                if fz_id is not None and fz_id in current_km:
                    lines.append(f"• {fz.get('bezeichnung', '?')}: **{int(current_km[fz_id]):,} km**")
            if lines:
                st.info("🚗 **Endkilometerstand pro Fahrzeug (Zeitraum-Ende):**\n" + "\n".join(lines))
                try:
                    update_start_km(username, current_km)
                    st.toast("Endkilometer als Startkilometer gespeichert!")
                except DatabaseError as e:
                    st.warning(f"Endkilometer konnten nicht gespeichert werden: {e}")
            try:
                for key, data in generated.items():
                    save_month(username, key[0], key[1], data["data"])
                st.toast("Fahrten in der Cloud gespeichert!")
            except DatabaseError as e:
                st.error(str(e))
            st.success(f"Fahrten für {len(monate_liste)} Monat(e) generiert.")
        except ValueError as e:
            st.error(f"⚠️ {e}")

    # ---- Plausibilität, Bearbeitung, Einzelfahrt, PDF ----
    df = st.session_state.get("fahrten_df")
    if df is not None:
        jahr_akt = st.session_state["aktuelles_jahr"]
        monat_akt = st.session_state["aktueller_monat"]
        red_flags = scan_for_red_flags(df)
        if red_flags:
            st.error("⚠️ Plausibilitätsprüfung fehlgeschlagen! Bitte korrigiere folgende Fehler "
                     "im Fahrtenbuch, bevor du das PDF exportierst:")
            for flag in red_flags:
                st.warning(flag)
            st.markdown("---")

        st.subheader("✏️ Fahrten anpassen & manuell hinzufügen")
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True,
                                   key="edit_fahrten_editor")
        col_save, col_add = st.columns([1, 1])
        with col_save:
            if st.button("💾 Änderungen für diesen Monat in der Cloud speichern"):
                try:
                    fixed = edited_df.copy()
                    fixed["datum"] = pd.to_datetime(fixed["datum"]).dt.date.astype(str)
                    save_month(username, jahr_akt, monat_akt, fixed)
                    st.session_state["generated_months_data"][(jahr_akt, monat_akt)]["data"] = fixed
                    st.session_state["fahrten_df"] = fixed
                    st.toast("Änderungen erfolgreich gespeichert!", icon="✅")
                    st.rerun()
                except DatabaseError as e:
                    st.error(str(e))
        with col_add:
            if st.button("➕ Einzelne Fahrt manuell hinzufügen"):
                st.session_state["show_add_form"] = True

        if st.session_state.get("show_add_form", False):
            with st.form("add_trip_form"):
                st.write("**Neue Fahrt eintragen:**")
                c1, c2, c3 = st.columns(3)
                with c1: new_date = st.date_input("Datum")
                with c2: new_fzg = st.selectbox("Fahrzeug",
                                                fahrzeuge_df['bezeichnung'].tolist() if not fahrzeuge_df.empty else [])
                with c3: new_route = st.text_input("Reiseweg - Ziel - Zweck")
                c4, c5, c6, c7 = st.columns(4)
                with c4: new_km_d = st.number_input("Dienst-KM", 0, 999, 0)
                with c5: new_km_p = st.number_input("Privat-KM", 0, 999, 0)
                with c6: new_abf = st.text_input("Abfahrt (HH:MM)", value="08:00")
                with c7: new_ank = st.text_input("Ankunft (HH:MM)", value="17:00")
                if st.form_submit_button("✓ Fahrt einfügen"):
                    dauer_str = dauer_string(new_abf, new_ank)
                    fz_row = fahrzeuge_df[fahrzeuge_df['bezeichnung'] == new_fzg]
                    fz_id = _safe_int(fz_row['id'].values[0]) if not fz_row.empty else 1
                    km_max = pd.to_numeric(edited_df['abfahrt_km'], errors='coerce').max()
                    last_km = int(km_max) if pd.notna(km_max) else 0
                    new_row = {"datum": new_date, "fahrzeug_id": int(fz_id), "fahrzeug": new_fzg,
                               "route": new_route, "km_d": int(new_km_d), "km_p": int(new_km_p),
                               "abf": new_abf, "ank": new_ank, "dauer": dauer_str,
                               "abfahrt_km": last_km}
                    new_df = pd.concat([edited_df, pd.DataFrame([new_row])], ignore_index=True)
                    new_df = new_df.sort_values(by="datum").reset_index(drop=True)
                    try:
                        n = new_df.copy()
                        n["datum"] = pd.to_datetime(n["datum"]).dt.date.astype(str)
                        save_month(username, jahr_akt, monat_akt, n)
                        st.session_state["generated_months_data"][(jahr_akt, monat_akt)]["data"] = new_df
                        st.session_state["fahrten_df"] = new_df
                        st.session_state["show_add_form"] = False
                        st.rerun()
                    except DatabaseError as e:
                        st.error(str(e))

        st.markdown("---")
        st.subheader("📄 PDF-Export")
        colP1, colP2 = st.columns(2)
        with colP1:
            if st.button(f"📄 Monats-PDF ({MONATE[monat_akt - 1]} {jahr_akt}) erstellen"):
                buf = create_monats_pdf(st.session_state["fahrten_df"], monat_akt, jahr_akt,
                                        user_info, fahrzeuge_df)
                st.download_button(f"⬇️ Download PDF {MONATE[monat_akt - 1]} {jahr_akt}",
                                   data=buf, file_name=f"Fahrtenbuch_{jahr_akt}_{monat_akt:02d}.pdf",
                                   mime="application/pdf")
        with colP2:
            if st.button("📊 Jahresbericht-PDF erstellen"):
                if not st.session_state["generated_months_data"]:
                    st.warning("Noch keine Monatsdaten für den Jahresbericht vorhanden.")
                else:
                    from pdf.jahres_pdf import create_jahres_pdf
                    buf = create_jahres_pdf(st.session_state["generated_months_data"], jahr_akt,
                                            user_info, fahrzeuge_df)
                    st.download_button(f"⬇️ Download Jahresbericht {jahr_akt}", data=buf,
                                       file_name=f"Fahrtenbuch_Jahresuebersicht_{jahr_akt}.pdf",
                                       mime="application/pdf")