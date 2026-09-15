import streamlit as st
import pandas as pd

from database import DatabaseError
from database.fahrzeuge import load_fahrzeuge, save_fahrzeuge
from database.zeitraeume import load_zeitraeume, save_zeitraeume
from database.orte import load_orte, save_orte
from logic.helpers import to_date
from logic.excel_import import lade_fahrzeuge, lade_zeitraeume, lade_orte


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
    st.caption("Excel/CSV hochladen → Vorschau prüfen → „Übernehmen“. Spalten werden "
               "automatisch erkannt. Empfohlene Reihenfolge: erst Fahrzeuge importieren "
               "und speichern, dann Zeiträume.")
    c1, c2, c3 = st.columns(3)
    up_fzg = c1.file_uploader("Fahrzeuge", type=["xlsx", "xls", "csv"], key="up_fzg")
    up_zeit = c2.file_uploader("Zeiträume", type=["xlsx", "xls", "csv"], key="up_zeit")
    up_orte = c3.file_uploader("Orte", type=["xlsx", "xls", "csv"], key="up_orte")

    if up_fzg is not None and (up_fzg.name, up_fzg.size) != st.session_state.get("up_fzg_id"):
        st.session_state["up_fzg_id"] = (up_fzg.name, up_fzg.size)
        try:
            st.session_state["fzg_import"] = lade_fahrzeuge(up_fzg)
        except (ValueError, Exception) as e:
            st.error(f"Fahrzeuge-Import: {e}")

    if up_zeit is not None and (up_zeit.name, up_zeit.size) != st.session_state.get("up_zeit_id"):
        st.session_state["up_zeit_id"] = (up_zeit.name, up_zeit.size)
        try:
            st.session_state["zeit_import"] = lade_zeitraeume(up_zeit)
        except (ValueError, Exception) as e:
            st.error(f"Zeiträume-Import: {e}")

    if up_orte is not None and (up_orte.name, up_orte.size) != st.session_state.get("up_orte_id"):
        st.session_state["up_orte_id"] = (up_orte.name, up_orte.size)
        try:
            st.session_state["orte_import"] = lade_orte(up_orte)
        except (ValueError, Exception) as e:
            st.error(f"Orte-Import: {e}")

    # --- Vorschau Fahrzeuge ---
    if st.session_state.get("fzg_import") is not None:
        st.markdown("**Vorschau Fahrzeuge-Import:**")
        st.dataframe(st.session_state["fzg_import"], use_container_width=True)
        b1, b2 = st.columns(2)
        if b1.button("✅ Fahrzeuge-Import übernehmen", type="primary"):
            st.session_state["fzg_basis"] = st.session_state["fzg_import"]
            st.session_state["fzg_import"] = None
            st.session_state["fzg_nonce"] = _nonce("fzg_nonce") + 1
            st.rerun()
        if b2.button("❌ Fahrzeuge-Import verwerfen"):
            st.session_state["fzg_import"] = None
            st.rerun()

    # --- Vorschau Zeiträume ---
    if st.session_state.get("zeit_import") is not None:
        st.markdown("**Vorschau Zeiträume-Import:**")
        st.dataframe(st.session_state["zeit_import"], use_container_width=True)
        st.caption("Zuordnung über die Fahrzeug-Bezeichnung – Fahrzeuge müssen dafür "
                   "bereits gespeichert sein.")
        b1, b2 = st.columns(2)
        if b1.button("✅ Zeiträume-Import übernehmen", type="primary"):
            name_to_id = {str(r["bezeichnung"]).strip().lower(): int(r["id"])
                          for _, r in fahrzeuge.iterrows() if pd.notna(r.get("id"))}
            import_map, nicht_gefunden = {}, []
            for _, z in st.session_state["zeit_import"].iterrows():
                fid = name_to_id.get(str(z["fahrzeug"]).strip().lower())
                if fid:
                    import_map[fid] = (z["von"], z["bis"])
                else:
                    nicht_gefunden.append(str(z["fahrzeug"]))
            st.session_state["zeit_import_map"] = import_map
            st.session_state["zeit_import"] = None
            if nicht_gefunden:
                st.warning("Übersprungen (Fahrzeug nicht gefunden): "
                           + ", ".join(nicht_gefunden))
            st.rerun()
        if b2.button("❌ Zeiträume-Import verwerfen"):
            st.session_state["zeit_import"] = None
            st.rerun()

    # --- Vorschau Orte ---
    if st.session_state.get("orte_import") is not None:
        st.markdown(f"**Vorschau Orte-Import:** {len(st.session_state['orte_import'])} Zeilen erkannt")
        st.dataframe(st.session_state["orte_import"], use_container_width=True)
        b1, b2 = st.columns(2)
        if b1.button("✅ Orte-Import übernehmen & speichern", type="primary"):
            try:
                save_orte(username, st.session_state["orte_import"]["ort"].tolist())
                st.session_state["orte_import"] = None
                st.success("Orte gespeichert.")
                st.rerun()
            except DatabaseError as e:
                st.error(str(e))
        if b2.button("❌ Orte-Import verwerfen"):
            st.session_state["orte_import"] = None
            st.rerun()

    st.divider()

    # ================= Fahrzeuge =================
    st.markdown("### 🚗 Fahrzeuge")
    basis = st.session_state.get("fzg_basis")
    if basis is None:
        basis = fahrzeuge.drop(columns=["username"], errors="ignore")
    edit = st.data_editor(
        basis,
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
            save_fahrzeuge(username, edit)
            st.session_state["fzg_basis"] = None
            st.session_state.pop("zeit_import_map", None)  # IDs ändern sich!
            st.success("Fahrzeuge gespeichert.")
            st.rerun()
        except DatabaseError as e:
            st.error(str(e))

    st.divider()

    # ================= Zeiträume =================
    st.markdown("### 📅 Nutzungszeiträume")
    if fahrzeuge.empty:
        st.info("Zuerst Fahrzeuge anlegen/importieren und speichern.")
        return

    zmap = {}
    if not zeitraeume.empty:
        for _, z in zeitraeume.iterrows():
            try:
                zmap[int(z["fahrzeug_id"])] = (to_date(z["von"]), to_date(z["bis"]))
            except (ValueError, TypeError):
                pass
    zmap.update(st.session_state.get("zeit_import_map", {}))

    neue_zeitraeume = []
    for _, fz in fahrzeuge.iterrows():
        fid = int(fz["id"])
        label = f"{fz['bezeichnung']} ({fz.get('kennzeichen', '')})"
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
            st.session_state.pop("zeit_import_map", None)
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