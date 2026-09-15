"""Login, Registrierung, Passwort vergessen (nur Benutzername), erzwungener Passwortwechsel."""
import streamlit as st
import secrets

from database import DatabaseError
from database.users import (add_user, verify_user, update_password,
                            reset_password_by_username)
from services.email import send_reset_email


def render_login():
    st.session_state.setdefault("logged_in", False)
    st.session_state.setdefault("username", "")
    st.session_state.setdefault("force_pw_change_flow", False)

    if st.session_state.get("force_pw_change_flow"):
        st.title("🔑 Passwort ändern")
        st.warning("Sicherheitshinweis: Sie müssen Ihr Passwort vor der ersten Nutzung ändern!")
        with st.form("force_change_form"):
            p1 = st.text_input("Neues Passwort", type="password")
            p2 = st.text_input("Neues Passwort bestätigen", type="password")
            if st.form_submit_button("Passwort speichern und einloggen"):
                if p1 != p2:
                    st.error("Die Passwörter stimmen nicht überein!")
                elif len(p1) < 4:
                    st.error("Passwort muss mindestens 4 Zeichen haben.")
                else:
                    try:
                        update_password(st.session_state["temp_username"], p1, force_change=False)
                        st.session_state.logged_in = True
                        st.session_state.username = st.session_state["temp_username"]
                        st.session_state.force_pw_change_flow = False
                        st.success("Passwort erfolgreich geändert! Willkommen.")
                        st.rerun()
                    except DatabaseError as e:
                        st.error(str(e))
        return

    st.title("🚗 Fahrtenbuch Login")
    tab1, tab2, tab3 = st.tabs(["Anmelden", "Registrieren", "Passwort vergessen"])

    with tab1:
        user = st.text_input("Benutzername", key="login_user")
        pw = st.text_input("Passwort", type="password", key="login_pw")
        if st.button("Login", type="primary"):
            try:
                ok, user_data = verify_user(user, pw)
            except DatabaseError as e:
                st.error(str(e))
            else:
                if ok:
                    if user_data.get("force_pw_change", False):
                        st.session_state["temp_username"] = user_data["username"]
                        st.session_state.force_pw_change_flow = True
                        st.rerun()
                    else:
                        st.session_state.logged_in = True
                        st.session_state.username = user.strip().lower()
                        st.rerun()
                else:
                    st.error("Falsche Zugangsdaten")

    with tab2:
        nu = st.text_input("Neuer Benutzername", key="reg_user")
        ne = st.text_input("Ihre E-Mail-Adresse", key="reg_email")
        np1 = st.text_input("Neues Passwort", type="password", key="reg_pw")
        if st.button("Account erstellen"):
            if not ne or "@" not in ne:
                st.error("Bitte geben Sie eine gültige E-Mail-Adresse an.")
            else:
                try:
                    add_user(nu, np1, ne)
                    st.success("Account erstellt! Bitte loggen Sie sich ein.")
                except DatabaseError as e:
                    st.error(str(e))

    with tab3:
        st.info("Geben Sie Ihren Benutzernamen ein. Das System sendet Ihnen dann sofort "
                "ein neues, sicheres Passwort an Ihre hinterlegte E-Mail-Adresse.")
        ru = st.text_input("Ihr Benutzername", key="reset_user_req")
        if st.button("📧 Neues Passwort anfordern"):
            if not ru:
                st.warning("Bitte Benutzernamen eingeben.")
            else:
                try:
                    new_pw = secrets.token_urlsafe(8)
                    email = reset_password_by_username(ru, new_pw)
                    if send_reset_email(email, new_pw):
                        st.success("Ein neues Passwort wurde an Ihre E-Mail-Adresse gesendet! "
                                   "Bitte prüfen Sie auch Ihren Spam-Ordner.")
                    else:
                        st.error("Fehler beim Senden der E-Mail. Bitte kontaktieren Sie den Admin.")
                except DatabaseError as e:
                    st.error(str(e))