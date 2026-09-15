"""Jahres-Fahrtenbuch als PDF (Monatssummen, Finanzen, Fahrzeuge)."""
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

from logic.constants import MONATE
from logic.helpers import _safe_int, _safe_float, _safe_dauer_min
from logic.taggeld import berechne_taggeld_betrag, taggeld_params_aus_settings


def create_jahres_pdf(monate_dict, jahr, user_info, fahrzeuge_df):
    """monate_dict: {(jahr, monat): {"data": DataFrame} oder DataFrame}"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    story = []
    styles = getSampleStyleSheet()
    params = taggeld_params_aus_settings(user_info)

    title_style = ParagraphStyle('JahrTitle', parent=styles['Normal'],
                                 fontName='Helvetica-Bold', fontSize=18, spaceAfter=8*mm)
    story.append(Paragraph(f"Fahrtenbuch Jahresübersicht {jahr}", title_style))

    info = ParagraphStyle('Info', parent=styles['Normal'], fontSize=10, leading=14)
    fzg_list = [f"{r.get('bezeichnung','')} ({r.get('kennzeichen','')})"
                for _, r in fahrzeuge_df.iterrows()]
    story.append(Paragraph(f"Name: {user_info.get('name','')}", info))
    story.append(Paragraph(f"PNR: {user_info.get('pnr','')}", info))
    story.append(Paragraph(f"Wohnort: {user_info.get('wohnort','')}", info))
    story.append(Paragraph(f"Dienstort: {user_info.get('dienstort','')}", info))
    story.append(Paragraph(f"Entfernung zwischen Arbeitsplatz und Wohnung: "
                           f"{_safe_int(user_info.get('entfernung'))} km", info))
    story.append(Paragraph(f"Fahrzeug(e): {', '.join(fzg_list)}", info))
    story.append(Spacer(1, 8*mm))

    km_satz = _safe_float(user_info.get('km_geld'), 0.42)
    total_d = total_p = total_km_geld = total_taggeld = 0
    data = [["Monat", "gefahren km", "", "km-Geld", ""],
            ["Monat", "dienstl.", "privat", "PKW", "EUR"]]

    for i, mname in enumerate(MONATE):
        key = (jahr, i + 1)
        entry = monate_dict.get(key)
        df = entry.get("data") if isinstance(entry, dict) else entry
        if df is None or getattr(df, 'empty', True):
            data.append([mname, 0, 0, "0,00", "0,00"])
            continue
        sd = int(df["km_d"].sum())
        sp = int(df["km_p"].sum())
        stag = sum(berechne_taggeld_betrag(_safe_dauer_min(r["dauer"]), params)
                   for _, r in df.iterrows())
        mg = sd * km_satz
        total_d += sd; total_p += sp; total_km_geld += mg; total_taggeld += stag
        data.append([mname, sd, sp,
                     f"{mg:.2f}".replace('.', ','), f"{stag:.2f}".replace('.', ',')])

    data.append(["Summen", total_d, total_p,
                 f"{total_km_geld:.2f}".replace('.', ','),
                 f"{total_taggeld:.2f}".replace('.', ',')])
    t = Table(data, colWidths=[32*mm, 28*mm, 25*mm, 30*mm, 30*mm], repeatRows=2)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 1), colors.whitesmoke),
        ("SPAN", (1, 0), (2, 0)), ("SPAN", (3, 0), (4, 0)),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 1.5, colors.black),
    ]))
    story.append(t)
    story.append(Spacer(1, 12*mm))

    s_style = ParagraphStyle('Summary', parent=styles['Normal'], fontSize=9, leading=13)
    gesamt = total_km_geld + total_taggeld
    story.append(Paragraph(f"km-Geld Satz PKW amtlich ab 01.01.{jahr} "
                           f"EUR {km_satz:.2f}".replace('.', ','), s_style))
    story.append(Paragraph(f"km-Geld Satz PKW dienstlich ab 01.01.{jahr} EUR 0,00", s_style))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(f"km-Geld dienstlich für {total_d}km: EUR 0,00", s_style))
    story.append(Paragraph(f"km-Geld amtlich für {total_d}km inkl. Mitfahrer: "
                           f"EUR {total_km_geld:.2f}".replace('.', ','), s_style))
    story.append(Paragraph(f"Taggeld amtlich: EUR {total_taggeld:.2f}".replace('.', ','), s_style))
    story.append(Paragraph(f"Taggeld + km-Geld amtlich: EUR {gesamt:.2f}".replace('.', ','), s_style))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("Vom Dienstgeber vergütete Reisekosten: EUR 0,00", s_style))
    story.append(Paragraph(f"Für die Arbeitnehmerveranlagung zu berücksichtigen: "
                           f"EUR {total_km_geld:.2f}".replace('.', ','), s_style))
    story.append(Spacer(1, 10*mm))

    vehicle_rows = []
    total_veh = 0
    for _, fz in fahrzeuge_df.iterrows():
        name = str(fz.get('bezeichnung', '')).strip()
        if not name or name.lower() in ('none', 'nan'):
            continue
        km_jahr = 0
        for entry in monate_dict.values():
            mdf = entry.get("data") if isinstance(entry, dict) else entry
            if mdf is None or getattr(mdf, 'empty', True):
                continue
            for _, row in mdf.iterrows():
                if str(row.get('fahrzeug', '')).strip().lower() == name.lower():
                    km_jahr += _safe_int(row.get('km_d'))
        vehicle_rows.append((name, str(fz.get('kennzeichen', '')).strip(), km_jahr))
        total_veh += km_jahr

    vd = [["Fahrzeug", "Kennzeichen", "dienstl."]]
    vd += [[n, k, f"{km}"] for n, k, km in vehicle_rows]
    vd.append(["Summen", "", f"{total_veh}"])
    vt = Table(vd, colWidths=[40*mm, 30*mm, 25*mm])
    vt.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("ALIGN", (0, 1), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 1.5, colors.black),
    ]))
    story.append(vt)
    story.append(Spacer(1, 12*mm))

    disc = ParagraphStyle('Disclaimer', parent=styles['Normal'], fontSize=8,
                          leading=11, textColor=colors.grey)
    story.append(Paragraph("Die angegebenen Daten beruhen auf persönlichen Aufzeichnungen "
                           "der oben genannten Person. UNIQA übernimmt keine Haftung für "
                           "die Richtigkeit der Angaben.", disc))
    doc.build(story)
    buf.seek(0)
    return buf