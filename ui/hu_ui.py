"""HU-Korrekturen wie Original: Werkstattort-Dropdown, Stopps-Freitext (Komma-getrennt),
Kilometerstände + Dauer + Ankunft werden neu berechnet, HU-Fahrt mit Werkstatt-Route."""
import streamlit as st
import pandas as pd

from database import DatabaseError
from database.fahrzeuge import load_fahrzeuge
from database.orte import load_orte
from database.hu_corrections import load_hu_raw, save_hu_corrections
from database.fahrten import load_year
from logic.helpers import _safe_int, _parse_date_iso
from logic.hu_korrektur import wende_hu_korrekturen_an

SPALTEN = ["Fahrzeug", "Datum der HU", "Kilometerstand bei HU",
           "Werkstattort (Dropdown)", "Kundenstopps vor HU (mehrere möglich)",
           "Kundenstopps nach HU (mehrere möglich)"]


def render(username):
    st.subheader("🔧 Kilometerstand anpassen (Hauptuntersuchung)")
    st.info("Hier kannst du für jedes Fahrzeug den Kilometerstand an einem bestimmten Datum "
            "(z. B. von einer Hauptuntersuchung) anpassen. Die Fahrten werden vor und nach "
            "diesem Datum neu berechnet und eine Fahrt zur Werkstatt erstellt.")
    try:
        fahrzeuge = load_fahrzeuge(username)
        orte = load_orte(username)
        raw = load_hu_raw(username)
    except DatabaseError as e:
        st.error(str(e)); return

    fahrzeug_optionen = {str(r['bezeichnung']).strip(): _safe_int(r['id'])
                         for _, r in fahrzeuge.iterrows()
                         if pd.notna(r.get('id')) and str(r.get('bezeichnung', '')).strip()
                         and str(r['bezeichnung']).strip().lower() not in ('none', 'nan')}
    if not fahrzeug_optionen:
        st.warning("Zuerst Fahrzeuge anlegen.")
        return

    werkstatt_orte = sorted(orte) if orte else []
    verfuegbar_str = ", ".join(werkstatt_orte[:20]) + (" …" if len(werkstatt_orte) > 20 else "")

    rows = []
    for r in raw:
        fid = r.get("fahrzeug_id")
        name = next((n for n, i in fahrzeug_optionen.items() if i == int(fid)), "") if fid is not None else ""
        rows.append({"Fahrzeug": name, "Datum der HU": r.get("datum") or None,
                     "Kilometerstand bei HU": _safe_int(r.get("km_at_hu")),
                     "Werkstattort (Dropdown)": r.get("werkstattort", "") or "",
                     "Kundenstopps vor HU (mehrere möglich)": r.get("stopps_vor_hu", "") or "",
                     "Kundenstopps nach HU (mehrere möglich)": r.get("stopps_nach_hu", "") or ""})
    basis = pd.DataFrame(rows, columns=SPALTEN)
    if not basis.empty:
        basis["Datum der HU"] = pd.to_datetime(basis["Datum der HU"], errors="coerce").dt.date

    edited = st.data_editor(
        basis, num_rows="dynamic", use_container_width=True, key="hu_editor",
        column_config={
            "Fahrzeug": st.column_config.SelectboxColumn("Fahrzeug", options=list(fahrzeug_optionen.keys()), required=True),
            "Datum der HU": st.column_config.DateColumn("Datum der HU", format="DD.MM.YYYY", required=True),
            "Kilometerstand bei HU": st.column_config.NumberColumn("Kilometerstand bei HU (km)", min_value=0, step=1, required=True),
            "Werkstattort (Dropdown)": st.column_config.SelectboxColumn(
                "Werkstattort", options=werkstatt_orte, required=True,
                help="Orte werden im Tab 'Fahrzeuge & Orte' gepflegt/importiert."),
            "Kundenstopps vor HU (mehrere möglich)": st.column_config.TextColumn(
                "Stopps vor HU", max_chars=300,
                help=f"Orte EINTIPPEN (Komma-getrennt). Zweck wird automatisch zugewiesen. Verfügbare Orte: {verfuegbar_str}"),
            "Kundenstopps nach HU (mehrere möglich)": st.column_config.TextColumn(
                "Stopps nach HU", max_chars=300,
                help=f"Orte EINTIPPEN (Komma-getrennt). Zweck wird automatisch zugewiesen. Verfügbare Orte: {verfuegbar_str}"),
        })

    if st.button("🔧 Kilometerstände korrigieren"):
        if edited.empty:
            st.warning("Bitte gib mindestens eine Korrektur ein.")
            return
        correction_data, fehler = [], []
        for i, (_, row) in enumerate(edited.iterrows(), start=2):
            name = str(row.get("Fahrzeug") or "").strip()
            if name not in fahrzeug_optionen:
                if not name:
                    continue
                fehler.append(f"Zeile {i}: Fahrzeug '{name}' unbekannt")
                continue
            if pd.isna(row.get("Werkstattort (Dropdown)")) or not str(row.get("Werkstattort (Dropdown)")).strip():
                fehler.append(f"Zeile {i}: Werkstattort fehlt")
                continue
            datum = _parse_date_iso(row.get("Datum der HU"))
            if not datum:
                fehler.append(f"Zeile {i}: ungültiges Datum")
                continue
            nach = [s.strip() for s in str(row.get("Kundenstopps nach HU (mehrere möglich)") or "").split(",") if s.strip()]
            vor = [s.strip() for s in str(row.get("Kundenstopps vor HU (mehrere möglich)") or "").split(",") if s.strip()]
            correction_data.append({"fahrzeug_id": fahrzeug_optionen[name], "datum": datum,
                                    "km_at_hu": _safe_int(row.get("Kilometerstand bei HU")),
                                    "werkstattort": str(row["Werkstattort (Dropdown)"]).strip(),
                                    "stopps_nach_hu": nach, "stopps_vor_hu": vor})
        if fehler:
            st.error("Nicht gespeichert: " + " | ".join(fehler))
            return
        if not correction_data:
            st.error("Ungültige Eingabe. Bitte stelle sicher, dass alle Pflichtfelder ausgefüllt sind.")
            return
        # generierte Daten laden (aus DB, damit HU auf gespeicherten Fahrten arbeitet)
        gen = {}
        try:
            from database.fahrten import load_year
            from datetime import date as _d
            jahre = sorted({int(c["datum"][:4]) for c in correction_data})
            for j in jahre:
                for (jj, mm), df in load_year(username, j).items():
                    gen[(jj, mm)] = {"data": df}
        except DatabaseError as e:
            st.error(str(e)); return
        if not gen:
            st.info("Es sind noch keine generierten Fahrten gespeichert – zuerst im "
                    "Generator-Tab das Jahr generieren.")
            return
        settings_like = {"wohnort": ""}
        try:
            from database.settings import load_settings
            settings_like = load_settings(username)
        except DatabaseError:
            pass
        with st.spinner("Wende Korrekturen an…"):
            gen, meldungen = wende_hu_korrekturen_an(
                gen, fahrzeuge, correction_data,
                pd.DataFrame(columns=["Ort", "Zweck"]),
                settings_like.get("wohnort", ""))
            for m in meldungen:
                st.write(m)
            try:
                from database.fahrten import save_month
                for (j, m), data in gen.items():
                    save_month(username, j, m, data["data"])
                save_hu_corrections(username, correction_data)
                st.success("Kilometerstände und HU-Fahrten wurden erfolgreich korrigiert!")
                st.toast("Korrekturen in Cloud gespeichert!")
            except DatabaseError as e:
                st.error(str(e))