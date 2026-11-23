# Fahrtenbuch 3.0 (Multi-User)

Fahrtenbuch-App mit Fahrten-Generator, lückenloser Kilometerkette,
Plausibilitätsprüfung, HU-Korrektur, Privat-KM-Verteilung, Taggeld und
PDF-Export (Monat + Jahr). Läuft komplett online:

| Teil | Dienst |
|---|---|
| Code | GitHub (`main`) |
| App | Streamlit Cloud – baut nach jedem Commit automatisch neu |
| Daten | Supabase (Postgres) |

## Einrichtung

**Streamlit Cloud → App → Settings → Secrets:**

```
SUPABASE_URL = "https://<projekt>.supabase.co"
SUPABASE_KEY = "<service_role-key>"
INVITE_CODE  = "<Code für neue Registrierungen>"   # optional
ADMIN_USERNAMES = "name1,name2"                    # optional
```

**GitHub → Settings → Secrets and variables → Actions:** `SUPABASE_KEY`
(gleicher Wert) – für den Keep-Alive-Workflow
(`.github/workflows/keepalive.yml`), der das Supabase-Free-Projekt wach hält.

## Ablauf in der App

1. **Stammdaten** – Name, Wohnort, Dienstort, Entfernung, Taggeld-Sätze
2. **Fahrzeuge & Orte** – Fahrzeuge, Nutzungszeiträume, Orte; Distanzen online berechnen
3. **Generator** – Jahr wählen, Eckdaten einstellen, generieren, Fahrten bearbeiten
4. **Privat-KM verteilen** – Jahressumme privat auf das Jahr verteilen
5. **Plausibilitätsprüfung** – Auffälligkeiten ansehen und korrigieren
6. **Export & HU** – PDFs erzeugen, HU-Stände eintragen und einmalig anwenden

Jede Änderung an Fahrten baut die Kilometerkette des ganzen Jahres neu auf –
immer ab dem gesperrten Jahres-Startwert (Tabelle `jahres_start_km`).

## Projektstruktur

```
app.py        Einstieg
config.py     Supabase-Verbindung (Secrets)
database/     Lesen/Speichern in Supabase
logic/        Generator, Kilometerkette (kette.py), HU, Privat-KM, Taggeld, Prüfung
services/     E-Mail (SMTP), Online-Distanzen (OpenStreetMap/OSRM)
pdf/          Monats- und Jahres-PDF
ui/           Bildschirmseiten (Tabs)
```

## Supabase-Tabellen

users, settings, fahrzeuge, zeitraeume, fahrten, hu_corrections, orte,
orte_distanz, ort_koordinaten, distanz_matrix, jahres_start_km,
generation_settings, system_config. RLS ist deaktiviert – Zugriff nur über
den `service_role`-Key in den Streamlit Secrets.
