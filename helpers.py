"""Sichere Typumwandlungen und Hilfsfunktionen. Importiert NIEMALS streamlit oder supabase!"""
import re
import unicodedata
from datetime import date, datetime

import numpy as np
import pandas as pd


def _safe_float(val, default=0.0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        if isinstance(val, float):
            try:
                if np.isnan(val):
                    return default
            except (TypeError, ValueError):
                pass
        return float(val)
    if hasattr(val, 'item'):
        try:
            v = val.item()
            if v is None:
                return default
            if isinstance(v, float):
                try:
                    if np.isnan(v):
                        return default
                except (TypeError, ValueError):
                    pass
            return float(v)
        except (TypeError, ValueError):
            return default
    s = str(val).strip().replace(',', '.')
    if s.lower() in ("", "none", "nan", "nat"):
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        try:
            if pd.isna(val):
                return default
        except (TypeError, ValueError):
            pass
        else:
            return int(val)
    s = str(val).strip().replace('.', '').replace(',', '').lower()
    if s in ("", "none", "nan", "nat"):
        return default
    try:
        return int(s)
    except (ValueError, TypeError):
        return default


def _parse_date_iso(val):
    """Konvertiert Datumswerte sicher in ISO 'YYYY-MM-DD' oder None."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    if isinstance(val, (date, datetime)):
        return val.strftime("%Y-%m-%d")
    if hasattr(val, 'date') and callable(val.date):
        return val.date().strftime("%Y-%m-%d")
    s = str(val).strip()
    if not s or s.lower() in ("nat", "nan", "none", ""):
        return None
    if re.match(r'^\d{4}-\d{2}-\d{2}', s):
        return s[:10]
    m = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def to_date(val):
    """Wie _parse_date_iso, liefert aber ein date-Objekt oder None."""
    s = _parse_date_iso(val)
    return date.fromisoformat(s) if s else None


def _safe_dauer_min(dauer_val):
    try:
        parts = str(dauer_val).split(':')
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError, TypeError, AttributeError):
        return 0


def dauer_string(abf, ank):
    """'07:00','17:00' -> '10:00' (bei Mitternachtsübergang +24h)."""
    try:
        h1, m1 = map(int, str(abf).split(':'))
        h2, m2 = map(int, str(ank).split(':'))
        mins = (h2 * 60 + m2) - (h1 * 60 + m1)
        if mins < 0:
            mins += 24 * 60
        return f"{mins // 60:02d}:{mins % 60:02d}"
    except (ValueError, TypeError):
        return "00:00"


def normalize_col(s):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.strip().lower()
    return re.sub(r"[^\w]+", "_", s).strip("_")


def normalize_df_cols(df):
    df = df.copy()
    df.columns = [normalize_col(c) for c in df.columns]
    return df


def coalesce(df, candidates, to_name):
    """Benennt die erste gefundene Kandidaten-Spalte in to_name um (wie Original)."""
    for cand in candidates:
        if cand in df.columns:
            return df.rename(columns={cand: to_name})
    for c in df.columns:
        for cand in candidates:
            if cand in c:
                return df.rename(columns={c: to_name})
    return df


def drop_empty_rows(df):
    return df.dropna(how="all").reset_index(drop=True)


def get_valid_fahrzeug_optionen(fahrzeuge_df):
    """Liefert ein Dict {bezeichnung: id} nur für Fahrzeuge mit gültigem Namen (wie Original)."""
    valid = {}
    if fahrzeuge_df is None or fahrzeuge_df.empty:
        return valid
    for _, row in fahrzeuge_df.iterrows():
        bez = row.get('bezeichnung')
        if bez is not None and pd.notna(bez):
            bez_str = str(bez).strip()
            if bez_str and bez_str.lower() not in ('none', 'nan', ''):
                valid[bez_str] = int(row['id']) if pd.notna(row.get('id')) else None
    return valid


def extrahiere_ort(adresse):
    if not adresse:
        return "Unbekannt"
    part = adresse.split(',')[-1].strip() if ',' in adresse else adresse.strip()
    cleaned = re.sub(r'^[A-Za-z]?-?\d{4,5}\s+', '', part)
    return cleaned if cleaned else part