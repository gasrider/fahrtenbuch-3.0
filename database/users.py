import hashlib

from config import supabase
from database import DatabaseError


def _hash(password: str) -> str:
    # HINWEIS: SHA256 ohne Salt nur zur Kompatibilität mit der Bestands-DB.
    # Bei der nächsten Migration auf bcrypt umstellen!
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
        raise DatabaseError(f"Registrierung fehlgeschlagen: {e}") from e


def verify_user(username, password):
    try:
        r = (supabase.table("users")
             .select("username, password, email, force_pw_change")
             .eq("username", username.strip().lower())
             .eq("password", _hash(password)).execute())
        return (True, r.data[0]) if r.data else (False, {})
    except Exception as e:
        raise DatabaseError(f"Login fehlgeschlagen: {e}") from e


def find_user(username, email):
    try:
        r = (supabase.table("users").select("username, email")
             .eq("username", username.strip().lower())
             .eq("email", email.strip().lower()).execute())
        return r.data[0] if r.data else None
    except Exception as e:
        raise DatabaseError(f"Benutzersuche fehlgeschlagen: {e}") from e


def update_password(username, new_password, force_change=None) -> bool:
    """force_change: True/False setzt die Spalte, None lässt sie unverändert."""
    try:
        data = {"password": _hash(new_password)}
        if force_change is not None:
            data["force_pw_change"] = bool(force_change)
        (supabase.table("users").update(data)
         .eq("username", username.strip().lower()).execute())
        return True
    except Exception as e:
        raise DatabaseError(f"Passwort-Update fehlgeschlagen: {e}") from e