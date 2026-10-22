"""Orte (Kundenstopps, Werkstätten), deren Distanzen vom Wohnort und die
Distanz-Matrix (echte Ort-zu-Ort Fahrstrecken von der Online-Karte)."""
from config import supabase
from database import DatabaseError


def load_orte(username) -> list:
    try:
        r = (supabase.table("orte").select("ort")
             .eq("username", username).order("ort").execute())
        return [row["ort"] for row in (r.data or [])]
    except Exception as e:
        raise DatabaseError(f"Orte laden fehlgeschlagen: {e}") from e


def save_orte(username, orte_list) -> bool:
    try:
        supabase.table("orte").delete().eq("username", username).execute()
        clean = [{"username": username, "ort": str(o).strip()}
                 for o in orte_list if str(o).strip()]
        for i in range(0, len(clean), 500):
            supabase.table("orte").insert(clean[i:i + 500]).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"Orte speichern fehlgeschlagen: {e}") from e


def lade_distanzen(username) -> dict:
    """Liefert {ort: km_einfach} für alle gepflegten Distanzen."""
    try:
        r = (supabase.table("orte_distanz").select("ort, km_einfach")
             .eq("username", username).execute())
        return {row["ort"]: int(row["km_einfach"] or 0) for row in (r.data or [])}
    except Exception as e:
        raise DatabaseError(f"Distanzen laden fehlgeschlagen: {e}") from e


def speichere_distanzen(username, distanzen: dict) -> bool:
    """Überschreibt alle Distanzen. distanzen: {ort: km_einfach}"""
    try:
        supabase.table("orte_distanz").delete().eq("username", username).execute()
        rows = [{"username": username, "ort": str(o).strip(),
                 "km_einfach": int(k or 0)}
                for o, k in distanzen.items() if str(o).strip()]
        for i in range(0, len(rows), 500):
            supabase.table("orte_distanz").insert(rows[i:i + 500]).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"Distanzen speichern fehlgeschlagen: {e}") from e


# ==================== Online-Karten-Cache ====================
# ort_koordinaten: Geocoding-Ergebnisse (Ort -> lat/lon)
# distanz_matrix:  echte Fahrstrecken zwischen zwei Orten (in km)


def lade_geo_cache(username) -> dict:
    """{ort_key: {"lat", "lon", "display_name"}} - ort_key = klein+getrimmt."""
    try:
        r = (supabase.table("ort_koordinaten")
             .select("ort_key, lat, lon, display_name")
             .eq("username", username).execute())
        out = {}
        for row in (r.data or []):
            if row.get("lat") is None or row.get("lon") is None:
                continue
            out[str(row["ort_key"]).strip().lower()] = {
                "lat": float(row["lat"]), "lon": float(row["lon"]),
                "display_name": str(row.get("display_name") or "")}
        return out
    except Exception as e:
        raise DatabaseError(f"Geo-Cache laden fehlgeschlagen: {e}") from e


def speichere_geo_cache(username, koordinaten: dict) -> bool:
    """Überschreibt den Geo-Cache des Users.
    koordinaten: {ort_key: {"lat", "lon", "display_name", "ort"}}"""
    try:
        supabase.table("ort_koordinaten").delete().eq(
            "username", username).execute()
        rows = []
        for k, e in (koordinaten or {}).items():
            if e.get("lat") is None or e.get("lon") is None:
                continue
            rows.append({"username": username,
                         "ort": str(e.get("ort") or k),
                         "ort_key": str(k).strip().lower(),
                         "lat": float(e["lat"]), "lon": float(e["lon"]),
                         "display_name": str(e.get("display_name") or "")})
        for i in range(0, len(rows), 500):
            supabase.table("ort_koordinaten").insert(
                rows[i:i + 500]).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"Geo-Cache speichern fehlgeschlagen: {e}") from e


def lade_distanz_matrix(username) -> dict:
    """{(key_a, key_b): km} mit key_a <= key_b (immer sortiert)."""
    try:
        r = (supabase.table("distanz_matrix")
             .select("key_a, key_b, km").eq("username", username).execute())
        out = {}
        for row in (r.data or []):
            ka = str(row["key_a"]).strip().lower()
            kb = str(row["key_b"]).strip().lower()
            if ka > kb:
                ka, kb = kb, ka
            try:
                km = int(row["km"] or 0)
            except (TypeError, ValueError):
                continue
            if km > 0:
                out[(ka, kb)] = km
        return out
    except Exception as e:
        raise DatabaseError(f"Distanz-Matrix laden fehlgeschlagen: {e}") from e


def lade_matrix_zeilen(username) -> list:
    """Rohzeilen für den Editor: [{ort_a, ort_b, km, quelle}] alphabetisch."""
    try:
        r = (supabase.table("distanz_matrix")
             .select("ort_a, ort_b, km, quelle").eq("username", username)
             .order("ort_a").order("ort_b").execute())
        zeilen = []
        for row in (r.data or []):
            try:
                km = int(row["km"] or 0)
            except (TypeError, ValueError):
                continue
            zeilen.append({"ort_a": str(row["ort_a"] or ""),
                           "ort_b": str(row["ort_b"] or ""),
                           "km": km,
                           "quelle": str(row.get("quelle") or "osrm")})
        return zeilen
    except Exception as e:
        raise DatabaseError(f"Distanz-Matrix laden fehlgeschlagen: {e}") from e


def speichere_distanz_matrix(username, zeilen: list) -> bool:
    """Überschreibt die Distanz-Matrix des Users.
    zeilen: [{ort_a, ort_b, km, quelle}]"""
    try:
        supabase.table("distanz_matrix").delete().eq(
            "username", username).execute()
        rows = []
        for z in (zeilen or []):
            a = str(z.get("ort_a") or "").strip()
            b = str(z.get("ort_b") or "").strip()
            km = int(z.get("km") or 0)
            if not a or not b or km <= 0 or a.lower() == b.lower():
                continue
            ka, kb = a.lower(), b.lower()
            if ka > kb:
                ka, kb = kb, ka
                a, b = b, a
            rows.append({"username": username, "ort_a": a, "ort_b": b,
                         "key_a": ka, "key_b": kb, "km": km,
                         "quelle": str(z.get("quelle") or "osrm")})
        for i in range(0, len(rows), 500):
            supabase.table("distanz_matrix").insert(
                rows[i:i + 500]).execute()
        return True
    except Exception as e:
        raise DatabaseError(f"Distanz-Matrix speichern fehlgeschlagen: {e}") from e
