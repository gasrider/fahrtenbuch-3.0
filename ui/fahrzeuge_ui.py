import streamlit as st
import pandas as pd

from database import DatabaseError
from database.fahrzeuge import load_fahrzeuge, save_fahrzeuge
from database.zeitraeume import load_zeitraeume, save_zeitraeume
from database.orte import load_orte, save_orte
from database.orte import lade_distanzen
from database.orte import speichere_distanzen
from database.orte import lade_distanz_matrix
from database.orte import lade_matrix_zeilen
from database.orte import speichere_distanz_matrix
from database.orte import speichere_geo_cache
from database.settings import load_settings
from logic.helpers import to_date
from logic.excel_import import process_fahrzeuge
from logic.excel_import import process_zeitraeume
from logic.excel_import import lade_orte
from services.routing import berechne_distanz_matrix
from services.routing import norm_key

SQL_HINWEIS = ("Falls 'relation ... does not exist' gemeldet wird: Die beiden "
               "Tabellen 'ort_koordinaten' und 'distanz_matrix' muessen einmalig "
               "im Supabase SQL-Editor angelegt werden (SQL aus der Anleitung).")


def _nonce(key):
    st.session_state.setdefault(key, 0)
    return st.session_state[key]


def render(username):
    st.subheader("Fahrzeuge, Zeitraeume & Orte")

    try:
        fahrzeuge = load_fahrzeuge(username)
        zeitraeume = load_zeitraeume(username)
        orte = load_orte(username)
        distanzen = lade_distanzen(username)
    except DatabaseError as e:
        st.error(str(e))
        return

    try:
        matrix_zeilen = lade_matrix_zeilen(username)
    except DatabaseError as e:
        matrix_zeilen = []
        st.warning(f"Distanz-Matrix nicht ladbar: {e} {SQL_HINWEIS}")

    # ================= Excel-Import =================
    st.markdown("### Excel-Import")
    st.caption("Fahrzeuge: Die ID-Spalte aus Excel wird ignoriert - Zuordnung beim "
               "Speichern ueber die Bezeichnung. Zeitraeume: Zuordnung ueber "
               "Kennzeichen/Name, offene Zeilen im Editor per Dropdown zuweisen. "
               "Reihenfolge: erst Fahrzeuge importieren & speichern, dann Zeitraeume.")
    c1, c2, c3 = st.columns(3)
    up_fzg = c1.file_uploader("Fahrzeugliste.xlsx", type=["xlsx"], key="up_fzg2")
    up_zeit = c2.file_uploader("Fahrzeug-Zeitraeume.xlsx", type=["xlsx"], key="up_zeit2")
    up_orte = c3.file_uploader("Orte.xlsx / Orte.csv", type=["xlsx", "csv"], key="up_orte2")

    if up_fzg is not None and (up_fzg.name, up_fzg.size) != st.session_state.get("up_fzg2_id"):
        st.session_state["up_fzg2_id"] = (up_fzg.name, up_fzg.size)
        try:
            importiert = process_fahrzeuge(up_fzg)
            name_zu_id = {}
            if not fahrzeuge.empty:
                for _, r in fahrzeuge.iterrows():
                    if pd.notna(r.get("id")) and r.get("bezeichnung"):
                        name_zu_id[str(r["bezeichnung"]).strip().lower()] = int(r["id"])
            importiert["id"] = importiert["bezeichnung"].map(
                lambda b: name_zu_id.get(str(b).strip().lower())
                if pd.notna(b) else None).astype("Int64")
            st.session_state["fzg_import"] = importiert
        except Exception as e:
            st.error(f"Fahrzeuge-Import: {e}")

    if up_zeit is not None and (up_zeit.name, up_zeit.size) != st.session_state.get("up_zeit2_id"):
        st.session_state["up_zeit2_id"] = (up_zeit.name, up_zeit.size)
        try:
            basis_fzg = fahrzeuge
            st.session_state["zeit_import"] = process_zeitraeume(up_zeit, basis_fzg)
            st.warning("Zeitraeume geladen - Zuordnung ueber Kennzeichen/Name; "
                       "offene Zeilen im Editor unten per Dropdown dem Fahrzeug "
                       "zuweisen und dann speichern!")
        except Exception as e:
            st.error(f"Zeitraeume-Import: {e}")

    if up_orte is not None and (up_orte.name, up_orte.size) != st.session_state.get("up_orte2_id"):
        st.session_state["up_orte2_id"] = (up_orte.name, up_orte.size)
        try:
            st.session_state["orte_import"] = lade_orte(up_orte)
        except Exception as e:
            st.error(f"Orte-Import: {e}")

    # --- Vorschau Fahrzeuge ---
    if st.session_state.get("fzg_import") is not None:
        st.markdown("**Vorschau Fahrzeuge-Import:**")
        st.dataframe(st.session_state["fzg_import"], use_container_width=True)
        b1, b2 = st.columns(2)
        if b1.button("Fahrzeuge-Import uebernehmen", type="primary"):
            st.session_state["fzg_basis"] = st.session_state.pop("fzg_import")
            st.session_state["fzg_nonce"] = _nonce("fzg_nonce") + 1
            st.rerun()
        if b2.button("Fahrzeuge-Import verwerfen"):
            st.session_state.pop("fzg_import", None)
            st.rerun()

    # --- Vorschau Zeitraeume ---
    if st.session_state.get("zeit_import") is not None:
        st.markdown("**Vorschau Zeitraeume-Import:**")
        st.dataframe(st.session_state["zeit_import"], use_container_width=True)
        b1, b2 = st.columns(2)
        if b1.button("Zeitraeume-Import uebernehmen", type="primary"):
            st.session_state["zeit_basis"] = st.session_state.pop("zeit_import")
            st.session_state["zeit_nonce"] = _nonce("zeit_nonce") + 1
            st.rerun()
        if b2.button("Zeitraeume-Import verwerfen"):
            st.session_state.pop("zeit_import", None)
            st.rerun()

    # --- Vorschau Orte ---
    if st.session_state.get("orte_import") is not None:
        st.markdown(f"**Vorschau Orte-Import:** {len(st.session_state['orte_import'])} Orte erkannt")
        st.dataframe(st.session_state["orte_import"], use_container_width=True)
        b1, b2 = st.columns(2)
        if b1.button("Orte-Import uebernehmen & speichern", type="primary"):
            try:
                save_orte(username, st.session_state["orte_import"]["Ort"].tolist())
                st.session_state.pop("orte_import", None)
                st.success("Orte gespeichert.")
                st.rerun()
            except DatabaseError as e:
                st.error(str(e))
        if b2.button("Orte-Import verwerfen"):
            st.session_state.pop("orte_import", None)
            st.rerun()

    st.divider()

    # ================= Fahrzeuge =================
    st.markdown("### Fahrzeuge")
    st.caption("IDs bleiben beim Speichern stabil (Update statt Neu-Anlegen). "
               "Excel-Importe werden ueber die Bezeichnung zugeordnet.")
    basis_fzg = st.session_state.get("fzg_basis")
    if basis_fzg is None:
        basis_fzg = fahrzeuge.drop(columns=["username"], errors="ignore")
    edit_fzg = st.data_editor(
        basis_fzg,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "bezeichnung": st.column_config.TextColumn("Bezeichnung"),
            "kennzeichen": st.column_config.TextColumn("Kennzeichen"),
            "start_km_vorjahr": st.column_config.NumberColumn(
                "Start-KM (Vorjahr)", min_value=0, step=1),
            "privat_km_min": st.column_config.NumberColumn(
                "Privat min. KM", min_value=0, step=1),
            "privat_km_max": st.column_config.NumberColumn(
                "Privat max. KM", min_value=0, step=1),
            "dienstlich_quote": st.column_config.NumberColumn(
                "Dienstlich %", min_value=0, max_value=100, step=5),
        },
        num_rows="dynamic", use_container_width=True,
        key=f"fzg_editor_{_nonce('fzg_nonce')}",
    )
    if st.button("Fahrzeuge speichern", type="primary"):
        try:
            save_fahrzeuge(username, edit_fzg)
            st.session_state["fzg_basis"] = None
            st.success("Fahrzeuge gespeichert - IDs blieben erhalten.")
            st.rerun()
        except DatabaseError as e:
            st.error(str(e))

    st.divider()

    # ================= Zeitraeume =================
    st.markdown("### Nutzungszeitraeume")
    if fahrzeuge.empty:
        st.info("Zuerst Fahrzeuge anlegen/importieren und speichern.")
        return

    basis_zeit = st.session_state.get("zeit_basis")
    if basis_zeit is None:
        basis_zeit = zeitraeume.copy()
        for col in ("von", "bis"):
            if col in basis_zeit.columns:
                basis_zeit[col] = pd.to_datetime(basis_zeit[col], errors="coerce").dt.date

    fzg_optionen_ids = []
    fzg_labels = {}
    for _, r in fahrzeuge.iterrows():
        if pd.notna(r.get("id")):
            fid = int(r["id"])
            fzg_optionen_ids.append(fid)
            fzg_labels[fid] = f"{r['bezeichnung']} ({r.get('kennzeichen', '')})"

    edit_zeit = st.data_editor(
        basis_zeit, num_rows="dynamic", use_container_width=True,
        key=f"zeiten_editor_{_nonce('zeit_nonce')}",
        column_config={
            "fahrzeug_id": st.column_config.SelectboxColumn(
                "Fahrzeug",
                options=fzg_optionen_ids,
                format_func=lambda i: fzg_labels.get(int(i), f"ID {i}"),
                required=True,
                help="Fahrzeug auswaehlen - Zeilen ohne Zuordnung werden beim "
                     "Speichern uebersprungen!"),
            "von": st.column_config.DateColumn("Von", format="DD.MM.YYYY"),
            "bis": st.column_config.DateColumn("Bis", format="DD.MM.YYYY"),
        })

    if st.button("Zeitraeume speichern", type="primary"):
        try:
            speichern_df = edit_zeit[edit_zeit["fahrzeug_id"].notna()].copy()
            if speichern_df.empty:
                st.warning("Keine Zeilen mit Fahrzeug-Zuordnung - bitte im Editor "
                           "jedem Zeitraum ein Fahrzeug zuweisen.")
            else:
                save_zeitraeume(username, speichern_df)
                st.session_state["zeit_basis"] = None
                st.success("Zeitraeume gespeichert.")
        except DatabaseError as e:
            st.error(str(e))

    st.divider()

    # ================= Orte & Distanzen =================
    st.markdown("### Orte & Distanzen")
    st.caption("Pro Ort die einfache Fahrstrecke vom Wohnort in km (wird unten "
               "automatisch aus der Online-Karte gefuellt) plus die "
               "Ort-zu-Ort-Distanz-Matrix. Generator und HU-Korrektur nutzen "
               "diese Werte fuer realistische Kilometer.")

    if orte:
        dist_df = pd.DataFrame([{"Ort": o, "km einfach": distanzen.get(o, 0)}
                                for o in orte])
        dist_edit = st.data_editor(dist_df, use_container_width=True,
                                   key="dist_editor",
                                   column_config={
                                       "Ort": st.column_config.TextColumn(
                                           "Ort", disabled=True),
                                       "km einfach": st.column_config.NumberColumn(
                                           "km einfach", min_value=0, step=1),
                                   })
        if st.button("Distanzen speichern"):
            try:
                d_map = {}
                for _, r in dist_edit.iterrows():
                    o = str(r["Ort"]).strip()
                    if o:
                        d_map[o] = int(r["km einfach"] or 0)
                speichere_distanzen(username, d_map)
                st.success("Distanzen gespeichert.")
            except DatabaseError as e:
                st.error(str(e))
    else:
        st.info("Noch keine Orte gespeichert - Excel hochladen oder unten hinzufuegen.")

    # --- Online-Berechnung (OpenStreetMap / OSRM) ---
    st.markdown("##### Distanzen automatisch berechnen (Online-Karte)")
    st.caption("Sucht alle Orte auf der Karte (OpenStreetMap) und berechnet die "
               "echten Fahrstrecken zwischen allen Orten (OSRM-Routing, kein "
               "API-Key noetig). Die Ergebnisse landen in der Distanz-Matrix "
               "unten und werden vom Generator und der HU-Korrektur automatisch "
               "verwendet. Erste Berechnung je nach Anzahl Orte ca. 2-5 Minuten, "
               "danach wird alles gespeichert und nur noch nachgerechnet, was fehlt.")
    zusatz_text = st.text_input(
        "Zusaetzliche Orte (z. B. Werkstaetten), kommagetrennt",
        key="zusatz_orte_input")
    nur_fehlende = st.checkbox(
        "Nur fehlende Strecken berechnen (vorhandene nicht ueberschreiben)",
        value=True)
    if st.button("Distanzen online berechnen", type="primary"):
        st.session_state.pop("geo_summary", None)
        zusatz = [s.strip() for s in (zusatz_text or "").split(",") if s.strip()]
        try:
            try:
                user_info = load_settings(username)
            except DatabaseError:
                user_info = {}
            wohnort_raw = str(user_info.get("wohnort", "") or "")
            wohnort_c = (wohnort_raw.split(",")[-1].strip()
                         if "," in wohnort_raw else wohnort_raw.strip())
            dienstort_raw = str(user_info.get("dienstort", "") or "")
            dienstort_c = (dienstort_raw.split(",")[-1].strip()
                           if "," in dienstort_raw else dienstort_raw.strip())
            if not wohnort_c:
                st.error("Kein Wohnort in den Einstellungen hinterlegt - bitte "
                         "zuerst im Login-/Profil-Bereich setzen.")
                return
            vorhandene = lade_distanz_matrix(username) if nur_fehlende else {}
            with st.status("Distanzen werden berechnet...", expanded=True) as status:
                bar = st.progress(0.0, text="Start...")
                txt = st.empty()

                def _prog(fertig, gesamt, msg):
                    frac = min(1.0, float(fertig) / float(gesamt)) if gesamt else 1.0
                    try:
                        bar.progress(frac, text=msg)
                    except Exception:
                        txt.write(msg)

                koordinaten, matrix_neu, meldungen = berechne_distanz_matrix(
                    list(orte), wohnort_c, dienstort_c, zusatz, vorhandene, _prog)
                for m in meldungen:
                    st.write(m)
                status.update(label="Distanzen berechnet.", state="complete")
            if koordinaten:
                speichere_geo_cache(username, koordinaten)
            if matrix_neu:
                quelle_alt = {(str(z["ort_a"]).strip().lower(),
                               str(z["ort_b"]).strip().lower()): z["quelle"]
                              for z in matrix_zeilen}
                zeilen = []
                for (a, b), km in matrix_neu.items():
                    disp_a = koordinaten.get(a, {}).get("ort") or a
                    disp_b = koordinaten.get(b, {}).get("ort") or b
                    zeilen.append({"ort_a": disp_a, "ort_b": disp_b,
                                   "km": int(km),
                                   "quelle": quelle_alt.get((a, b), "osrm")})
                speichere_distanz_matrix(username, zeilen)
            summary = []
            home_k = norm_key(wohnort_c)
            if matrix_neu:
                summary.append(f"{len(matrix_neu)} Strecken in der Distanz-Matrix "
                               "gespeichert.")
            if koordinaten.get(home_k, {}).get("ok") and orte:
                neue_map = dict(distanzen)
                aktualisiert = []
                for o in orte:
                    k = norm_key(o)
                    key = (home_k, k) if home_k <= k else (k, home_k)
                    km_neu = matrix_neu.get(key)
                    if km_neu and int(km_neu) > 0:
                        if int(neue_map.get(o, 0) or 0) != int(km_neu):
                            aktualisiert.append(
                                f"{o}: {neue_map.get(o, 0) or 0} -> {int(km_neu)} km")
                        neue_map[o] = int(km_neu)
                speichere_distanzen(username, neue_map)
                if aktualisiert:
                    summary.append("'km einfach' automatisch aktualisiert: "
                                   + ", ".join(aktualisiert))
            summary.append("Wichtig: Jahr im Generator neu generieren, damit die "
                           "neuen Kilometer einfliessen (bereits gespeicherte "
                           "Fahrten bleiben unveraendert).")
            st.session_state["geo_summary"] = summary
            st.rerun()
        except DatabaseError as e:
            st.error(f"{e} {SQL_HINWEIS}")
        except Exception as e:
            st.error(f"Online-Berechnung fehlgeschlagen: {e}")

    if st.session_state.get("geo_summary"):
        for line in st.session_state["geo_summary"]:
            st.write(line)
        if st.button("Hinweis ausblenden"):
            st.session_state.pop("geo_summary", None)
            st.rerun()

    # --- Distanz-Matrix (Ort zu Ort) ---
    st.markdown("##### Distanz-Matrix (Ort zu Ort)")
    st.caption("Echte Fahrstrecken zwischen allen Orten (von der Online-Karte "
               "oder manuell korrigiert). Jede Strecke gilt in beide Richtungen. "
               "Km-Werte hier aendern und speichern ueberschreibt die "
               "Online-Werte - nuetzlich, falls ein Ort falsch zugeordnet wurde.")
    if matrix_zeilen:
        mdf = pd.DataFrame([{"Ort A": z["ort_a"], "Ort B": z["ort_b"],
                             "km": z["km"], "Quelle": z["quelle"]}
                            for z in matrix_zeilen])
        alt_map = {(z["ort_a"].strip().lower(), z["ort_b"].strip().lower()):
                   (z["km"], z["quelle"]) for z in matrix_zeilen}
        edit_m = st.data_editor(
            mdf, use_container_width=True, key="matrix_editor",
            column_config={
                "Ort A": st.column_config.TextColumn("Ort A", disabled=True),
                "Ort B": st.column_config.TextColumn("Ort B", disabled=True),
                "km": st.column_config.NumberColumn("km", min_value=1, step=1),
                "Quelle": st.column_config.TextColumn("Quelle", disabled=True),
            })
        if st.button("Matrix-Aenderungen speichern"):
            try:
                zeilen_neu = []
                for _, r in edit_m.iterrows():
                    a = str(r["Ort A"] or "").strip()
                    b = str(r["Ort B"] or "").strip()
                    try:
                        km = int(r["km"] or 0)
                    except (TypeError, ValueError):
                        continue
                    if not a or not b or km <= 0:
                        continue
                    alt = alt_map.get((a.lower(), b.lower()))
                    if alt is None:
                        quelle = "manuell"
                    else:
                        km_alt, q_alt = alt
                        quelle = "manuell" if km != km_alt else q_alt
                    zeilen_neu.append({"ort_a": a, "ort_b": b, "km": km,
                                       "quelle": quelle})
                speichere_distanz_matrix(username, zeilen_neu)
                st.success("Distanz-Matrix gespeichert.")
                st.rerun()
            except DatabaseError as e:
                st.error(str(e))
    else:
        st.info("Noch keine Distanz-Matrix vorhanden - oben 'Distanzen online "
                "berechnen' starten.")

    loesch = st.multiselect("Zu loeschende Orte markieren", orte)
    if loesch and st.button("Ausgewaehlte Orte loeschen"):
        try:
            save_orte(username, [o for o in orte if o not in loesch])
            st.rerun()
        except DatabaseError as e:
            st.error(str(e))

    neu = st.text_input("Neuer Ort (manuell)")
    if st.button("Ort hinzufuegen") and neu.strip():
        try:
            save_orte(username, orte + [neu.strip()])
            st.rerun()
        except DatabaseError as e:
            st.error(str(e))
