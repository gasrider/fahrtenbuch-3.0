"""Monats-Fahrtenbuch als PDF."""
import io
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (Table, TableStyle, Paragraph, SimpleDocTemplate, Spacer)
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

from logic.constants import MONATE, WOCHENTAGE_KURZ
from logic.helpers import _safe_int, _safe_dauer_min
from logic.taggeld import berechne_taggeld, berechne_taggeld_betrag, taggeld_params_aus_settings


def create_monats_pdf(df, monat, jahr, user_info, fahrzeuge_df):
    monat_name = MONATE[monat - 1]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm,
                            topMargin=12*mm, bottomMargin=25*mm)
    story = []
    styles = getSampleStyleSheet()

    def footer(canvas, doc):
        canvas.saveState()
        page_num = canvas.getPageNumber()
        user_name = user_info.get('name', 'Unbekannt')
        text = (f"Erstellt von: {user_name} | Seite {page_num} | "
                f"Gedruckt: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 12*mm, 10*mm, text)
        canvas.restoreState()

    titel = Paragraph("Fahrtenbuch Monatsübersicht", styles['Heading2'])
    datum_p = Paragraph(f"{monat_name} {jahr}", styles['Heading2'])
    tt = Table([[titel, datum_p]], colWidths=[doc.width/2, doc.width/2])
    tt.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, 0), 16)]))
    story.append(tt)
    story.append(Spacer(1, 8*mm))

    fzg_list = [f"{i+1}-{r.get('bezeichnung','')} ({r.get('kennzeichen','')})"
                for i, r in fahrzeuge_df.iterrows()]
    stamm_data = [[Paragraph(f"Name: {user_info.get('name','')}", styles['Normal'])],
                  [Paragraph(f"PNR: {user_info.get('pnr','')}", styles['Normal'])],
                  [Paragraph(f"Wohnort: {user_info.get('wohnort','')}", styles['Normal'])],
                  [Paragraph(f"Dienstort: {user_info.get('dienstort','')}", styles['Normal'])],
                  [Paragraph(f"Entfernung zwischen Arbeitsplatz und Wohnung: "
                             f"{_safe_int(user_info.get('entfernung'))} km", styles['Normal'])],
                  [Paragraph("Fahrzeug(e): " + "  |  ".join(fzg_list), styles['Normal'])]]
    st = Table(stamm_data, colWidths=[doc.width])
    st.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                            ('FONTSIZE', (0, 0), (-1, -1), 9),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
    story.append(st)
    story.append(Spacer(1, 6*mm))
    line = Table([['']], colWidths=[doc.width])
    line.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, 0), 1, colors.black)]))
    story.append(line)
    story.append(Spacer(1, 4*mm))

    wrap_style = ParagraphStyle('wrap', parent=styles['Normal'],
                                fontName='Helvetica', fontSize=8, leading=9.6)
    headers = ["Tag", "Abf.", "Ank.", "Dauer", "Reiseweg - Ziel - Zweck",
               "Abfahrt", "gefahrene km", "amtlich.", "Taggeld", "KFZ"]
    sub = ["", "", "", "", "", "", "dienstl.", "privat", "", ""]
    data = [headers, sub]
    params = taggeld_params_aus_settings(user_info)

    for _, r in df.iterrows():
        dt = pd_to_dt(r["datum"])
        tag = f"{WOCHENTAGE_KURZ[dt.weekday()]}.{dt.day:02d}."
        route_para = Paragraph(str(r["route"]), wrap_style)
        dauer_min = _safe_dauer_min(r["dauer"])
        data.append([tag, str(r.get("abf", "00:00")), str(r.get("ank", "00:00")),
                     str(r.get("dauer", "00:00")), route_para,
                     _safe_int(r.get("abfahrt_km")), _safe_int(r.get("km_d")),
                     _safe_int(r.get("km_p")),
                     berechne_taggeld(dauer_min, params),
                     str(r.get("fahrzeug", ""))])

    sum_d = int(df["km_d"].sum())
    sum_p = int(df["km_p"].sum())
    sum_t = sum(berechne_taggeld_betrag(_safe_dauer_min(r["dauer"]), params)
                for _, r in df.iterrows())
    data.append(["Einzelsummen:", "", "", "", "", "", sum_d, sum_p,
                 f"{sum_t:.2f}".replace('.', ','), ""])

    col_widths = [12*mm, 10*mm, 10*mm, 12*mm, 71*mm, 15*mm, 15*mm, 15*mm, 12*mm, 18*mm]
    table = Table(data, colWidths=col_widths, repeatRows=2)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 1), 9), ("FONTSIZE", (0, 2), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("ALIGN", (4, 2), (4, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 1), colors.whitesmoke),
        ("SPAN", (6, 0), (7, 0)), ("SPAN", (0, -1), (4, -1)),
        ("BACKGROUND", (0, -1), (-1, -1), colors.whitesmoke),
    ]))
    story.append(table)
    story.append(Spacer(1, 5*mm))

    km_satz = float(user_info.get('km_geld', 0.42))
    for note in ["Privat-KM beinhalten die Fahrtstrecke Wohnung-Arbeitsplatz.",
                 f"km-Geld Satz PKW amtlich: EUR {km_satz:.2f}".replace('.', ',')]:
        story.append(Paragraph(note, styles['Normal']))
        story.append(Spacer(1, 3*mm))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buf.seek(0)
    return buf


def pd_to_dt(v):
    import pandas as pd
    return pd.to_datetime(v)