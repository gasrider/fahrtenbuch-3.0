# pdf/jahres_pdf.py
# Jahres-PDF: Monatstabelle, Finanz-Zusammenfassung, Fahrzeugübersicht.
#
# AENDERUNG (Taggeld-Fix):
# Taggeld wird NUR noch fuer echte Dienstfahrten berechnet (km_d > 0).
# Reine Privatfahrten (km_d = 0) erhalten kein Taggeld mehr.

import io

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from logic.constants import MONATE
from logic.helpers import _safe_dauer_min, _safe_int
from logic.taggeld import berechne_taggeld_betrag


def _taggeld_params(user_info):
    """Taggeld-Parameter aus den User-Einstellungen lesen."""
    return {
        "min_stunden": user_info.get("taggeld_min_stunden", 5),
        "basis": user_info.get("taggeld_basis", 10.00),
        "stufung": user_info.get("taggeld_stufung", 2.50),
        "max_betrag": user_info.get("taggeld_max_betrag", 30.00),
        "max_stunden": user_info.get("taggeld_max_stunden", 13),
    }


def _monats_taggeld(df, taggeld_params):
    """Taggeld-Summe fuer einen Monat.

    WICHTIG (Taggeld-Fix): Taggeld zaehlt ausschliesslich fuer Tage
    mit echter Dienstfahrt (km_d > 0). Reine Privatfahrten (km_d = 0)
    zaehlen nicht, egal wie lang die gespeicherte Dauer ist.
    """
    total = 0.0
    for _, r in df.iterrows():
        if _safe_int(r.get("km_d", 0)) <= 0:
            continue  # Privatfahrt: kein Taggeld
        total += berechne_taggeld_betrag(_safe_dauer_min(r.get("dauer")), taggeld_params)
    return total


def create_jahres_pdf(generated_data, jahr, user_info, fahrzeuge_df):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )
    story = []
    styles = getSampleStyleSheet()

    # Taggeld-Parameter fuer das Jahr
    taggeld_params = _taggeld_params(user_info)

    if fahrzeuge_df is None:
        fahrzeuge_df = pd.DataFrame()

    # ===== TITEL (18pt) =====
    title_style = ParagraphStyle('JahrTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=18, spaceAfter=8 * mm)
    story.append(Paragraph(f"Fahrtenbuch Jahresübersicht {jahr}", title_style))

    # ===== KOPFZEILEN (12pt) =====
    info_style = ParagraphStyle('Info', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=14)
    fzg_list = [f"{r.get('bezeichnung', '')} ({r.get('kennzeichen', '')})" for _, r in fahrzeuge_df.iterrows()]
    story.append(Paragraph(f"Name: {user_info.get('name', '')}", info_style))
    story.append(Paragraph(f"PNR: {user_info.get('pnr', '')}", info_style))
    story.append(Paragraph(f"Wohnort: {user_info.get('wohnort', '')}", info_style))
    story.append(Paragraph(f"Dienstort: {user_info.get('dienstort', '')}", info_style))
    story.append(Paragraph(f"Entfernung zwischen Arbeitsplatz und Wohnung: {_safe_int(user_info.get('entfernung'))} km", info_style))
    story.append(Paragraph(f"Fahrzeug(e): {', '.join(fzg_list)}", info_style))
    story.append(Spacer(1, 8 * mm))

    # ===== HAUPTTABELLE =====
    # Zeile 1: Monat | gefahren km (SPAN) | km-Geld (SPAN)
    # Zeile 2: Monat | dienstl. | privat | PKW | EUR
    header_row1 = ["Monat", "gefahren km", "", "km-Geld", ""]
    header_row2 = ["Monat", "dienstl.", "privat", "PKW", "EUR"]
    data = [header_row1, header_row2]

    km_geld_satz = float(user_info.get('km_geld', 0.42))
    total_dienstl = 0
    total_privat = 0
    total_km_geld = 0
    total_taggeld = 0.0

    for i, monat_name in enumerate(MONATE):
        monat_key = (jahr, i + 1)
        if monat_key in generated_data:
            month_data = generated_data[monat_key]
            df = month_data.get("data") if isinstance(month_data, dict) else month_data
            if df is None or df.empty:
                data.append([monat_name, 0, 0, "0,00", "0,00"])
                continue

            sum_dienstl = int(df["km_d"].sum())
            sum_privat = int(df["km_p"].sum())

            # TAGGELD-FIX: nur Tage mit echter Dienstfahrt (km_d > 0) zaehlen
            sum_taggeld = _monats_taggeld(df, taggeld_params)
            month_km_geld = sum_dienstl * km_geld_satz

            total_dienstl += sum_dienstl
            total_privat += sum_privat
            total_km_geld += month_km_geld
            total_taggeld += sum_taggeld
            data.append([monat_name, sum_dienstl, sum_privat, f"{month_km_geld:.2f}".replace('.', ','), f"{sum_taggeld:.2f}".replace('.', ',')])
        else:
            data.append([monat_name, 0, 0, "0,00", "0,00"])

    data.append(["Summen", total_dienstl, total_privat, f"{total_km_geld:.2f}".replace('.', ','), f"{total_taggeld:.2f}".replace('.', ',')])

    col_widths = [32 * mm, 28 * mm, 25 * mm, 30 * mm, 30 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=2)
    table_style = TableStyle([
        # Header Zeile 1
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 1), colors.whitesmoke),
        # Spans
        ("SPAN", (1, 0), (2, 0)),  # "gefahren km" über dienstl./privat
        ("SPAN", (3, 0), (4, 0)),  # "km-Geld" über PKW/EUR
        # Ausrichtung
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # Rahmen
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        # Summen-Zeile
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 1.5, colors.black),
    ])
    table.setStyle(table_style)
    story.append(table)
    story.append(Spacer(1, 12 * mm))

    # ===== ZUSAMMENFASSUNG (Finanzen) =====
    sum_style = ParagraphStyle('Summary', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=13)
    gesamt_amtlich = total_km_geld + total_taggeld
    story.append(Paragraph(f"km-Geld Satz PKW amtlich ab 01.01.{jahr} EUR {km_geld_satz:.2f}", sum_style))
    story.append(Paragraph(f"km-Geld Satz PKW dienstlich ab 01.01.{jahr} EUR 0,00", sum_style))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(f"km-Geld dienstlich für {total_dienstl}km: EUR 0,00", sum_style))
    story.append(Paragraph(f"km-Geld amtlich für {total_dienstl}km inkl. Mitfahrer: EUR {total_km_geld:.2f}".replace('.', ','), sum_style))
    story.append(Paragraph(f"Taggeld amtlich: EUR {total_taggeld:.2f}".replace('.', ','), sum_style))
    story.append(Paragraph(f"Taggeld + km-Geld amtlich: EUR {gesamt_amtlich:.2f}".replace('.', ','), sum_style))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Vom Dienstgeber vergütete Reisekosten: EUR 0,00", sum_style))
    story.append(Paragraph(f"Für die Arbeitnehmerveranlagung zu berücksichtigen: EUR {total_km_geld:.2f}".replace('.', ','), sum_style))
    story.append(Spacer(1, 10 * mm))

    # ===== FAHRZEUGÜBERSICHT =====
    # Fuer JEDES Fahrzeug aus fahrzeuge_df die dienstlichen KM aus allen
    # Monaten zusammenzaehlen. .tolist() konvertiert Arrow/numpy zu reinem
    # Python fuer maximale Kompatibilitaet.
    vehicle_rows = []  # list of (name, kennzeichen, km_d)
    total_km_d_veh = 0
    for _, fz_row in fahrzeuge_df.iterrows():
        fz_name = str(fz_row.get('bezeichnung', '')).strip()
        fz_kz = str(fz_row.get('kennzeichen', '')).strip()
        if not fz_name or fz_name.lower() in ('none', 'nan'):
            continue
        km_d_jahr = 0
        for month_key, month_data in generated_data.items():
            try:
                mdf = month_data.get('data') if isinstance(month_data, dict) else month_data
                if mdf is None or (hasattr(mdf, 'empty') and mdf.empty):
                    continue
                col_list = list(mdf.columns)
                if 'fahrzeug' not in col_list or 'km_d' not in col_list:
                    continue
                fz_vals = mdf['fahrzeug'].tolist()
                km_vals = mdf['km_d'].tolist()
                for fz_val, km_val in zip(fz_vals, km_vals):
                    try:
                        cell_fz = str(fz_val).strip() if fz_val is not None else ''
                        if cell_fz.lower() == fz_name.lower():
                            if km_val is not None:
                                km_d_jahr += int(float(str(km_val)))
                    except (ValueError, TypeError):
                        continue
            except Exception:
                continue
        vehicle_rows.append((fz_name, fz_kz, km_d_jahr))
        total_km_d_veh += km_d_jahr

    veh_headers = ["Fahrzeug", "Kennzeichen", "dienstl."]
    veh_data = [veh_headers]
    for name, kz, km in vehicle_rows:
        veh_data.append([name, kz, f"{km}"])
    veh_data.append(["Summen", "", f"{total_km_d_veh}"])

    veh_col_widths = [40 * mm, 30 * mm, 25 * mm]
    vehicle_table = Table(veh_data, colWidths=veh_col_widths)
    vehicle_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 1), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 1.5, colors.black),
    ]))
    story.append(vehicle_table)
    story.append(Spacer(1, 12 * mm))

    # ===== DISCLAIMER =====
    disc_style = ParagraphStyle('Disclaimer', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=11, textColor=colors.grey)
    story.append(Paragraph("Die angegebenen Daten beruhen auf persönlichen Aufzeichnungen der oben genannten Person. UNIQA übernimmt keine Haftung für die Richtigkeit der Angaben.", disc_style))

    doc.build(story)
    buf.seek(0)
    return buf
