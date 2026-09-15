"""Ostern, Feiertage (AT), Datumshelfer."""
from datetime import date, timedelta

from logic.constants import MONATE


def easter_sunday(year):
    a = year % 19; b = year // 100; c = year % 100; d = b // 4; e = b % 4
    f = (b + 8) // 25; g = (b - f + 1) // 3; h = (19 * a + b - d - g + 15) % 30
    i = c // 4; k = c % 4; l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    return date(year, (h + l - 7 * m + 114) // 31, ((h + l - 7 * m + 114) % 31) + 1)


def austria_holidays(year):
    E = easter_sunday(year)
    return {
        date(year, 1, 1), date(year, 1, 6), date(year, 5, 1),
        date(year, 8, 15), date(year, 10, 26), date(year, 11, 1),
        date(year, 12, 8), date(year, 12, 25), date(year, 12, 26),
        E + timedelta(days=1), E + timedelta(days=39),
        E + timedelta(days=50), E + timedelta(days=60),
    }


def monatsname(monat):
    return MONATE[monat - 1]


def ist_arbeitstag(d: date) -> bool:
    return d.weekday() < 5 and d not in austria_holidays(d.year)