import hashlib
import secrets

from config import supabase
from database import DatabaseError


def _hash(password: str) -> str:
    # Kompatibilität mit Bestands-DB (SHA256). Bei nächster Migration: bcrypt!
    return hashlib.sha256(password.encode()).hexdigest()


def add_user(username, password, email) -> bool:
    try:
        supabase.table("users").insert({
            "username": username.strip().lower(),
            "password": _hash(password),
            "email": email.strip().lower(),
            "force_pw_change": True,
        }).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"Registrierung fehlgeschlagen (Benutzername existiert bereits?): {e}") from e


def verify_user(username, password):
    try:
        r = (supabase.table("users").select("username, password, email, force_pw_change")
             .eq("username", username.strip().lower())
             .eq("password", _hash(password)).execute())
        return (True, r.data[0]) if r.data else (False, {})
    except Exception as e:
        raise DatabaseError(f"Login fehlgeschlagen: {e}") from e


def get_user_email(username) -> str:
    """Liefert die hinterlegte E-Mail (für Passwort-Reset), sonst ''. """
    try:
        r = (supabase.table("users").select("username, email")
             .eq("username", username.strip().lower()).execute())
        if not r.data:
            return ""
        return r.data[0].get("email") or ""
    except Exception as e:
        raise DatabaseError(f"Benutzersuche fehlgeschlagen: {e}") from e


def all_usernames() -> list:
    try:
        r = supabase.table("users").select("username").execute()
        return [row["username"] for row in (r.data or [])]
    except Exception as e:
        raise DatabaseError(f"Benutzerliste fehlgeschlagen: {e}") from e


def set_user_email(username, email) -> bool:
    try:
        supabase.table("users").update({"email": email.strip().lower()}) \
            .eq("username", username).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"E-Mail-Update fehlgeschlagen: {e}") from e


def update_password(username, new_password, force_change=None) -> bool:
    try:
        data = {"password": _hash(new_password)}
        if force_change is not None:
            data["force_pw_change"] = bool(force_change)
        (supabase.table("users").update(data)
         .eq("username", username.strip().lower()).execute())
        return True
    except Exception as e:
        raise DatabaseError(f"Passwort-Update fehlgeschlagen: {e}") from e


def reset_password_by_username(username, new_plain_password) -> str:
    """Wie Original: neues Passwort setzen + force_pw_change=True. Gibt E-Mail zurück."""
    email = get_user_email(username)
    if not email:
        raise DatabaseError("Für diesen Account ist keine E-Mail hinterlegt.")
    update_password(username, new_plain_password, force_change=True)
    return email