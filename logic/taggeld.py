"""Taggeld-Berechnung: Nur bei dienstlicher Auswaertstaetigkeit (km_d > 0).
Privatfahrten, Sonntage, Feiertage und reine Arbeitswege bekommen kein Taggeld."""
from logic.constants import DEFAULT_TAGGELD_PARAMS
from logic.helpers import _safe_float, _safe_int


def berechne_taggeld_betrag(dauer_minuten, params=None, km_dienstlich=None):
    """Kernfunktion: Taggeld als float (auf 2 Stellen gerundet).
    Wird km_dienstlich uebergeben und ist 0 -> 0.00 (keine Auswaertstaetigkeit)."""
    if km_dienstlich is not None and _safe_int(km_dienstlich) <= 0:
        return 0.0
    if params is None:
        params = DEFAULT_TAGGELD_PARAMS
    min_st = params.get('min_stunden', 5)
    basis = params.get('basis', 10.00)
    stufung = params.get('stufung', 2.50)
    max_betrag = params.get('max_betrag', 30.00)
    max_st = params.get('max_stunden', 13)

    stunden = dauer_minuten / 60.0
    if stunden < min_st:
        return 0.0
    if stunden >= max_st:
        return round(max_betrag, 2)
    return round(min(basis + (stunden - min_st) * stufung, max_betrag), 2)


def taggeld_fuer_fahrt(dauer_minuten, km_dienstlich=0, params=None):
    """Convenience fuer Einzelfahrten: Nur km_d > 0 erzeugt Taggeld."""
    return berechne_taggeld_betrag(dauer_minuten, params, km_dienstlich=km_dienstlich)


def berechne_taggeld(dauer_minuten, params=None) -> str:
    """Anzeige-Variante ohne km-Pruefung (Abwaertskompatibilitaet)."""
    return f"{berechne_taggeld_betrag(dauer_minuten, params):.2f}".replace('.', ',')


def taggeld_params_aus_settings(user_info: dict) -> dict:
    return {
        "min_stunden": _safe_float(user_info.get("taggeld_min_stunden"), 5),
        "basis": _safe_float(user_info.get("taggeld_basis"), 10.00),
        "stufung": _safe_float(user_info.get("taggeld_stufung"), 2.50),
        "max_betrag": _safe_float(user_info.get("taggeld_max_betrag"), 30.00),
        "max_stunden": _safe_float(user_info.get("taggeld_max_stunden"), 13),
    }
