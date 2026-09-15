"""Login, Registrierung, Passwort vergessen, erzwungener Passwortwechsel."""
import streamlit as st

from database import DatabaseError
from database.users import add_user, verify_user, find_user, update_password
from services.email import send_reset_email, generate_random_password


def render_login():
    st.session_state.setdefault("logged_in", False)
    st.session_state.setdefault("username", "")
    st.session_state.setdefault("force_pw_change_flow", False)

    # Erzwungener Passwortwechsel direkt nach Login
    if st.session_state.get("force_pw_change_flow"):
        st.title("🔑 Passwort ändern")
        st.warning("Sicherheitshinweis: Sie müssen Ihr Passwort vor der ersten Nutzung ändern!")
        with st.form("force_change_form"):
            p1 = st.text_input("Neues Passwort", type="password")
            p2 = st.text_input("Neues Passwort wiederholen", type="password")
            if st.form_submit_button("Passwort ändern", type="primary"):
                if len(p1) < 8:
                    st.error("Passwort muss mindestens 8 Zeichen lang sein.")
                elif p1 != p2:
                    st.error("Passwörter stimmen nicht überein.")
                else:
                    try:
                        update_password(st.session_state["temp_username"], p1,
                                        force_change=False)
                        st.session_state.logged_in = True
                        st.session_state.username = st.session_state["temp_username"]
                        st.session_state.force_pw_change_flow = False
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
        nu = st.text_input("Benutzername", key="reg_user")
        ne = st.text_input("E-Mail", key="reg_email")
        np1 = st.text_input("Passwort (min. 8 Zeichen)", type="password", key="reg_pw1")
        np2 = st.text_input("Passwort wiederholen", type="password", key="reg_pw2")
        if st.button("Registrieren"):
            if not nu or not ne or not np1:
                st.error("Bitte alle Felder ausfüllen.")
            elif np1 != np2:
                st.error("Passwörter stimmen nicht überein.")
            elif len(np1) < 8:
                st.error("Passwort muss mindestens 8 Zeichen lang sein.")
            else:
                try:
                    add_user(nu, np1, ne)
                    st.success("Registrierung erfolgreich! Sie können sich jetzt anmelden.")
                except DatabaseError as e:
                    st.error(str(e))

    with tab3:
        fu = st.text_input("Benutzername", key="pw_user")
        fe = st.text_input("E-Mail", key="pw_email")
        if st.button("Neues Passwort per E-Mail anfordern"):
            try:
                found = find_user(fu, fe)
                if not found:
                    st.error("Kein Benutzer mit dieser Kombination gefunden.")
                else:
                    new_pw = generate_random_password()
                    update_password(fu, new_pw, force_change=True)
                    if send_reset_email(fe, new_pw):
                        st.success("E-Mail gesendet! Bitte Postfach prüfen.")
                    else:
                        st.error("E-Mail-Versand fehlgeschlagen. "
                                 "Bitte Administrator informieren (SMTP-Einstellungen).")
            except DatabaseError as e:
                st.error(str(e))