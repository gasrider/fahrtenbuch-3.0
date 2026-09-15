import streamlit as st

st.set_page_config(page_title="Fahrtenbuch Generator v7.0 – Multi-User", layout="wide")

from ui.login import render_login
from ui.app_main import render_main

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

if not st.session_state.logged_in:
    render_login()
else:
    render_main()