import streamlit as st

from ui.stammdaten import render as render_stammdaten
from ui.fahrten_ui import render as render_generator
from ui.fahrzeuge_ui import render as render_fahrzeuge
from ui.pruefung_ui import render as render_pruefung
from ui.export_ui import render as render_export


def render_main():
    username = st.session_state.get("username", "")
    with st.sidebar:
        st.success(f"Eingeloggt als: **{username}**")
        if st.button("Logout"):
            for k in ("logged_in", "username", "force_pw_change_flow", "temp_username",
                      "generated_months_data", "fahrten_df"):
                st.session_state.pop(k, None)
            st.session_state.logged_in = False
            st.rerun()
    st.title("🚗 Fahrtenbuch Generator v7.0 - Multi-User Edition")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 Stammdaten", "⚙️ Generator", "🚗 Fahrzeuge & Orte",
        "🔍 Plausibilitätsprüfung", "📄 Export & HU"])
    with tab1: render_stammdaten(username)
    with tab2: render_generator(username)
    with tab3: render_fahrzeuge(username)
    with tab4: render_pruefung(username)
    with tab5: render_export(username)