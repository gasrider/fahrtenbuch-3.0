"""Generator-Tab: Uploads, Eckdaten, Editoren, Generierung MIT automatischer
Fahrzeiten-Anpassung + automatischer Plausibilitätsprüfung aller Monate,
Bearbeitung (mit Kilometer-Neuberechnung), PDF-Export."""
from datetime import date

import pandas as pd
import streamlit as st

from database import DatabaseError
from database.settings import load_settings
from database.fahrzeuge import load_fahrzeuge, save_fahrzeuge, update_start_km
from database.zeitraeume import load_zeitraeume, save_zeitraeume
from database.fahrten import save_month, load_year
from logic.generator import generiere_monate, urlaubs_tage
from logic.validation import (scan_for_red_flags, korrigiere_geschwindigkeiten_generated,
                              pruefe_alle_monate)
from logic.excel_import import (process_fahrzeuge, process_zeitraeume,
                                lade_keywords, keywords_aus_text)
from logic.helpers import _safe_int, dauer_string
from pdf.monats_pdf import create_monats_pdf
from pdf.jahres_pdf import create_jahres_pdf
from logic.constants import MONATE

DEFAULT_KEYWORD_TEXT = ("Straßwalchen:Büro\nOberhofen am Irrsee:KB\nStraßwalchen:Schaden,Angebot\n"
    "Mondsee:Antrag,KFZ\nNeumarkt:Angebot,KFZ\nHenndorf:Angebot,KB\nZell am "
    "Moos:KB,Schaden\nKöstendorf:Angebot,KB\nFrankenmarkt:Angebot,KFZ\nEugendorf:KFZ,Angebot\n"
    "Mattighofen:KFZ,Angebot\nObertrum:KFZ\nSeekirchen:Angebot,KB\nLochen:KB,Angebot\n"
    "Friedburg:Angebot,KB\nVöcklamarkt:KFZ,Angebot\nSt. Georgen:Angebot,Schaden\nSt. "
    "Gilgen:Angebot\nUnterach:KB\nOberwang:Angebot\nKirchberg:Antrag,KB\nFornach:Angebot\n"
    "Salzburg:Schaden,Angebot\nMunderfing:KB\nSeeham:KB\nHof bei Salzburg:KFZ\nLamprechtshausen:"
    "Schaden\nOberndorf:Angebot,KB\nHallwang:Angebot,KB\nSchachen:Antrag\nVöcklabruck:Angebot")


def _init_session():
    st.session_state.setdefault("generated_months_data", {})
    st.session_state.setdefault("fahrten_df", None)
    st.session_state.setdefault("aktuelles_jahr", date.today().year)
    st.session_state.setdefault("aktueller_monat", date.today().month)
    st.session_state.setdefault("show_add_form", False)


def _fzg_namen(fahrzeuge_df):
    if fahrzeuge_df is None or fahrzeuge_df.empty or "bezeichnung" not in fahrzeuge_df.columns:
        return []
    return [str(b).strip() for b in fahrzeuge_df["bezeichnung"].dropna().tolist()
            if str(b).strip() and str(b).strip().lower() not in ("none", "nan")]


def _zeige_plausibilitaet(flags_map, monate_gesamt):
    """Kompakte Ampel-Anzeige der automatischen Prüfung."""
    if not flags_map:
        st.success(f"✅ Automatische Plausibilitätsprüfung: {monate_gesamt} Monat(e) geprüft – "
                   "keine Auffälligkeiten. Fahrtenbuch ist konsistent.")
        return
    total = sum(len(v) for v in flags_map.values())
    st.warning(f"⚠️ Plausibilitätsprüfung: {total} Auffälligkeit(en) in {len(flags_map)} "
               f"von {monate_gesamt} Monat(en) – bitte unten im Editor korrigieren "
               "(Kilometer UND Fahrzeiten im selben Zug anpassen):")
    for key in sorted(flags_map.keys()):
        with st.expander(f"📌 {MONATE[key[1] - 1]} {key[0]}: {len(flags_map[key])} Auffälligkeit(en)"):
            for f in flags_map[key]:
                st.markdown(f"- {f}")


def _jahr_recalc_und_speichern(username, jahr, edited_monat_df, monat_key, fahrzeuge_df):
    """Lädt alle Monate des Jahres, setzt den bearbeiteten Monat ein und rechnet
    ALLE abfahrt_km chronologisch neu (inkl. Jahres-Anfang/-Ende)."""
    year_data = load_year(username, jahr)
    edited = edited_monat_df.copy()
    edited["datum"] = pd.to_datetime(edited["datum"]).dt.date.astype(str)
    year_data[monat_key] = edited

    km = {}
    for _, fz in fahrzeuge_df.iterrows():
        fz_id = _safe_int(fz.get('id'), default=None)
        if fz_id is None:
            continue
        ende = _safe_int(fz.get('start_km_vorjahr'))
        total = 0
        for (j, m), dfm in year_data.items():
            d = dfm[dfm["fahrzeug_id"] == fz_id]
            if not d.empty:
                total += _safe_int(pd.to_numeric(d["km_d"], errors="coerce").fillna(0).sum()) \
                       + _safe_int(pd.to_numeric(d["km_p"], errors="coerce").fillna(0).sum())
        km[fz_id] = ende - total

    for key in sorted(year_data.keys()):
        dfm = year_data[key].copy().sort_values("datum").reset_index(drop=True)
        rows = []
        for _, row in dfm.iterrows():
            r = row.to_dict()
            fz = r.get("fahrzeug_id")
            if fz is not None and not pd.isna(fz):
                fz = int(fz)
                r["abfahrt_km"] = km.get(fz, 0)
                km[fz] = km.get(fz, 0) + _safe_int(r.get("km_d")) + _safe_int(r.get("km_p"))
            rows.append(r)
        year_data[key] = pd.DataFrame(rows)

    for key, dfm in year_data.items():
        save_month(username, key[0], key[1], dfm)
    try:
        update_start_km(username, km)
    except DatabaseError:
        pass
    return year_data


def render(username):
    _init_session()
    try:
        user_info = load_settings(username)
        fahrzeuge_df = load_fahrzeuge(username)
        zeitraeume_df = load_zeitraeume(username)
    except DatabaseError as e:
        st.error(str(e)); return

    # ========== 1) UPLOADS & KEYWORDS ==========
    st.subheader("📥 Excel-Dateien hochladen (optional)")
    colU1, colU2, colU3 = st.columns(3)
    fzg_xlsx = colU1.file_uploader("Fahrzeugliste.xlsx", type=["xlsx"], key="upl_fzg")
    zeit_xlsx = colU2.file_uploader("Fahrzeug-Zeiträume.xlsx", type=["xlsx"], key="upl_zeit")
    kw_xlsx = colU3.file_uploader("Keywords.xlsx (optional)", type=["xlsx"], key="upl_kw")

    import_hinweis = []
    if fzg_xlsx is not None:
        try:
            fahrzeuge_df = process_fahrzeuge(fzg_xlsx)
            import_hinweis.append(f"Fahrzeuge aus Excel geladen ({len(fahrzeuge_df)} Zeilen) – "
                                  "noch NICHT gespeichert, bitte unten auf 💾 Speichern klicken!")
        except Exception as e:
            st.error(f"Fahrzeugliste-Import: {e}")
    if zeit_xlsx is not None and not fahrzeuge_df.empty:
        try:
            zeitraeume_df = process_zeitraeume(zeit_xlsx, fahrzeuge_df)
            import_hinweis.append("Zeiträume aus Excel geladen – noch NICHT gespeichert, "
                                  "bitte unten auf 💾 Speichern klicken!")
        except Exception as e:
            st.error(f"Zeiträume-Import: {e}")
    if import_hinweis:
        st.warning("⚠️ " + " | ".join(import_hinweis))

    if kw_xlsx is not None:
        keywords = lade_keywords(kw_xlsx)
        st.info("✔ Keywords werden aus der hochgeladenen Excel-Datei verwendet.")
    else:
        keyword_text = st.text_area(
            "Oder Orte und Zwecke hier eintragen (Format: 'Ort:Zweck1,Zweck2, ...')",
            value=DEFAULT_KEYWORD_TEXT, height=200)
        keywords = keywords_aus_text(keyword_text)

    # ========== 2) ECKDATEN ==========
    st.markdown("---")
    st.subheader("⚙️ Eckdaten & Keywords für die Generierung")

    with st.expander("🏖️ Urlaubswochen (optional)"):
        st.markdown("An diesen Tagen werden keine Dienstfahrten generiert.")
        u1, u2, u3 = st.columns(3)
        with u1:
            anzahl_wochen = st.slider("Anzahl der Urlaubswochen", 0, 4, 0)
        with u2:
            verteilung = st.selectbox("Verteilung", ["1x4 Wochen", "2x2 Wochen", "4x1 Woche"],
                                      disabled=anzahl_wochen == 0)
        with u3:
            start_w = st.date_input("Start der 1. Urlaubswoche",
                                    value=date(date.today().year, 4, 1),
                                    disabled=anzahl_wochen == 0)
        urlaub_fahrzeug, urlaub_km_min, urlaub_km_max = "", 30, 80
        if anzahl_wochen > 0:
            fzg_namen = _fzg_namen(fahrzeuge_df)
            if not fzg_namen:
                st.warning("Keine Fahrzeuge vorhanden – zuerst Fahrzeuge anlegen/speichern.")
            st.markdown("**Private Kilometer im Urlaub:**")
            u4, u5, u6 = st.columns(3)
            with u4:
                urlaub_fahrzeug = st.selectbox("Fahrzeug für private Urlaubs-KM", fzg_namen,
                                               disabled=not fzg_namen)
            with u5:
                urlaub_km_min = st.number_input("Private KM pro Urlaubstag (Min)", 0, 500, 30, 5)
            with u6:
                urlaub_km_max = st.number_input("Private KM pro Urlaubstag (Max)", 0, 500, 80, 5)

    st.markdown("**Feinabstimmung für Wochenenden/Feiertage:**")
    w1, w2 = st.columns(2)
    with w1:
        st.slider("Wahrscheinlichkeit für Dienstfahrt am Wochenende/Feiertag (%)", 0, 100, 10)
    with w2:
        st.info("Restliche Fahrten sind Privatfahrten.")

    colA, colB, colC, colD = st.columns(4)
    with colA:
        modus = st.radio("Generierungs-Modus", ["Einzelner Monat", "Ganzes Jahr"])
        monat_name = st.selectbox("Monat für Generierung", MONATE,
                                  index=date.today().month - 1, disabled=(modus == "Ganzes Jahr"))
        monat = MONATE.index(monat_name) + 1
    with colB:
        st.slider("Ø Fahrten pro Woche", 1, 10, 4)
    with colC:
        st.slider("Ø Privat-KM an Feiertagen/Sonntagen", 10, 500, 50)
    with colD:
        prob_werktag = st.slider("Wahrscheinlichkeit Dienstfahrt (Werktag %)", 0, 100, 75,
                                 help="Steuert die Anzahl der Stopps (Fahrtlänge).")
    colKM1, colKM2 = st.columns(2)
    with colKM1:
        target_km_min = st.number_input("Ø Dienst-KM pro Monat (Minimum)", 0, 5000, 1650, 50)
    with colKM2:
        target_km_max = st.number_input("Ø Dienst-KM pro Monat (Maximum)", 0, 5000, 2000, 50)

    st.markdown("**Feinabstimmung für Feiertage/Urlaub:**")
    f1, f2 = st.columns(2)
    with f1:
        prob_feiertag_urlaub = st.slider(
            "Wahrscheinlichkeit für Dienstfahrt an Feiertagen/Urlaubstagen (%)", 0, 100, 5)
    with f2:
        st.info("Restliche Fahrten sind Privatfahrten.")

    st.markdown("**_ Hauptfahrzeug-Gewichtung:**")
    st.caption("Wie viel Prozent der Fahrten gehen an das Hauptfahrzeug? Rest gleichmäßig verteilt.")
    fzg_namen_liste = _fzg_namen(fahrzeuge_df)
    hcol1, hcol2 = st.columns(2)
    with hcol1:
        hauptfahrzeug_name = st.selectbox("Hauptfahrzeug",
                                          ["(keines - gleichmäßig)"] + fzg_namen_liste)
    with hcol2:
        hauptfahrzeug_anteil = st.slider("Anteil Hauptfahrzeug (%)", 0, 100, 70)

    # ========== 3) EDITOREN + SPEICHERN ==========
    st.markdown("---")
    st.subheader("✏️ Fahrzeuge & Zeiträume (editierbar)")
    colE1, colE2 = st.columns(2)
    with colE1:
        fahrzeuge_edit = st.data_editor(fahrzeuge_df, num_rows="dynamic",
                                        key="fahrzeuge_editor", use_container_width=True)
    with colE2:
        zeitraeume_edit = st.data_editor(zeitraeume_df, num_rows="dynamic",
                                         key="zeiten_editor", use_container_width=True)
    if st.button("💾 Fahrzeuge & Zeiträume speichern", type="primary"):
        try:
            save_fahrzeuge(username, fahrzeuge_edit)
            save_zeitraeume(username, zeitraeume_edit)
            st.toast("Gespeichert!")
            st.rerun()
        except DatabaseError as e:
            st.error(str(e))

    # ========== 4) GENERATOR ==========
    st.markdown("---")
    jahr = int(st.number_input("Jahr", min_value=2000, max_value=2100,
                               value=date.today().year, step=1))
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
        vacation_days = urlaubs_tage(jahr, anzahl_wochen,
                                     verteilung if anzahl_wochen > 0 else "1x4 Wochen",
                                     start_w if anzahl_wochen > 0 else date(jahr, 4, 1))
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
                jahr, monate_liste, user_info, fahrzeuge_df, zeitraeume_df, keywords, params)
            progress.empty()

            # --- Automatische Fahrzeiten-Anpassung (Kilometer bleiben unverändert!) ---
            generated, anz_fix = korrigiere_geschwindigkeiten_generated(generated)
            if anz_fix:
                st.info(f"🔧 Automatische Fahrzeiten-Anpassung: Bei {anz_fix} Fahrt(en) war die "
                        "Durchschnittsgeschwindigkeit durch die KM-Skalierung unrealistisch hoch. "
                        "Die FAHRZEITEN wurden verlängert (Kilometer unverändert), sodass "
                        "Kilometer und Dauer zusammenpassen.")

            # --- Automatische Plausibilitätsprüfung über ALLE generierten Monate ---
            flags_map = pruefe_alle_monate(generated)
            _zeige_plausibilitaet(flags_map, len(monate_liste))

            st.session_state["generated_months_data"] = generated
            st.session_state["aktuelles_jahr"] = jahr
            st.session_state["aktueller_monat"] = monate_liste[-1]
            st.session_state["fahrten_df"] = generated[(jahr, monate_liste[-1])]["data"]

            lines = []
            for _, fz in fahrzeuge_df.iterrows():
                fz_id = _safe_int(fz['id']) if pd.notna(fz.get('id')) else None
                if fz_id is not None and fz_id in current_km:
                    lines.append(f"• {fz.get('bezeichnung', '?')}: **{int(current_km[fz_id]):,} km**")
            if lines:
                st.info("🚗 **Endkilometerstand pro Fahrzeug:**\n" + "\n".join(lines))
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

    # ========== 5) ANZEIGE, BEARBEITUNG, PDF ==========
    df = st.session_state.get("fahrten_df")
    if df is not None:
        jahr_akt = st.session_state["aktuelles_jahr"]
        monat_akt = st.session_state["aktueller_monat"]

        st.subheader("✏️ Fahrten anpassen & manuell hinzufügen")
        st.caption("💡 Beim Speichern werden ALLE Kilometerstände des Jahres neu berechnet "
                   "und danach automatisch erneut geprüft.")
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True,
                                   key="edit_fahrten_editor")
        col_save, col_add = st.columns([1, 1])
        with col_save:
            if st.button("💾 Änderungen speichern (Kilometer + Prüfung automatisch)"):
                try:
                    with st.spinner("Kilometerstände neu berechnen und prüfen…"):
                        year_data = _jahr_recalc_und_speichern(
                            username, jahr_akt, edited_df, (jahr_akt, monat_akt), fahrzeuge_df)
                    flags_map = pruefe_alle_monate(year_data)
                    _zeige_plausibilitaet(flags_map, len(year_data))
                    st.session_state["generated_months_data"] = {k: {"data": v} for k, v in year_data.items()}
                    st.session_state["fahrten_df"] = year_data[(jahr_akt, monat_akt)]
                    st.toast("Gespeichert – Kilometerkette neu aufgebaut!", icon="✅")
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
                with c2: new_fzg = st.selectbox("Fahrzeug", _fzg_namen(fahrzeuge_df) or [""])
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
                    new_row = {"datum": new_date, "fahrzeug_id": int(fz_id), "fahrzeug": new_fzg,
                               "route": new_route, "km_d": int(new_km_d), "km_p": int(new_km_p),
                               "abf": new_abf, "ank": new_ank, "dauer": dauer_str,
                               "abfahrt_km": 0}
                    new_df = pd.concat([edited_df, pd.DataFrame([new_row])], ignore_index=True)
                    new_df = new_df.sort_values(by="datum").reset_index(drop=True)
                    try:
                        with st.spinner("Kilometerstände neu berechnen und prüfen…"):
                            year_data = _jahr_recalc_und_speichern(
                                username, jahr_akt, new_df, (jahr_akt, monat_akt), fahrzeuge_df)
                        flags_map = pruefe_alle_monate(year_data)
                        _zeige_plausibilitaet(flags_map, len(year_data))
                        st.session_state["generated_months_data"] = {k: {"data": v} for k, v in year_data.items()}
                        st.session_state["fahrten_df"] = year_data[(jahr_akt, monat_akt)]
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
                    buf = create_jahres_pdf(st.session_state["generated_months_data"], jahr_akt,
                                            user_info, fahrzeuge_df)
                    st.download_button(f"⬇️ Download Jahresbericht {jahr_akt}", data=buf,
                                       file_name=f"Fahrtenbuch_Jahresuebersicht_{jahr_akt}.pdf",
                                       mime="application/pdf")
