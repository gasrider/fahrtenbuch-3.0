"""HU-Korrektur v2: symmetrische Skalierung (vor/nach HU), Faktor-Deckel,
Jahressumme bleibt erhalten, HU-Fahrt wird garantiert angelegt."""
import re
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from logic.helpers import _safe_int

FAKTOR_MIN = 0.5
FAKTOR_MAX = 2.0


def _scale_dauer(dauer_str, factor):
    try:
        parts = str(dauer_str).split(':')
        if len(parts) != 2:
            return dauer_str
        total = int(parts[0]) * 60 + int(parts[1])
        if total <= 0:
            return dauer_str
        new = min(max(int(total * factor), 10), 840)
        return f"{new // 60:02d}:{new % 60:02d}"
    except Exception:
        return dauer_str


def _recalc_ankunft(row):
    try:
        a = str(row['abf']).split(':')
        d = str(row['dauer']).split(':')
        m = int(a[0]) * 60 + int(a[1]) + int(d[0]) * 60 + int(d[1])
        m = min(m, 23 * 60 + 59)
        return f"{m // 60:02d}:{m % 60:02d}"
    except Exception:
        return str(row.get('ank', '08:00'))


def _skaliere(df, factor):
    if df is None or df.empty or factor == 1.0:
        return df
    df = df.copy()
    df['km_d'] = (df['km_d'] * factor).astype(int)
    df['km_p'] = (df['km_p'] * factor).astype(int)
    df['dauer'] = df['dauer'].apply(lambda d: _scale_dauer(d, factor))
    df['ank'] = df.apply(_recalc_ankunft, axis=1)
    return df


def wende_hu_korrekturen_an(generated_months_data, fahrzeuge_df, corrections,
                            keywords_df, wohnort_raw):
    rng = np.random.default_rng()
    meldungen = []
    wohnort = str(wohnort_raw or '')
    if ',' in wohnort:
        wohnort = re.sub(r'^[A-Za-z]?-?\d{4,5}\s+', '', wohnort.split(',')[-1].strip())

    for key in generated_months_data:
        df = generated_months_data[key].get("data")
        if df is not None and not df.empty:
            df['datum'] = pd.to_datetime(df['datum']).dt.date
            generated_months_data[key]["data"] = df

    id_zu_name = {}
    start_km_map = {}
    for _, row in fahrzeuge_df.iterrows():
        if pd.notna(row.get('id')):
            fid = _safe_int(row['id'])
            id_zu_name[fid] = str(row.get('bezeichnung', '')).strip()
            start_km_map[fid] = _safe_int(row.get('start_km_vorjahr'))

    def sammle_fahrten():
        alle = {}
        for key in sorted(generated_months_data.keys()):
            df = generated_months_data[key].get("data")
            if df is None or df.empty:
                continue
            for fz_id in id_zu_name:
                f = df[df['fahrzeug_id'] == fz_id]
                if not f.empty:
                    if fz_id in alle:
                        alle[fz_id] = pd.concat([alle[fz_id], f])
                    else:
                        alle[fz_id] = f.copy()
        return alle

    for c in corrections:
        fz_id = c['fahrzeug_id']
        hu_date = c['datum']
        if isinstance(hu_date, str):
            hu_date = pd.to_datetime(hu_date).date()
        km_at_hu = _safe_int(c['km_at_hu'])
        werkstatt = str(c.get('werkstattort', '') or '').strip()
        stops_vor = c.get('stopps_vor_hu', []) or []
        stops_nach = c.get('stopps_nach_hu', []) or []
        fz_name = id_zu_name.get(fz_id, f'FZ {fz_id}')
        meldungen.append(f"**HU {fz_name} am {hu_date.strftime('%d.%m.%Y')}**")

        alle_fahrten = sammle_fahrten()
        if fz_id not in alle_fahrten or alle_fahrten[fz_id].empty:
            meldungen.append("- Keine Fahrten dieses Fahrzeugs gefunden - uebersprungen.")
            continue

        trips = alle_fahrten[fz_id].sort_values('datum').reset_index(drop=True)
        start_km = start_km_map.get(fz_id, 0)

        vor = trips[trips['datum'] < hu_date].copy()
        am_tag = trips[trips['datum'] == hu_date].copy()
        nach = trips[trips['datum'] > hu_date].copy()

        sum_vor = _safe_int(vor['km_d'].sum()) + _safe_int(vor['km_p'].sum())
        sum_nach = _safe_int(nach['km_d'].sum()) + _safe_int(nach['km_p'].sum())
        sum_tag = _safe_int(am_tag['km_d'].sum()) + _safe_int(am_tag['km_p'].sum())
        jahres_ende = start_km + sum_vor + sum_tag + sum_nach

        ziel_vor = km_at_hu - start_km
        faktor_vor = (ziel_vor / sum_vor) if (sum_vor > 0 and ziel_vor > 0) else 1.0

        total_stops = len(stops_vor) + 1 + len(stops_nach)
        hu_km = int(rng.integers(20, 40)) + total_stops * int(rng.integers(10, 20))
        ziel_nach = jahres_ende - km_at_hu - hu_km
        faktor_nach = (ziel_nach / sum_nach) if (sum_nach > 0 and ziel_nach > 0) else 1.0

        fv = max(min(faktor_vor, FAKTOR_MAX), FAKTOR_MIN)
        fn = max(min(faktor_nach, FAKTOR_MAX), FAKTOR_MIN)
        if abs(fv - faktor_vor) > 0.01:
            meldungen.append(f"- ACHTUNG: HU-Stand passt stark nicht zu den generierten km "
                             f"(Faktor waere {faktor_vor:.2f}) - auf {fv:.2f} begrenzt. "
                             "Bitte km_at_hu pruefen!")
        if abs(fn - faktor_nach) > 0.01:
            meldungen.append(f"- Faktor nach HU auf {fn:.2f} begrenzt.")
        meldungen.append(f"- Faktor vor HU: {fv:.3f} | nach HU: {fn:.3f} "
                         "(Jahressumme bleibt erhalten)")

        vor_s = _skaliere(vor, fv)
        nach_s = _skaliere(nach, fn)
        werte = {}
        for _, r in vor_s.iterrows():
            werte[r['datum']] = r
        for _, r in nach_s.iterrows():
            werte[r['datum']] = r

        parts = [wohnort] + [str(s) for s in stops_vor] + [f"{werkstatt} (HU)"] \
            + [str(s) for s in stops_nach] + [wohnort]
        hu_route = " - ".join([p for p in parts if p])
        hu_dauer = 90 + total_stops * 20
        hu_abf = datetime.combine(hu_date, datetime.min.time()) + timedelta(hours=8, minutes=30)
        hu_ank = hu_abf + timedelta(minutes=hu_dauer)

        hu_angelegt = False
        for key in sorted(generated_months_data.keys()):
            df = generated_months_data[key].get("data")
            if df is None:
                continue
            if df.empty:
                continue
            mask_fz = df['fahrzeug_id'] == fz_id
            for idx in df[mask_fz].index:
                d = df.at[idx, 'datum']
                if d == hu_date:
                    df.at[idx, 'route'] = hu_route
                    df.at[idx, 'km_d'] = hu_km
                    df.at[idx, 'km_p'] = 0
                    df.at[idx, 'abf'] = hu_abf.strftime('%H:%M')
                    df.at[idx, 'ank'] = hu_ank.strftime('%H:%M')
                    df.at[idx, 'dauer'] = f"{hu_dauer // 60:02d}:{hu_dauer % 60:02d}"
                    hu_angelegt = True
                elif d in werte:
                    r = werte[d]
                    df.at[idx, 'km_d'] = _safe_int(r['km_d'])
                    df.at[idx, 'km_p'] = _safe_int(r['km_p'])
                    df.at[idx, 'dauer'] = r['dauer']
                    df.at[idx, 'ank'] = r['ank']
            if not hu_angelegt:
                treffer = df[df['datum'] == hu_date]
                if not treffer.empty:
                    i = treffer.index[0]
                    df.at[i, 'fahrzeug_id'] = fz_id
                    df.at[i, 'fahrzeug'] = fz_name
                    df.at[i, 'route'] = hu_route
                    df.at[i, 'km_d'] = hu_km
                    df.at[i, 'km_p'] = 0
                    df.at[i, 'abf'] = hu_abf.strftime('%H:%M')
                    df.at[i, 'ank'] = hu_ank.strftime('%H:%M')
                    df.at[i, 'dauer'] = f"{hu_dauer // 60:02d}:{hu_dauer % 60:02d}"
                    hu_angelegt = True
                elif key[0] == hu_date.year and key[1] == hu_date.month:
                    neuer = {"datum": hu_date, "fahrzeug_id": fz_id, "fahrzeug": fz_name,
                             "route": hu_route, "km_d": hu_km, "km_p": 0,
                             "abf": hu_abf.strftime('%H:%M'),
                             "ank": hu_ank.strftime('%H:%M'),
                             "dauer": f"{hu_dauer // 60:02d}:{hu_dauer % 60:02d}",
                             "abfahrt_km": 0}
                    df = pd.concat([df, pd.DataFrame([neuer])], ignore_index=True)
                    df = df.sort_values('datum').reset_index(drop=True)
                    hu_angelegt = True
            generated_months_data[key]["data"] = df
        if hu_angelegt:
            meldungen.append(f"- HU-Fahrt am {hu_date.strftime('%d.%m.%Y')} mit {hu_km} km angelegt.")
        else:
            meldungen.append("- WARNUNG: HU-Tag liegt ausserhalb der geladenen Monate!")

    km = dict(start_km_map)
    for key in sorted(generated_months_data.keys()):
        df = generated_months_data[key].get("data")
        if df is None or df.empty:
            continue
        df = df.sort_values('datum').reset_index(drop=True)
        for idx, row in df.iterrows():
            fz = row.get('fahrzeug_id')
            if fz is not None and not pd.isna(fz):
                fz = int(fz)
                df.at[idx, 'abfahrt_km'] = km.get(fz, 0)
                km[fz] = km.get(fz, 0) + _safe_int(row['km_d']) + _safe_int(row['km_p'])
        generated_months_data[key]["data"] = df

    return generated_months_data, km, meldungen
