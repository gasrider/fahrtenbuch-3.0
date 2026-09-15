"""HU-Korrektur: km vor HU skalieren, HU-Fahrt mit Werkstatt-Route anlegen, kmstände neu."""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from logic.helpers import _safe_int


def _scale_dauer(dauer_str, factor):
    try:
        parts = str(dauer_str).split(':')
        if len(parts) != 2:
            return dauer_str
        total = int(parts[0]) * 60 + int(parts[1])
        if total <= 0:
            return dauer_str
        new = min(int(total * factor), 840)
        return f"{new // 60:02d}:{new % 60:02d}"
    except Exception:
        return dauer_str


def _recalc_ankunft(row):
    try:
        a = str(row['abf']).split(':'); d = str(row['dauer']).split(':')
        m = int(a[0]) * 60 + int(a[1]) + int(d[0]) * 60 + int(d[1])
        m = min(m, 1320)  # max 22:00
        return f"{m // 60:02d}:{m % 60:02d}"
    except Exception:
        return row['ank']


def wende_hu_korrekturen_an(generated_months_data, fahrzeuge_df, corrections,
                            keywords_df, wohnort_raw):
    """corrections: [{fahrzeug_id, datum(date), km_at_hu, werkstattort,
                      stopps_vor_hu:[..], stopps_nach_hu:[..]}]
    Gibt (generated_months_data, meldungen) zurück."""
    rng = np.random.default_rng()
    meldungen = []
    wohnort = str(wohnort_raw)
    import re as _re
    wohnort_clean = _re.sub(r'^[A-Za-z]?-?\d{4,5}\s+', '',
                            wohnort.split(',')[-1].strip()) if ',' in wohnort else wohnort

    fahrzeug_optionen = {}
    for _, row in fahrzeuge_df.iterrows():
        if pd.notna(row.get('id')) and pd.notna(row.get('bezeichnung')):
            fahrzeug_optionen[_safe_int(row['id'])] = str(row['bezeichnung']).strip()

    kw = keywords_df if keywords_df is not None and not keywords_df.empty else \
        pd.DataFrame([{"Ort": "Büro", "Zweck": "Büro"}])

    def lookup_zweck(ort):
        o = ort.strip().lower()
        m = kw[kw['Ort'].astype(str).str.lower().str.strip() == o]
        if not m.empty:
            return rng.choice(m['Zweck'].tolist())
        for _, r in kw.iterrows():
            if o in str(r['Ort']).lower() or str(r['Ort']).lower() in o:
                return r['Zweck']
        return rng.choice(["Angebot", "Schaden", "KB"])

    all_trips = {}
    for fz_id in fahrzeug_optionen:
        parts = []
        for key, data in generated_months_data.items():
            df = data["data"]
            f = df[df['fahrzeug_id'] == fz_id]
            if not f.empty:
                parts.append(f)
        if parts:
            all_trips[fz_id] = pd.concat(parts).sort_values("datum").reset_index(drop=True)

    for c in corrections:
        fz_id = c['fahrzeug_id']; hu_date = c['datum']; km_at_hu = _safe_int(c['km_at_hu'])
        werkstatt = c['werkstattort']
        stops_vor = c.get('stopps_vor_hu', []); stops_nach = c.get('stopps_nach_hu', [])
        if fz_id not in all_trips:
            meldungen.append(f"⚠️ Keine Fahrten für Fahrzeug '{fahrzeug_optionen.get(fz_id, fz_id)}' – übersprungen.")
            continue
        fz_name = fahrzeug_optionen[fz_id]
        meldungen.append(f"**Korrigiere Fahrzeug:** {fz_name}")
        trips = all_trips[fz_id]
        start_match = fahrzeuge_df[fahrzeuge_df['id'] == fz_id]['start_km_vorjahr']
        start_km = _safe_int(start_match.iloc[0]) if len(start_match) else 0
        before = trips[trips['datum'] < hu_date].copy()
        if not before.empty:
            meldungen.append(f"• Berechne {len(before)} Fahrten vor dem {hu_date.strftime('%d.%m.%Y')} neu.")
            calc = start_km + (before['km_d'] + before['km_p']).sum()
            target = km_at_hu - start_km
            if calc > start_km and (calc - start_km) > 0:
                sf = target / (calc - start_km)
                meldungen.append(f"• Skalierungsfaktor: {sf:.4f}")
                before['km_d'] = (before['km_d'] * sf).astype(int)
                before['km_p'] = (before['km_p'] * sf).astype(int)
                before['dauer'] = before['dauer'].apply(lambda d: _scale_dauer(d, sf))
                before['ank'] = before.apply(_recalc_ankunft, axis=1)
            for _, trip in before.iterrows():
                key = (pd.Timestamp(trip['datum']).year, pd.Timestamp(trip['datum']).month)
                if key not in generated_months_data:
                    continue
                odf = generated_months_data[key]["data"]
                m = odf[(pd.to_datetime(odf['datum']).dt.date == pd.Timestamp(trip['datum']).date())
                        & (odf['fahrzeug_id'] == fz_id)].index
                if m.empty:
                    continue
                i = m[0]
                for col in ('km_d', 'km_p', 'dauer', 'ank'):
                    generated_months_data[key]["data"].at[i, col] = trip[col]

        # HU-Fahrt am HU-Tag erstellen/ersetzen
        hu_key = (hu_date.year, hu_date.month)
        if hu_key not in generated_months_data:
            meldungen.append(f"⚠️ Kein Monat {hu_key} generiert – HU-Fahrt übersprungen.")
            continue
        hdf = generated_months_data[hu_key]["data"]
        idx = hdf[(pd.to_datetime(hdf['datum']).dt.date == hu_date)
                  & (hdf['fahrzeug_id'] == fz_id)].index
        if idx.empty:
            idx = hdf[pd.to_datetime(hdf['datum']).dt.date == hu_date].index
        total_stops = len(stops_vor) + 1 + len(stops_nach)
        km_hu = int(rng.integers(20, 40)) + total_stops * int(rng.integers(10, 20))
        parts = [wohnort_clean]
        for s in stops_vor:
            parts.append(f"{s} ({lookup_zweck(s)})")
        parts.append(f"{werkstatt} (HU)")
        for s in stops_nach:
            parts.append(f"{s} ({lookup_zweck(s)})")
        parts.append(wohnort_clean)
        hu_route = " - ".join(parts)
        hu_dauer = 90 + total_stops * 20
        hu_abf = datetime.combine(hu_date, datetime.min.time()) + timedelta(hours=8, minutes=30)
        hu_ank = hu_abf + timedelta(minutes=hu_dauer)
        if not idx.empty:
            i = idx[0]
            upd = {'fahrzeug_id': fz_id, 'fahrzeug': fz_name, 'km_d': km_hu, 'km_p': 0,
                   'route': hu_route, 'abf': hu_abf.strftime("%H:%M"),
                   'ank': hu_ank.strftime("%H:%M"),
                   'dauer': f"{hu_dauer // 60:02d}:{hu_dauer % 60:02d}"}
            for col, v in upd.items():
                generated_months_data[hu_key]["data"].at[i, col] = v
            meldungen.append(f"• HU-Fahrt am {hu_date.strftime('%d.%m.%Y')} mit {km_hu} km angelegt.")
        else:
            meldungen.append(f"⚠️ Kein Eintrag am {hu_date.strftime('%d.%m.%Y')} gefunden – übersprungen.")

    # Alle abfahrt_km neu (chronologisch)
    km = {_safe_int(r['id']): _safe_int(r.get('start_km_vorjahr'))
          for _, r in fahrzeuge_df.iterrows() if pd.notna(r.get('id'))}
    for key in sorted(generated_months_data.keys()):
        df = generated_months_data[key]["data"].sort_values("datum").reset_index(drop=True)
        rows = []
        for _, row in df.iterrows():
            fz = row['fahrzeug_id']
            r = row.to_dict()
            if fz is not None and not pd.isna(fz):
                fz = int(fz)
                r['abfahrt_km'] = km.get(fz, 0)
                km[fz] = km.get(fz, 0) + _safe_int(row['km_d']) + _safe_int(row['km_p'])
            rows.append(r)
        generated_months_data[key]["data"] = pd.DataFrame(rows)
    return generated_months_data, meldungen