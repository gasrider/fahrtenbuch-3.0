import streamlit as st
import pandas as pd

from database import DatabaseError
from database.fahrzeuge import load_fahrzeuge, save_fahrzeuge
from database.zeitraeume import load_zeitraeume, save_zeitraeume
from database.orte import load_orte, save_orte
from logic.helpers import to_date
from logic.excel_import import process_fahrzeuge, process_zeitraeume, lade_orte


def _nonce(key):
    st.session_state.setdefault(key, 0)
    return st.session_state[key]


def render(username):
    st.subheader("🚗 Fahrzeuge, Zeiträume & Orte")

    try:
        fahrzeuge = load_fahrzeuge(username)
        zeitraeume = load_zeitraeume(username)
        orte = load_orte(username)
    except DatabaseError as e:
        st.error(str(e)); return

    # ================= Excel-Import =================
    st.markdown("### 📥 Excel-Import")
    st.caption("Reihenfolge: erst Fahrzeuge importieren & speichern, dann Zeiträume "
               "(Zuordnung erfolgt über Kennzeichen oder Bezeichnung).")
    c1, c2, c3 = st.columns(3)
    up_fzg = c1.file_uploader("Fahrzeugliste.xlsx", type=["xlsx"], key="up_fzg2")
    up_zeit = c2.file_uploader("Fahrzeug-Zeiträume.xlsx", type=["xlsx"], key="up_zeit2")
    up_orte = c3.file_uploader("Orte.xlsx / Orte.csv", type=["xlsx", "csv"], key="up_orte2")

    if up_fzg is not None and (up_fzg.name, up_fzg.size) != st.session_state.get("up_fzg2_id"):
        st.session_state["up_fzg2_id"] = (up_fzg.name, up_fzg.size)
        try:
            st.session_state["fzg_import"] = process_fahrzeuge(up_fzg)
        except Exception as e:
            st.error(f"Fahrzeuge-Import: {e}")

    if up_zeit is not None and (up_zeit.name, up_zeit.size) != st.session_state.get("up_zeit2_id"):
        st.session_state["up_zeit2_id"] = (up_zeit.name, up_zeit.size)
        try:
            basis_fzg = st.session_state.get("fzg_import", fahrzeuge)
            st.session_state["zeit_import"] = process_zeitraeume(up_zeit, basis_fzg)
        except Exception as e:
            st.error(f"Zeiträume-Import: {e}")

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
        if b1.button("✅ Fahrzeuge-Import übernehmen", type="primary"):
            st.session_state["fzg_basis"] = st.session_state.pop("fzg_import")
            st.session_state["fzg_nonce"] = _nonce("fzg_nonce") + 1
            st.rerun()
        if b2.button("❌ Fahrzeuge-Import verwerfen"):
            st.session_state.pop("fzg_import", None)
            st.rerun()

    # --- Vorschau Zeiträume ---
    if st.session_state.get("zeit_import") is not None:
        st.markdown("**Vorschau Zeiträume-Import:**")
        st.dataframe(st.session_state["zeit_import"], use_container_width=True)
        b1, b2 = st.columns(2)
        if b1.button("✅ Zeiträume-Import übernehmen", type="primary"):
            st.session_state["zeit_basis"] = st.session_state.pop("zeit_import")
            st.session_state["zeit_nonce"] = _nonce("zeit_nonce") + 1
            st.rerun()
        if b2.button("❌ Zeiträume-Import verwerfen"):
            st.session_state.pop("zeit_import", None)
            st.rerun()

    # --- Vorschau Orte ---
    if st.session_state.get("orte_import") is not None:
        st.markdown(f"**Vorschau Orte-Import:** {len(st.session_state['orte_import'])} Orte erkannt")
        st.dataframe(st.session_state["orte_import"], use_container_width=True)
        b1, b2 = st.columns(2)
        if b1.button("✅ Orte-Import übernehmen & speichern", type="primary"):
            try:
                save_orte(username, st.session_state["orte_import"]["Ort"].tolist())
                st.session_state.pop("orte_import", None)
                st.success("Orte gespeichert.")
                st.rerun()
            except DatabaseError as e:
                st.error(str(e))
        if b2.button("❌ Orte-Import verwerfen"):
            st.session_state.pop("orte_import", None)
            st.rerun()

    st.divider()

    # ================= Fahrzeuge =================
    st.markdown("### 🚗 Fahrzeuge")
    st.caption("Hinweis: Beim Speichern werden alle Zeilen neu angelegt – die IDs ändern "
               "sich! Danach ggf. Zeiträume neu speichern.")
    basis_fzg = st.session_state.get("fzg_basis")
    if basis_fzg is None:
        basis_fzg = fahrzeuge.drop(columns=["username"], errors="ignore")
    edit_fzg = st.data_editor(
        basis_fzg,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "bezeichnung": st.column_config.TextColumn("Bezeichnung"),
            "kennzeichen": st.column_config.TextColumn("Kennzeichen"),
            "start_km_vorjahr": st.column_config.NumberColumn("Start-KM (Vorjahr)", min_value=0, step=1),
            "privat_km_min": st.column_config.NumberColumn("Privat min. KM", min_value=0, step=1),
            "privat_km_max": st.column_config.NumberColumn("Privat max. KM", min_value=0, step=1),
            "dienstlich_quote": st.column_config.NumberColumn("Dienstlich %", min_value=0, max_value=100, step=5),
        },
        num_rows="dynamic", use_container_width=True,
        key=f"fzg_editor_{_nonce('fzg_nonce')}",
    )
    if st.button("💾 Fahrzeuge speichern", type="primary"):
        try:
            save_fahrzeuge(username, edit_fzg)
            st.session_state["fzg_basis"] = None
            st.success("Fahrzeuge gespeichert.")
            st.rerun()
        except DatabaseError as e:
            st.error(str(e))

    st.divider()

    # ================= Zeiträume =================
    st.markdown("### 📅 Nutzungszeiträume (fahrzeug_id, von, bis)")
    if fahrzeuge.empty:
        st.info("Zuerst Fahrzeuge anlegen/importieren und speichern.")
        return
    basis_zeit = st.session_state.get("zeit_basis")
    if basis_zeit is None:
        basis_zeit = zeitraeume.copy()
        for col in ("von", "bis"):
            if col in basis_zeit.columns:
                basis_zeit[col] = pd.to_datetime(basis_zeit[col], errors="coerce").dt.date
    edit_zeit = st.data_editor(
        basis_zeit, num_rows="dynamic", use_container_width=True,
        key=f"zeiten_editor_{_nonce('zeit_nonce')}",
        column_config={
            "fahrzeug_id": st.column_config.NumberColumn(
                "Fahrzeug-ID",
                help="ID aus der Fahrzeug-Tabelle oben (Spalte 'id')."),
            "von": st.column_config.DateColumn("Von", format="DD.MM.YYYY"),
            "bis": st.column_config.DateColumn("Bis", format="DD.MM.YYYY"),
        })
    if st.button("💾 Zeiträume speichern", type="primary"):
        try:
            save_zeitraeume(username, edit_zeit)
            st.session_state["zeit_basis"] = None
            st.success("Zeiträume gespeichert.")
        except DatabaseError as e:
            st.error(str(e))

    st.divider()

    # ================= Orte =================
    st.markdown("### 📍 Orte (Kundenstopps, Werkstätten, Ziele)")
    if orte:
        st.dataframe(pd.DataFrame({"Ort": orte}), use_container_width=True)
        loesch = st.multiselect("Zu löschende Orte markieren", orte)
        if loesch and st.button("🗑️ Ausgewählte Orte löschen"):
            try:
                save_orte(username, [o for o in orte if o not in loesch])
                st.rerun()
            except DatabaseError as e:
                st.error(str(e))
    else:
        st.info("Noch keine Orte gespeichert – Excel hochladen oder unten hinzufügen.")
    neu = st.text_input("Neuer Ort (manuell)")
    if st.button("➕ Ort hinzufügen") and neu.strip():
        try:
            save_orte(username, orte + [neu.strip()])
            st.rerun()
        except DatabaseError as e:
            st.error(str(e))