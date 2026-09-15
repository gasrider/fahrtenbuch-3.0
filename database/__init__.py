"""Paket-Markierung + Fehler-Typen der Datenbank-Schicht."""

class DatabaseError(Exception):
    """Fehler aus der Datenbank-Schicht – wird in der UI angezeigt."""