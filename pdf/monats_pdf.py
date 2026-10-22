# pdf/monats_pdf.py
# Monats-PDF: tagesgenaue Fahrtenliste mit Taggeld-Spalte.
#
# AENDERUNG (Taggeld-Fix):
# Taggeld wird NUR noch fuer echte Dienstfahrten berechnet (km_d > 0).
# Reine Privatfahrten (km_d = 0) zeigen in der Taggeld-Spalte 0,00
# und zaehlen auch nicht in die Taggeld-Summe.

import io
from datetime import datetime

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from logic.constants import MONATE
from logic.helpers import _safe_dauer_min, _safe_int
from logic.taggeld import berechne_taggeld


def create_monats_pdf(df, monat, jahr, user_info, fahrzeuge_df):
    monat_name = MONATE[monat - 1]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=25 * mm)
    story = []
    styles = getSampleStyleSheet()

    def footer(canvas, doc):
        canvas.saveState()
        page_num = canvas.getPageNumber()
        user_name = user_info.get('name', 'Unbekannt')
        footer_text = f"Erstellt von: {user_name} | Seite {page_num} | Gedruckt: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 12 * mm, 10 * mm, footer_text)
        canvas.restoreState()

    titel_para = Paragraph("Fahrtenbuch Monatsübersicht", styles['Heading2'])
    datum_para = Paragraph(f"{monat_name} {jahr}", styles['Heading2'])
    title_table = Table([[titel_para, datum_para]], colWidths=[doc.width / 2, doc.width / 2])
    title_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'LEFT'), ('ALIGN', (1, 0), (1, 0), 'RIGHT'), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, 0), 16)]))
    story.append(title_table)
    story.append(Spacer(1, 8 * mm))

    fzg_list = [f"{i + 1}-{r.get('bezeichnung', '')} ({r.get('kennzeichen', '')})" for i, r in fahrzeuge_df.iterrows()]
    fzg_string = "  |  ".join(fzg_list)
    stamm_data = [
        [Paragraph(f"Name: {user_info.get('name', '')}", styles['Normal'])],
        [Paragraph(f"PNR: {user_info.get('pnr', '')}", styles['Normal'])],
        [Paragraph(f"Wohnort: {user_info.get('wohnort', '')}", styles['Normal'])],
        [Paragraph(f"Dienstort: {user_info.get('dienstort', '')}", styles['Normal'])],
        [Paragraph(f"Entfernung zwischen Arbeitsplatz und Wohnung: {_safe_int(user_info.get('entfernung'))} km", styles['Normal'])],
        [Paragraph("Fahrzeug(e): " + fzg_string, styles['Normal'])],
    ]
    stamm_table = Table(stamm_data, colWidths=[doc.width])
    stamm_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'LEFT'), ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'), ('FONTSIZE', (0, 0), (-1, -1), 9), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
    story.append(stamm_table)
    story.append(Spacer(1, 6 * mm))

    story.append(Table([['']], colWidths=[doc.width]))
    story[-1].setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, 0), 1, colors.black)]))
    story.append(Spacer(1, 4 * mm))

    wrap_style = ParagraphStyle('wrap', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=9.6)
    headers = ["Tag", "Abf.", "Ank.", "Dauer", "Reiseweg - Ziel - Zweck", "Abfahrt", "gefahrene km", "amtlich.", "Taggeld", "KFZ"]
    sub_headers = ["", "", "", "", "", "", "dienstl.", "privat", "", ""]
    data = [headers, sub_headers]

    # Taggeld-Parameter fuer den Monat
    taggeld_params = {
        'min_stunden': user_info.get('taggeld_min_stunden', 5),
        'basis': user_info.get('taggeld_basis', 10.00),
        'stufung': user_info.get('taggeld_stufung', 2.50),
        'max_betrag': user_info.get('taggeld_max_betrag', 30.00),
        'max_stunden': user_info.get('taggeld_max_stunden', 13),
    }

    german_day_abbr = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    for _, r in df.iterrows():
        dt = pd.to_datetime(r["datum"])
        tag_name = german_day_abbr[dt.weekday()]
        tag = f"{tag_name[:2]}.{dt.day:02d}."
        route_para = Paragraph(str(r["route"]), wrap_style)
        dauer_min = _safe_dauer_min(r["dauer"])
        km_d_wert = _safe_int(r.get("km_d", 0))

        # TAGGELD-FIX: Taggeld nur bei echter Dienstfahrt (km_d > 0)
        if km_d_wert > 0:
            taggeld_text = berechne_taggeld(dauer_min, taggeld_params)
        else:
            taggeld_text = "0,00"

        data.append([tag, str(r.get("abf", "00:00")), str(r.get("ank", "00:00")), str(r.get("dauer", "00:00")), route_para, _safe_int(r.get("abfahrt_km")), km_d_wert, _safe_int(r.get("km_p")), taggeld_text, str(r.get("fahrzeug", ""))])

    sum_dienstl = int(df["km_d"].sum())
    sum_privat = int(df["km_p"].sum())

    # TAGGELD-FIX: Summe nur ueber echte Dienstfahrten (km_d > 0)
    sum_taggeld = 0.0
    for _, r in df.iterrows():
        if _safe_int(r.get("km_d", 0)) > 0:
            sum_taggeld += float(berechne_taggeld(_safe_dauer_min(r.get("dauer")), taggeld_params).replace(',', '.'))

    data.append(["Einzelsummen:", "", "", "", "", "", sum_dienstl, sum_privat, f"{sum_taggeld:.2f}".replace('.', ','), ""])

    col_widths = [12 * mm, 10 * mm, 10 * mm, 12 * mm, 71 * mm, 15 * mm, 15 * mm, 15 * mm, 12 * mm, 18 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=2)
    style = TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 1), 9), ("FONTSIZE", (0, 2), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("ALIGN", (4, 2), (4, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 1), colors.whitesmoke), ("SPAN", (6, 0), (7, 0)),
        ("SPAN", (0, -1), (4, -1)), ("BACKGROUND", (0, -1), (-1, -1), colors.whitesmoke),
    ])
    table.setStyle(style)
    story.append(table)
    story.append(Spacer(1, 5 * mm))

    km_satz = float(user_info.get('km_geld', 0.42))
    notes = [
        "Privat-KM beinhalten die Fahrtstrecke Wohnung-Arbeitsplatz.",
        f"km-Geld Satz PKW amtlich: EUR {km_satz:.2f}".replace('.', ',')]
    for note in notes:
        story.append(Paragraph(note, styles['Normal']))
        story.append(Spacer(1, 3 * mm))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buf.seek(0)
    return buf
