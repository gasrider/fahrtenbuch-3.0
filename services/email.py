"""E-Mail-Versand (Passwort-Reset & Testmail). SMTP zuerst aus DB, Fallback Secrets/Env."""
import os
import secrets
import smtplib
import string
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from database.system_config import load_system_config


def get_smtp_settings() -> dict:
    config = load_system_config()
    return {
        "server": config.get("smtp_server") or os.environ.get("SMTP_SERVER", ""),
        "port": str(config.get("smtp_port") or os.environ.get("SMTP_PORT", "465")),
        "user": config.get("smtp_user") or os.environ.get("SMTP_USER", ""),
        "password": config.get("smtp_password") or os.environ.get("SMTP_PASSWORD", ""),
        "from_name": config.get("smtp_from_name") or "Fahrtenbuch System",
    }


def generate_random_password(length=12) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw)):
            return pw


def send_reset_email(to_email, new_plain_password, smtp_settings=None) -> bool:
    """True bei Erfolg. smtp_settings kann einen Override (für Test-Mail) enthalten."""
    try:
        s = smtp_settings if smtp_settings else get_smtp_settings()
        if not all([s.get("server"), s.get("port"), s.get("user"), s.get("password")]):
            print("SMTP nicht konfiguriert (weder DB noch Umgebungsvariablen).")
            return False
        smtp_user = s["user"]
        msg = EmailMessage()
        msg['From'] = formataddr((s.get("from_name", "Fahrtenbuch System"), smtp_user))
        msg['To'] = to_email
        msg['Subject'] = "Ihr neues Passwort für das Fahrtenbuch"
        msg['Reply-To'] = smtp_user
        domain = smtp_user.split('@')[1] if '@' in smtp_user else 'localhost'
        msg['Message-ID'] = make_msgid(domain=domain)
        # Bewusst KEIN X-Priority-Header und KEIN HTML (Spam-Filter!).
        msg.set_content(f"""Hallo,

Sie haben ein neues Passwort fuer das Fahrtenbuch-System angefordert.

Ihr neues Passwort lautet: {new_plain_password}

Bitte aendern Sie dieses Passwort sofort nach dem ersten Login.

Viele Gruesse
{s.get('from_name', 'Fahrtenbuch System')}""", subtype='plain', charset='utf-8')

        if int(s["port"]) == 465:
            with smtplib.SMTP_SSL(s["server"], int(s["port"]), timeout=15) as server:
                server.login(smtp_user, s["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(s["server"], int(s["port"]), timeout=15) as server:
                server.ehlo(); server.starttls(); server.ehlo()
                server.login(smtp_user, s["password"])
                server.send_message(msg)
        return True
    except smtplib.SMTPAuthenticationError:
        print("SMTP-Login fehlgeschlagen! Benutzername/App-Passwort prüfen.")
        return False
    except Exception as e:
        print(f"Fehler beim E-Mail-Versand: {e}")
        return False