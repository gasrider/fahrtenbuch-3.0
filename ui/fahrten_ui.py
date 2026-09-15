import streamlit as st
import pandas as pd

from database import DatabaseError
from database.fahrten import load_month, save_month
from database.settings import load_settings
from database.fahrzeuge import load_fahrzeuge
from database.zeitraeume import load_zeitraeume
from logic.fahrten import baue_monats_vorlage, recalc_abfahrt_km
from logic.helpers import _parse_date_iso, _safe_int
from ui.fahrten_spalten import FAHRTEN_COLUMN_CONFIG, display_columns


def _init_df():
    return pd.DataFrame(columns=display_columns())


def _zu_display_df(df):
    """DB-Daten → Editor-Darstellung (Datum als date, ohne fahrzeug_id)."""
    if df is None or df.empty:
        return _init_df()
    df = df.copy()
    df["datum"] = pd.to_datetime(df["datum"]).dt.date
    cols = display_columns()
    return df[[c for c in cols if c in df.columns]]


def render(username):
    st.subheader("📝 Fahrten erfassen")
    try:
        settings = load_settings(username)
        fahrzeuge = load_fahrzeuge(username)
        zeitraeume = load_zeitraeume(username)
    except DatabaseError as e:
        st.error(str(e)); return

    c1, c2, c3 = st.columns([1, 1, 2])
    jahr = c1.number_input("Jahr", min_value=2000, max_value=2100,
                           value=pd.Timestamp.now().year, step=1)
    monat = c2.selectbox("Monat", range(1, 13),
                         format_func=lambda m: ["Jänner","Februar","März","April","Mai","Juni",
                                                "Juli","August","September","Oktober",
                                                "November","Dezember"][m-1])

    try:
        vorhanden = load_month(username, jahr, monat)
    except DatabaseError as e:
        st.error(str(e)); return

    if vorhanden is not None and not vorhanden.empty:
        st.info(f"Für {monat:02d}/{jahr} sind bereits {len(vorhanden)} Einträge gespeichert.")

    if "vorlage_nonce" not in st.session_state:
        st.session_state.vorlage_nonce = 0

    if st.button("🧱 Arbeitstage-Vorlage erzeugen (überschreibt den Editor-Inhalt)"):
        vorlage = baue_monats_vorlage(jahr, monat, settings, fahrzeuge, zeitraeume)
        st.session_state[f"vorlage_{jahr}_{monat}"] = vorlage
        st.session_state.vorlage_nonce += 1
        st.rerun()

    quelle = st.session_state.get(f"vorlage_{jahr}_{monat}")
    if quelle is not None:
        basis = _zu_display_df(quelle)
    elif vorhanden is not None and not vorhanden.empty:
        basis = _zu_display_df(vorhanden)
    else:
        basis = _init_df()

    st.caption("⚠️ Diese Tabelle muss mit den REAL gefahrenen Werten übereinstimmen. "
               "Die Vorlage ist nur ein Starting Point – bitte alle Zeiten/KM prüfen und korrigieren.")
    edited = st.data_editor(
        basis,
        column_config=FAHRTEN_COLUMN_CONFIG,
        num_rows="dynamic",
        use_container_width=True,
        key=f"fahrten_editor_{jahr}_{monat}_{st.session_state.vorlage_nonce}",
    )

    if st.button("💾 Monat speichern", type="primary"):
        try:
            df = edited.copy()
            df = df[df["datum"].notna()]
            if df.empty:
                st.warning("Keine Zeilen zum Speichern.")
                return
            # Fahrzeugname → ID auflösen
            name_to_id = {str(r["bezeichnung"]).strip(): _safe_int(r["id"])
                          for _, r in fahrzeuge.iterrows() if pd.notna(r["id"])}
            df["fahrzeug_id"] = df["fahrzeug"].map(
                lambda n: name_to_id.get(str(n).strip()))
            unbekannt = df[df["fahrzeug_id"].isna()]["fahrzeug"].dropna().unique()
            if len(unbekannt):
                st.warning(f"Fahrzeug ohne Zuordnung ignoriert: {', '.join(map(str, unbekannt))}")
            df = df[df["fahrzeug_id"].notna()]
            df["datum"] = df["datum"].map(lambda d: _parse_date_iso(d))
            df = recalc_abfahrt_km(df, fahrzeuge)
            save_month(username, jahr, monat, df)
            st.success(f"{len(df)} Fahrten für {monat:02d}/{jahr} gespeichert.")
            st.rerun()
        except DatabaseError as e:
            st.error(str(e))