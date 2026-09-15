import streamlit as st

from ui.stammdaten import render as render_stammdaten
from ui.fahrzeuge_ui import render as render_fahrzeuge
from ui.fahrten_ui import render as render_fahrten
from ui.pruefung_ui import render as render_pruefung
from ui.export_ui import render as render_export


def render_main():
    username = st.session_state.get("username", "")

    with st.sidebar:
        st.markdown(f"**Angemeldet als:** {username}")
        if st.button("🚪 Abmelden"):
            for k in ("logged_in", "username", "force_pw_change_flow", "temp_username"):
                st.session_state.pop(k, None)
            st.session_state.logged_in = False
            st.rerun()

    st.title("🚗 Fahrtenbuch Generator")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 Stammdaten", "🚗 Fahrzeuge & Zeiträume",
        "📝 Fahrten erfassen", "🔍 Plausibilitätsprüfung", "📄 Export & HU",
    ])
    with tab1: render_stammdaten(username)
    with tab2: render_fahrzeuge(username)
    with tab3: render_fahrten(username)
    with tab4: render_pruefung(username)
    with tab5: render_export(username)