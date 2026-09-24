"""Der original Fahrten-Generator: Urlaubswochen, Wahrscheinlichkeiten,
2-wöchentliche Sonderfahrt, dienstlich_quote, KM-Skalierung, Endkilometer.

GEÄNDERT gegenüber Original: An Werktagen bleibt kein Tag mehr leer.
Fällt die Werktag-Wahrscheinlichkeit negativ aus, wird trotzdem eine
normale Dienstfahrt erzeugt. Der Slider steuert die Anzahl der Stopps
(und damit die Fahrtlänge)."""
from datetime import date, datetime, timedelta
import calendar

import numpy as np
import pandas as pd

from logic.kalender import austria_holidays
from logic.helpers import _safe_int


def _time_str(dt):
    return dt.strftime("%H:%M")


def _dauer_str(mins):
    return f"{mins // 60:02d}:{mins % 60:02d}"


def urlaubs_tage(jahr, anzahl_wochen, verteilung, start_woche_1: date) -> set:
    """Exakt wie Original: 1x4 / 2x2 / 4x1 Wochen."""
    vacation = set()
    if anzahl_wochen <= 0:
        return vacation
    if verteilung == "1x4 Wochen":
        for j in range(4 * 7):
            vacation.add(start_woche_1 + timedelta(days=j))
    elif verteilung == "2x2 Wochen":
        for i in range(2):
            block = start_woche_1 + timedelta(weeks=i * 26)
            for j in range(2 * 7):
                vacation.add(block + timedelta(days=j))
    elif verteilung == "4x1 Woche":
        for i in range(4):
            block = start_woche_1 + timedelta(weeks=i * 13)
            for j in range(7):
                vacation.add(block + timedelta(days=j))
    return vacation


def generiere_monate(jahr, monate_liste, user_info, fahrzeuge_df, zeitraeume_df,
                     keywords_df, params):
    """Liefert ({monat_key: {"data": df, "end_km": int}}, current_km_dict)."""
    rng = np.random.default_rng()
    hol = austria_holidays(jahr)
    wohnort = str(user_info.get('wohnort', 'Oberhofen am Irrsee'))
    dienstort = str(user_info.get('dienstort', 'Straßwalchen'))
    wohnort_clean = wohnort.split(',')[-1].strip() if ',' in wohnort else wohnort
    dienstort_clean = dienstort.split(',')[-1].strip() if ',' in dienstort else dienstort

    fahrzeug_optionen = {}
    for _, row in fahrzeuge_df.iterrows():
        bez = row.get('bezeichnung')
        if bez is not None and pd.notna(bez):
            b = str(bez).strip()
            if b and b.lower() not in ('none', 'nan', ''):
                fahrzeug_optionen[b] = _safe_int(row['id'])

    current_km = {row['id']: _safe_int(row.get('start_km_vorjahr'))
                  for _, row in fahrzeuge_df.iterrows() if pd.notna(row.get('id'))}
    privat_km_ranges = {_safe_int(row['id']): (
        _safe_int(row.get('privat_km_min'), 5), _safe_int(row.get('privat_km_max'), 20))
        for _, row in fahrzeuge_df.iterrows() if pd.notna(row.get('id'))}
    dienstlich_quotes = {_safe_int(row['id']): max(0, min(100, _safe_int(
        row.get('dienstlich_quote'), 90)))
        for _, row in fahrzeuge_df.iterrows() if pd.notna(row.get('id'))}

    _liste = []
    if zeitraeume_df is not None and not zeitraeume_df.empty:
        for _, z in zeitraeume_df.iterrows():
            try:
                v, b, fid = str(z['von'])[:10], str(z['bis'])[:10], _safe_int(z['fahrzeug_id'], None)
            except (KeyError, TypeError, ValueError):
                continue
            if v and b and v not in ('none', 'nan') and b not in ('none', 'nan') and fid is not None:
                _liste.append((v, b, fid))

    deckt = any(int(v[:4]) <= jahr <= int(b[:4]) for v, b, _ in _liste)
    if not deckt:
        raise ValueError(f"Kein Zeitraum deckt das Jahr {jahr} ab! "
                         "Bitte Zeiträume (von/bis) aktualisieren, sonst werden keine "
                         "Fahrzeuge zugewiesen.")

    month_workday_counts, avg_workdays = {}, 0
    for mk in monate_liste:
        tage = pd.date_range(date(jahr, mk, 1), date(jahr, mk, calendar.monthrange(jahr, mk)[1]), freq="D")
        wd = sum(1 for t in tage if t.weekday() < 5 and t.date() not in hol
                 and t.date() not in params.get('vacation_days', set()))
        month_workday_counts[mk] = wd
        avg_workdays += wd
    avg_workdays = avg_workdays / len(monate_liste) if monate_liste else 21

    vacation_days = params.get('vacation_days', set())
    urlaub_fahrzeug_id = fahrzeug_optionen.get(params.get('urlaub_fahrzeug_name', ''), None)
    haupt_id = fahrzeug_optionen.get(params.get('hauptfahrzeug_name', ''), None)
    haupt_anteil = params.get('hauptfahrzeug_anteil', 70) / 100.0
    prob_feiertag_urlaub = params.get('prob_feiertag_urlaub', 5) / 100.0
    prob_werktag = params.get('prob_werktag', 75)
    kw = keywords_df if keywords_df is not None and not keywords_df.empty else \
        pd.DataFrame([{"Ort": "Büro", "Zweck": "Büro"}])

    generated = {}
    for monat_key in monate_liste:
        tage = pd.date_range(date(jahr, monat_key, 1),
                             date(jahr, monat_key, calendar.monthrange(jahr, monat_key)[1]), freq="D")
        out = []
        special_trip_done_this_week = False

        for t in tage:
            route = "Keine Fahrt"; km_d = 0; km_p = 0
            abf = ank = dauer = "00:00"
            fahrzeug_id = None; fahrzeug_name = "Kein Fahrzeug"
            tag_str = t.strftime("%Y-%m-%d")
            gueltig = [fid for v, b, fid in _liste if v <= tag_str <= b]
            if gueltig:
                if haupt_id is not None and int(haupt_id) in gueltig and len(gueltig) > 1:
                    rest = (1.0 - haupt_anteil) / (len(gueltig) - 1)
                    weights = [haupt_anteil if int(fid) == int(haupt_id) else rest for fid in gueltig]
                    fahrzeug_id = int(rng.choice(gueltig, p=weights))
                else:
                    fahrzeug_id = int(rng.choice(gueltig))
                fahrzeug_name = "Unbekannt"
                for bname, bid in fahrzeug_optionen.items():
                    if int(bid) == fahrzeug_id:
                        fahrzeug_name = bname
                        break
            if t.weekday() == 0:
                special_trip_done_this_week = False
            is_saturday = t.weekday() == 5
            is_sunday = t.weekday() == 6
            is_holiday = t.date() in hol
            is_vacation = t.date() in vacation_days

            if is_holiday or is_vacation:
                if rng.random() < prob_feiertag_urlaub:
                    num_stops = int(rng.integers(1, 3))
                    sel = kw.sample(min(num_stops, len(kw)))
                    stops = [f"{r['Ort']} ({r['Zweck']})" for _, r in sel.iterrows()]
                    km_d = int(rng.integers(15, 25)) + sum(int(rng.integers(10, 25)) for _ in range(num_stops))
                    route = ("Feiertag: " if is_holiday else "Urlaub: ") + " - ".join([wohnort_clean] + stops + [wohnort_clean])
                    fahrzeit = int(km_d / 80 * 60)
                    pause = int(rng.integers(20, 60))
                    dauer_min = fahrzeit + pause
                    start_minute = int(np.clip(rng.normal(480, 20, 1)[0], 420, 540))
                    abf_dt = datetime.combine(t.date(), datetime.min.time()) + timedelta(minutes=start_minute)
                    ank_dt = abf_dt + timedelta(minutes=int(dauer_min))
                    abf, ank, dauer = _time_str(abf_dt), _time_str(ank_dt), _dauer_str(dauer_min)
                else:
                    if is_vacation:
                        if urlaub_fahrzeug_id is not None and urlaub_fahrzeug_id in gueltig:
                            fahrzeug_id = int(urlaub_fahrzeug_id)
                            match = fahrzeuge_df[fahrzeuge_df['id'] == fahrzeug_id]
                            fahrzeug_name = match['bezeichnung'].values[0] if len(match) else "Unbekannt"
                            km_p = int(rng.integers(params.get('urlaub_km_min', 30),
                                                    params.get('urlaub_km_max', 80) + 1))
                            route = "Urlaub"
                        else:
                            km_p = int(rng.integers(5, 21))
                            route = "Urlaub (Urlaubs-FZ nicht verfügbar)"
                    else:
                        km_p = int(rng.integers(*privat_km_ranges.get(fahrzeug_id, (5, 21)))) \
                            if fahrzeug_id in privat_km_ranges else int(rng.integers(5, 21))
                        route = "Feiertag"
                    km_d = 0
                    start_hour = int(rng.integers(9, 18))
                    fahrzeit = max(int(km_p / 70 * 60) + int(rng.integers(5, 15)), 15)
                    abf_dt = datetime.combine(t.date(), datetime.min.time()) + timedelta(hours=start_hour)
                    ank_dt = abf_dt + timedelta(minutes=fahrzeit)
                    abf, ank, dauer = _time_str(abf_dt), _time_str(ank_dt), _dauer_str(fahrzeit)
            elif is_saturday:
                if rng.random() < 0.4:
                    km_d = int(rng.integers(25, 55)); km_p = 0
                    num_stops = int(rng.integers(1, 2))
                    sel = kw.sample(min(num_stops, len(kw)))
                    stops = [f"{r['Ort']} ({r['Zweck']})" for _, r in sel.iterrows()]
                    route = " - ".join([wohnort_clean] + stops + [wohnort_clean])
                    fahrzeit = int(km_d / 80 * 60)
                    dauer_min = fahrzeit + int(rng.integers(15, 30))
                    abf_dt = datetime.combine(t.date(), datetime.min.time()) + timedelta(hours=9)
                    ank_dt = abf_dt + timedelta(minutes=int(dauer_min))
                    abf, ank, dauer = _time_str(abf_dt), _time_str(ank_dt), _dauer_str(dauer_min)
            elif is_sunday:
                km_p = int(rng.integers(*privat_km_ranges.get(fahrzeug_id, (5, 21)))) \
                    if fahrzeug_id in privat_km_ranges else int(rng.integers(5, 21))
                km_d = 0; route = "Sonntag"
                start_hour = int(rng.integers(9, 18))
                fahrzeit = max(int(km_p / 70 * 60) + int(rng.integers(5, 15)), 15)
                abf_dt = datetime.combine(t.date(), datetime.min.time()) + timedelta(hours=start_hour)
                ank_dt = abf_dt + timedelta(minutes=fahrzeit)
                abf, ank, dauer = _time_str(abf_dt), _time_str(ank_dt), _dauer_str(fahrzeit)
            else:
                # WERKTAG: dienstlich_quote des Fahrzeugs entscheidet Dienst vs. Privat
                fz_quote = dienstlich_quotes.get(fahrzeug_id, 90) / 100.0
                is_dienstlich = rng.random() < fz_quote
                if not is_dienstlich:
                    km_d = 0
                    km_p = int(rng.integers(*privat_km_ranges.get(fahrzeug_id, (5, 21)))) \
                        if fahrzeug_id in privat_km_ranges else int(rng.integers(5, 21))
                    route = f"{wohnort_clean} - {dienstort_clean} (Arbeitsweg)" if rng.random() < 0.4 else "Privatfahrt"
                    fahrzeit = max(int(km_p / 70 * 60) + int(rng.integers(5, 15)), 15)
                    start_minute = int(np.clip(rng.normal(480, 10, 1)[0], 450, 540))
                    abf_dt = datetime.combine(t.date(), datetime.min.time()) + timedelta(minutes=start_minute)
                    ank_dt = abf_dt + timedelta(minutes=fahrzeit)
                    abf, ank, dauer = _time_str(abf_dt), _time_str(ank_dt), _dauer_str(fahrzeit)
                else:
                    current_week = t.isocalendar()[1]
                    target_day = 0 if current_week % 2 == 1 else 1
                    if t.weekday() == target_day and not special_trip_done_this_week:
                        special_trip_done_this_week = True
                        km_p = _safe_int(user_info.get('entfernung'), 25)
                        parts = [wohnort_clean, f"{dienstort_clean} (Büro)"]
                        num_stops = int(rng.integers(1, 4))
                        sel = kw.sample(min(num_stops, len(kw)))
                        for _, r in sel.iterrows():
                            parts.append(f"{r['Ort']} ({r['Zweck']})")
                        parts.append(wohnort_clean)
                        route = " - ".join(parts)
                        km_d = int(km_p) + sum(int(rng.integers(15, 35)) for _ in range(num_stops))
                        fahrzeit = int((km_d + km_p) / 75 * 60)
                        termin = int(num_stops * int(rng.integers(25, 45)))
                        pause = int(rng.integers(15, 30)) if num_stops >= 3 else (int(rng.integers(5, 15)) if num_stops >= 2 else 0)
                        dauer_min = max(min(fahrzeit + termin + pause, 840), 180)
                        start_minute = int(np.clip(rng.normal(480, 5, 1)[0], 470, 490))
                        abf_dt = datetime.combine(t.date(), datetime.min.time()) + timedelta(minutes=start_minute)
                        ank_dt = abf_dt + timedelta(minutes=int(dauer_min))
                        abf, ank, dauer = _time_str(abf_dt), _time_str(ank_dt), _dauer_str(dauer_min)
                    else:
                        # GEÄNDERT: immer eine Dienstfahrt – kein Werktag bleibt leer.
                        # Der Slider steuert die Anzahl der Stopps (Fahrtlänge).
                        if prob_werktag >= 90: num_stops = int(rng.integers(1, 3))
                        elif prob_werktag >= 70: num_stops = int(rng.integers(1, 4))
                        elif prob_werktag >= 50: num_stops = int(rng.integers(2, 4))
                        else: num_stops = int(rng.integers(2, 5))
                        sel = kw.sample(min(num_stops, len(kw)))
                        stops = [f"{r['Ort']} ({r['Zweck']})" for _, r in sel.iterrows()]
                        route = " - ".join([wohnort_clean] + stops + [wohnort_clean])
                        km_d = sum(int(rng.integers(15, 35)) for _ in range(num_stops)); km_p = 0
                        fahrzeit = int((km_d + km_p) / 75 * 60)
                        termin = int(num_stops * int(rng.integers(25, 45)))
                        pause = int(rng.integers(15, 30)) if num_stops >= 3 else (int(rng.integers(5, 15)) if num_stops >= 2 else 0)
                        dauer_min = max(min(fahrzeit + termin + pause, 840), 150)
                        start_minute = int(np.clip(rng.normal(480, 5, 1)[0], 470, 490))
                        abf_dt = datetime.combine(t.date(), datetime.min.time()) + timedelta(minutes=start_minute)
                        ank_dt = abf_dt + timedelta(minutes=int(dauer_min))
                        abf, ank, dauer = _time_str(abf_dt), _time_str(ank_dt), _dauer_str(dauer_min)

            abfahrt_km = current_km.get(fahrzeug_id, 0) if fahrzeug_id is not None else 0
            out.append({"datum": t.date(), "fahrzeug_id": fahrzeug_id, "fahrzeug": fahrzeug_name,
                        "route": route, "km_d": km_d, "km_p": km_p, "abf": abf, "ank": ank,
                        "dauer": dauer, "abfahrt_km": abfahrt_km})
            if fahrzeug_id is not None and (km_d > 0 or km_p > 0):
                current_km[fahrzeug_id] = current_km.get(fahrzeug_id, 0) + km_d + km_p

        df = pd.DataFrame(out).sort_values(["datum"]).reset_index(drop=True)

        # KM-Skalierung auf Monatsziel (wie Original)
        target_min = params.get('target_km_min', 1650)
        target_max = params.get('target_km_max', 2000)
        if not df.empty and target_max > 0:
            cur = df["km_d"].sum()
            if cur > 0 and not (target_min <= cur <= target_max):
                base = rng.uniform(target_min, target_max)
                wf = np.clip(month_workday_counts.get(monat_key, 21) / avg_workdays if avg_workdays > 0 else 1.0, 0.70, 1.20)
                zf = rng.uniform(0.88, 1.12)
                mt = np.clip(base * wf * zf, target_min * 0.55, target_max * 1.25)
                sf = mt / cur
                df["km_d"] = df.apply(lambda r: int(r["km_d"] * sf) if r["km_d"] > 0 else 0, axis=1)
                msk = {fz: km - df[df["fahrzeug_id"] == fz][["km_d", "km_p"]].sum().sum()
                       for fz, km in current_km.items()}
                rows = []
                for _, row in df.iterrows():
                    fz = row["fahrzeug_id"]
                    if fz is not None:
                        r = row.to_dict(); r["abfahrt_km"] = msk.get(fz, 0)
                        rows.append(r); msk[fz] += row["km_d"] + row["km_p"]
                    else:
                        rows.append(row.to_dict())
                df = pd.DataFrame(rows)
                for fz, km in msk.items():
                    current_km[fz] = km

        generated[(jahr, monat_key)] = {"data": df,
                                        "end_km": max(current_km.values()) if current_km else 0}
    return generated, current_km
