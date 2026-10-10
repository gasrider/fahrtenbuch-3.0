import streamlit as st
import pandas as pd

from database import DatabaseError
from database.fahrzeuge import load_fahrzeuge, save_fahrzeuge
from database.zeitraeume import load_zeitraeume, save_zeitraeume
from database.orte import load_orte, save_orte
from database.orte import lade_distanzen
from database.orte import speichere_distanzen
from logic.helpers import to_date
from logic.excel_import import process_fahrzeuge
from logic.excel_import import process_zeitraeume
from logic.excel_import import lade_orte


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
    st.caption("Pro Ort die einfache Fahrstrecke vom Wohnort in km - die HU-Korrektur "
               "nutzt diese Werte fuer die privaten Kilometer zur Werkstatt.")

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

        loesch = st.multiselect("Zu loeschende Orte markieren", orte)
        if loesch and st.button("Ausgewaehlte Orte loeschen"):
            try:
                save_orte(username, [o for o in orte if o not in loesch])
                st.rerun()
            except DatabaseError as e:
                st.error(str(e))
    else:
        st.info("Noch keine Orte gespeichert - Excel hochladen oder unten hinzufuegen.")

    neu = st.text_input("Neuer Ort (manuell)")
    if st.button("Ort hinzufuegen") and neu.strip():
        try:
            save_orte(username, orte + [neu.strip()])
            st.rerun()
        except DatabaseError as e:
            st.error(str(e))
