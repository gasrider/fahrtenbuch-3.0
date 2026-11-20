# Fahrtenbuch (PHP-Version) – Projektkontext für Claude Code

Mehrbenutzer-Fahrtenbuch-Generator einer kleinen Firma in Österreich (Wohnsitz Oberhofen/Zell am Moos, Dienstort Straßwalchen).
Läuft auf dem **World4You-Webhosting „Grow“** neben dem Notizbuch: geplant unter **https://va-strasswalchen.at/fahrtenbuch/**.
Ersetzt die Streamlit-/Supabase-Version (Ordner oberhalb, Branch `main`). Aufbau wie das Notizbuch-Projekt (gasrider/Notizbuch).
Betreiber: Christian (Admin, kein Entwickler, kann am PC nichts installieren). **Alle Texte Deutsch (Österreich), einfache Sprache.**

## Aufbau
```
app/                       ← wird 1:1 in den Ordner /fahrtenbuch gespielt
  index.html               ← komplette Oberfläche (Vanilla-JS, kein Build), Reiter wie die alte App
  api.php                  ← JSON-API, switch über ?action=…, Anmeldung per Header X-Auth-Token
  server/lib.php           ← DB (PDO MySQL), Schema create_schema() (idempotent!), Anmeldung, Einstellungen, Mail (SMTP/Graph/mail())
  server/logic.php         ← Fachlogik, 1:1 aus Python portiert (generator, hu_korrektur v5, privat_km, validation, taggeld, kalender)
  server/data.php          ← Datenzugriff je Benutzer + year_commit() (Kilometerkette!)
  server/pdf.php           ← eigener PDF-Schreiber (Helvetica/WinAnsi) + Monats-/Jahres-PDF im alten Layout
  server/import.php        ← .xlsx (ZipArchive+SimpleXML) / .csv lesen, Zuordnung wie excel_import.py
  server/routing.php       ← Nominatim + OSRM (Online-Distanzen), schrittweise von der App aufgerufen
  server/migrate.php       ← einmaliger Umzug aus Supabase (REST, tabellenweise)
  server/config.php        ← Vorlage; echte Datei schreibt der Installer, NIE ausliefern
build/make_installer.py    ← packt app/ in dist/installieren.php
dist/installieren.php      ← Auslieferung: per WebFTP in /fahrtenbuch hochladen und im Browser öffnen
tests/api_test.py          ← frische Installation + alle Fachregeln (braucht php + MariaDB root ohne Passwort)
tests/ui_test.mjs          ← Playwright gegen laufende Instanz (Desktop + iPhone, Überbreite, JS-Fehler)
```

## Harte Fachregeln (nie verletzen)
- **Kilometer-Anker + Kilometerkette sind heilig.** `fb_jahres_start_km` (username, jahr, fahrzeug_id) wird beim ersten Bedarf aus
  „Start-KM (Vorjahr)“ gesetzt und danach nicht mehr automatisch überschrieben (nur „Startwerte neu einlesen“ löscht ihn).
  JEDE Schreibaktion auf Fahrten läuft über `year_commit()`: ganzes Jahr ab Anker neu verketten, Folgejahres-Anker = Endstand,
  vorhandene Folgejahre werden nachgezogen (Kette lückenlos über Jahresgrenzen).
- Generator: Distanz zuerst aus `fb_distanz_matrix`, dann Differenz „km einfach“ (min. 8), dann Zufall 15–34. Monats-Skalierung 0,80–1,35.
- HU v5: Tacho bei Ankunft Werkstatt = exakt HU-Stand (Rest-km werden verteilt), Weg zur Werkstatt privat, Kundenstopps dienstlich,
  **nur einmal pro HU-Eintrag** (`fb_hu.angewendet_am`; wird beim Neu-Generieren des Monats zurückgesetzt).
- Taggeld nur bei km_d > 0. KM-Geld laut Stammdaten (0,42).
- `auto_correct_red_flags` (Kilometer verschleiern) wird bewusst NICHT umgesetzt. Erlaubt ist nur: Fahrzeit verlängern (>100 km/h).
- Excel-Import: ID-Spalten ignorieren, Zuordnung über Bezeichnung/Kennzeichen.

## Lokal testen
```bash
mkdir -p /run/mysqld && chown mysql:mysql /run/mysqld && (mysqld_safe &) && sleep 6
python3 tests/api_test.py                 # baut den Installer, installiert frisch, ~80 Prüfungen
# UI: Instanz aufsetzen (siehe api_test.py) und dann
BASE=http://127.0.0.1:8793/fahrtenbuch/ node tests/ui_test.mjs
```
**Definition of Done:** `php -l` auf allen PHP-Dateien, JS-Syntax (`sed -n '/^<script>$/,/^<\/script>$/p' app/index.html | sed '1d;$d' > /tmp/a.js && node --check /tmp/a.js`),
beide Tests grün, `sw.js`-CACHE hochzählen, `python3 build/make_installer.py`. Dem Betreiber nur die neue `installieren.php` geben.

## Stolperfallen
- PHP ≥ 7.4 kompatibel bleiben (keine PHP-8-only-Syntax: kein match, keine Union-Types, kein str_contains).
- Shared Hosting: Zeitlimit ~30–60 s. Lange Arbeiten (Online-Karte, Supabase-Umzug) laufen schrittweise, von der App gesteuert.
- Spalten mit Ortsnamen/Benutzernamen sind `utf8mb4_bin` (sonst wäre „ß“ = „ss“ und „ä“ = „a“).
- `fb_orte.km_einfach` NULL = unbekannt, 0 = am Wohnort (nicht verwechseln!).
- opcache: Installer ruft `opcache_invalidate()` auf. Groß-/Kleinschreibung der Ordner beachten (`fahrtenbuch`).
