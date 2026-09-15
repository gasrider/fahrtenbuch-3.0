"""Taggeld-Berechnung (linear mit Deckel)."""
from logic.constants import DEFAULT_TAGGELD_PARAMS
from logic.helpers import _safe_float


def berechne_taggeld_betrag(dauer_minuten, params=None) -> float:
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


def berechne_taggeld(dauer_minuten, params=None) -> str:
    return f"{berechne_taggeld_betrag(dauer_minuten, params):.2f}".replace('.', ',')


def taggeld_params_aus_settings(user_info: dict) -> dict:
    return {
        "min_stunden": _safe_float(user_info.get("taggeld_min_stunden"), 5),
        "basis": _safe_float(user_info.get("taggeld_basis"), 10.00),
        "stufung": _safe_float(user_info.get("taggeld_stufung"), 2.50),
        "max_betrag": _safe_float(user_info.get("taggeld_max_betrag"), 30.00),
        "max_stunden": _safe_float(user_info.get("taggeld_max_stunden"), 13),
    }