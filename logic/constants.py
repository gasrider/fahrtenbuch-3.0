"""Fachliche Konstanten."""

MONATE = ["Jänner", "Februar", "März", "April", "Mai", "Juni",
          "Juli", "August", "September", "Oktober", "November", "Dezember"]

WOCHENTAGE_KURZ = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

IGNORE_ROUTES = ["Keine Fahrt", "Sonntag", "Feiertag", "Urlaub"]

DEFAULT_TAGGELD_PARAMS = {
    "min_stunden": 5, "basis": 10.00, "stufung": 2.50,
    "max_betrag": 30.00, "max_stunden": 13,
}

DEFAULT_KM_GELD = 0.42

DEFAULT_VEHICLES_COLUMNS = ["id", "bezeichnung", "kennzeichen", "start_km_vorjahr",
                            "privat_km_min", "privat_km_max", "dienstlich_quote"]

FAHRTEN_COLUMNS = ["datum", "fahrzeug", "route", "abf", "ank", "dauer",
                   "km_d", "km_p", "abfahrt_km"]