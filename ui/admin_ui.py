"""Admin-Bereich: SMTP, Passwort-Reset, E-Mail-Verwaltung, Datenansicht."""
import hashlib
import os

import pandas as pd
import streamlit as st

from database import DatabaseError
from database.system_config import load_system_config
from database.system_config import save_system_config
from database.users import all_usernames
from database.users import update_password
from database.users import set_user_email
from database.users import get_user_email
from database.settings import load_settings
from database.fahrzeuge import load_fahrzeuge
from services.email import send_reset_email


def _secret(key):
    try:
        return st.secrets.get(key, "")
    except Exception:
        return ""


def _is_admin(username):
    if username == "christian mayerhofer":
        return True
    extra = str(_secret("ADMIN_USERNAMES") or "")
    namen = [a.strip().lower() for a in extra.split(",") if a.strip()]
    return username in namen


def _zeige_smtp(username):
    st.subheader("E-Mail / SMTP")
    st.caption("Zugangsdaten fuer den E-Mail-Versand (Passwort-Reset).")
    try:
        cfg = load_system_config()
    except DatabaseError as e:
        st.error(str(e))
        return
    c1, c2 = st.columns(2)
    with c1:
        server = st.text_input("SMTP Server", value=str(cfg.get("smtp_server") or ""))
        port = st.text_input("Port", value=str(cfg.get("smtp_port") or "465"))
        user = st.text_input("SMTP Benutzer / E-Mail", value=str(cfg.get("smtp_user") or ""))
    with c2:
        pw = st.text_input("SMTP Passwort (leer = unveraendert)",
                           type="password", value="")
        von = st.text_input("Absendername",
                            value=str(cfg.get("smtp_from_name") or "Fahrtenbuch System"))
    if st.button("SMTP speichern"):
        daten = {
            "smtp_server": server.strip(),
            "smtp_port": port.strip(),
            "smtp_user": user.strip(),
            "smtp_from_name": von.strip(),
            "smtp_password": pw or str(cfg.get("smtp_password") or ""),
        }
        try:
            if save_system_config(daten):
                st.success("SMTP-Einstellungen gespeichert!")
        except DatabaseError as e:
            st.error(str(e))
    st.markdown("---")
    st.subheader("Test-E-Mail")
    ziel = st.text_input("Test-E-Mail an")
    if st.button("Test-E-Mail senden"):
        if not ziel or "@" not in ziel:
            st.error("Bitte eine gueltige E-Mail-Adresse eingeben.")
        else:
            neu = {
                "server": server.strip() or str(cfg.get("smtp_server") or ""),
                "port": port.strip() or "465",
                "user": user.strip() or str(cfg.get("smtp_user") or ""),
                "password": pw or str(cfg.get("smtp_password") or ""),
                "from_name": von.strip() or "Fahrtenbuch System",
            }
            ok = send_reset_email(ziel, "TEST-PASSWORT-1234", smtp_settings=neu)
            if ok:
                st.success("Test-E-Mail gesendet! Auch Spam-Ordner pruefen.")
            else:
                st.error("Senden fehlgeschlagen. SMTP-Daten und App-Passwort pruefen.")


def _zeige_benutzer(username):
    st.subheader("Benutzerverwaltung")
    try:
        users = all_usernames()
    except DatabaseError as e:
        st.error(str(e))
        return
    if not users:
        st.info("Keine Benutzer vorhanden.")
        return
    sel = st.selectbox("User auswaehlen", users)
    st.markdown("**Passwort zuruecksetzen**")
    new_pw = st.text_input("Neues Passwort", type="password", key="admin_pw")
    if st.button("Passwort aendern"):
        if new_pw:
            update_password(sel, new_pw, force_change=True)
            st.success(f"Passwort fuer {sel} geaendert. User muss bei naechstem "
                       "Login ein neues Passwort setzen.")
        else:
            st.warning("Bitte ein Passwort eingeben.")
    st.markdown("---")
    st.subheader("E-Mail-Adresse")
    try:
        cur = get_user_email(sel)
    except DatabaseError as e:
        st.error(str(e))
        cur = ""
    mail = st.text_input("E-Mail eintragen/aendern", value=cur, key="admin_mail")
    if st.button("E-Mail speichern"):
        if mail and "@" in mail:
            set_user_email(sel, mail)
            st.success("E-Mail gespeichert.")
        else:
            st.error("Bitte eine gueltige E-Mail-Adresse eingeben.")


def _zeige_daten(username):
    st.subheader("Daten ansehen")
    try:
        users = all_usernames()
    except DatabaseError as e:
        st.error(str(e))
        return
    if not users:
        st.info("Keine Benutzer vorhanden.")
        return
    sel = st.selectbox("User-Daten anzeigen", users, key="admin_data")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Stammdaten:**")
        try:
            s = load_settings(sel)
            if s:
                st.json(s)
            else:
                st.info("Keine Stammdaten.")
        except DatabaseError as e:
            st.error(str(e))
    with c2:
        st.markdown("**Fahrzeuge:**")
        try:
            fz = load_fahrzeuge(sel)
            if not fz.empty:
                st.dataframe(fz, use_container_width=True)
            else:
                st.info("Keine Fahrzeuge.")
        except DatabaseError as e:
            st.error(str(e))


def render(username):
    st.subheader("Admin-Bereich")
    if not _is_admin(username):
        st.info("Kein Admin-Zugang.")
        return
    t1, t2, t3 = st.tabs(["SMTP / E-Mail", "Benutzer", "Daten"])
    with t1:
        _zeige_smtp(username)
    with t2:
        _zeige_benutzer(username)
    with t3:
        _zeige_daten(username)
