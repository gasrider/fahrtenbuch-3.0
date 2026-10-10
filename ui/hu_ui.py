"""HU-Verwaltung: Eintraege bearbeiten/loeschen + optionale Fahrten-Anpassung."""
import pandas as pd
import streamlit as st

from database import DatabaseError
from database.fahrzeuge import load_fahrzeuge
from database.jahres_start_km import get_or_create_anchor, set_start_km
from database.orte import load_orte
from database.hu_corrections import load_hu_raw, save_hu_corrections
from database.fahrten import load_year, save_month
from database.settings import load_settings
from logic.helpers import _safe_int, _parse_date_iso
from logic.hu_korrektur import wende_hu_korrekturen_an


def render(username):
    st.subheader("HU-Korrekturen")
    st.caption("Zeilen koennen geaendert, ueber das Kaestchen links geloescht oder neu "
               "angelegt werden. Stopps: Orte mit Komma getrennt eintragen.")
    try:
        fahrzeuge = load_fahrzeuge(username)
        orte = load_orte(username)
        raw = load_hu_raw(username)
    except DatabaseError as e:
        st.error(str(e))
        return

    optionen = {}
    for _, r in fahrzeuge.iterrows():
        if pd.notna(r.get("id")):
            name = str(r.get("bezeichnung", "")).strip()
            if name and name.lower() not in ("none", "nan"):
                optionen[name] = _safe_int(r["id"])
    id_zu_name = {v: k for k, v in optionen.items()}
    if not optionen:
        st.warning("Zuerst Fahrzeuge anlegen.")
        return

    rows = []
    for r in raw:
        fid = r.get("fahrzeug_id")
        rows.append({
            "Fahrzeug": id_zu_name.get(_safe_int(fid, default=-1), ""),
            "Datum der HU": r.get("datum") or None,
            "Kilometerstand bei HU": _safe_int(r.get("km_at_hu")),
            "Werkstattort": str(r.get("werkstattort", "") or ""),
            "Stopps vor HU": str(r.get("stopps_vor_hu", "") or ""),
            "Stopps nach HU": str(r.get("stopps_nach_hu", "") or ""),
        })
    basis = pd.DataFrame(rows, columns=["Fahrzeug", "Datum der HU",
                                        "Kilometerstand bei HU", "Werkstattort",
                                        "Stopps vor HU", "Stopps nach HU"])
    if not basis.empty:
        basis["Datum der HU"] = pd.to_datetime(basis["Datum der HU"],
                                               errors="coerce").dt.date

    werkstatt_orte = sorted(orte) if orte else []
    edited = st.data_editor(
        basis, num_rows="dynamic", use_container_width=True, key="hu_editor",
        column_config={
            "Fahrzeug": st.column_config.SelectboxColumn(
                "Fahrzeug", options=sorted(optionen.keys()), required=True),
            "Datum der HU": st.column_config.DateColumn(
                "Datum der HU", format="DD.MM.YYYY", required=True),
            "Kilometerstand bei HU": st.column_config.NumberColumn(
                "Kilometerstand bei HU", min_value=0, step=1, required=True),
            "Werkstattort": st.column_config.SelectboxColumn(
                "Werkstattort", options=werkstatt_orte),
            "Stopps vor HU": st.column_config.TextColumn(
                "Stopps vor HU", max_chars=300,
                help="Orte mit Komma getrennt, z. B.: Straßwalchen,Neumarkt,Henndorf"),
            "Stopps nach HU": st.column_config.TextColumn(
                "Stopps nach HU", max_chars=300),
        })

    col1, col2 = st.columns(2)
    with col1:
        if st.button("HU-Eintraege speichern", type="primary"):
            daten, fehler = [], []
            for i, (_, z) in enumerate(edited.iterrows(), start=2):
                name = str(z.get("Fahrzeug") or "").strip()
                if not name or name.lower() in ("none", "nan"):
                    continue
                if name not in optionen:
                    fehler.append(f"Zeile {i}: Fahrzeug unbekannt")
                    continue
                datum = _parse_date_iso(z.get("Datum der HU"))
                if not datum:
                    fehler.append(f"Zeile {i}: Datum fehlt/ungueltig")
                    continue
                werk = str(z.get("Werkstattort") or "").strip()
                if not werk:
                    fehler.append(f"Zeile {i}: Werkstattort fehlt")
                    continue
                daten.append({
                    "fahrzeug_id": optionen[name],
                    "datum": datum,
                    "km_at_hu": _safe_int(z.get("Kilometerstand bei HU")),
                    "werkstattort": werk,
                    "stopps_vor_hu": str(z.get("Stopps vor HU") or "").strip(),
                    "stopps_nach_hu": str(z.get("Stopps nach HU") or "").strip(),
                })
            if fehler:
                st.error(" | ".join(fehler))
            else:
                try:
                    save_hu_corrections(username, daten)
                    st.success(f"{len(daten)} HU-Eintraege gespeichert.")
                    st.rerun()
                except DatabaseError as e:
                    st.error(str(e))
    with col2:
        st.caption("Nur Speichern aendert KEINE Fahrten. Erst wenn die Eintraege "
                   "stimmen, unten die Fahrten-Anpassung starten.")

    st.markdown("---")
    st.subheader("Fahrten an HU anpassen")
    st.warning("Nur EINMAL pro HU ausfuehren! Kilometer vor dem HU-Datum werden auf "
               "den HU-Stand skaliert, danach kompensierend (Jahressumme bleibt "
               "erhalten) und eine Werkstatt-Fahrt angelegt.")
    if st.button("Fahrten anpassen (Kilometer neu berechnen)"):
        if edited.empty:
            st.warning("Keine HU-Eintraege vorhanden.")
            return
        daten = []
        for _, z in edited.iterrows():
            name = str(z.get("Fahrzeug") or "").strip()
            datum = _parse_date_iso(z.get("Datum der HU"))
            werk = str(z.get("Werkstattort") or "").strip()
            if name not in optionen or not datum or not werk:
                continue
            vor = [s.strip() for s in str(z.get("Stopps vor HU") or "").split(",") if s.strip()]
            nach = [s.strip() for s in str(z.get("Stopps nach HU") or "").split(",") if s.strip()]
            daten.append({"fahrzeug_id": optionen[name], "datum": datum,
                          "km_at_hu": _safe_int(z.get("Kilometerstand bei HU")),
                          "werkstattort": werk,
                          "stopps_vor_hu": vor, "stopps_nach_hu": nach})
        if not daten:
            st.error("Keine gueltigen Eintraege (Fahrzeug, Datum, Werkstattort pruefen).")
            return
        try:
            jahre = sorted({int(d["datum"][:4]) for d in daten})
            gen = {}
            for j in jahre:
                for (jj, mm), dfm in load_year(username, j).items():
                    gen[(jj, mm)] = {"data": dfm}
            if not gen:
                st.info("Keine gespeicherten Fahrten gefunden - zuerst im Generator "
                        "generieren.")
                return
            settings = load_settings(username)
                        with st.spinner("Wende HU-Korrekturen an..."):
                fzg_hu = fahrzeuge
                if len(jahre) == 1:
                    anchor = get_or_create_anchor(username, jahre[0], fahrzeuge)
                    fzg_hu = fahrzeuge.copy()
                    fzg_hu["start_km_vorjahr"] = fzg_hu["id"].map(
                        lambda x: anchor.get(int(x)) if pd.notna(x) else None)
                gen, km_ende, meldungen = wende_hu_korrekturen_an(
                    gen, fzg_hu, daten, pd.DataFrame(columns=["Ort", "Zweck"]),
                    settings.get("wohnort", ""))
                for m in meldungen:
                    st.write(m)
                for (j, m), d in gen.items():
                    save_month(username, j, m, d["data"])
                for j in jahre:
                    set_start_km(username, j + 1, km_ende)
            st.success("Fahrten angepasst. Jahres-Endkilometer als Startwert gespeichert!")
        except DatabaseError as e:
            st.error(str(e))
