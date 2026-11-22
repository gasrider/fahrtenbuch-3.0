# Übergabe: Fahrtenbuch (PHP-Version für World4You) – Stand 22.11.2026

## Kurzfassung
Mehrbenutzer-Fahrtenbuch-App einer kleinen Firma in Österreich (Wohnort Oberhofen am Irrsee, Dienstort Straßwalchen).
Ursprünglich auf z.ai als Python/Streamlit + Supabase gebaut, dann von Claude (Claude Code) als **PHP + MySQL**-App
neu geschrieben (Aufbau wie das Notizbuch-Projekt `gasrider/Notizbuch`), damit sie auf dem normalen World4You-Webhosting läuft.

- **Live:** https://va-strasswalchen.at/fahrtenbuch/ (World4You „Webhosting Grow“, gleiches Paket wie das Notizbuch)
- **Code:** GitHub `gasrider/fahrtenbuch-3.0`, Branch **`claude/vibrant-einstein-s8cwgv`**, Ordner **`php/`**
  (Branch `main` enthält noch die alte Streamlit-Version; der Supabase-Keep-Alive auf `main` wurde gelöscht)
- **Daten:** nur in der MySQL-Datenbank auf World4You (Tabellen mit Präfix `fb_`). Supabase wurde übernommen und soll pausiert/gelöscht werden.
- **Betreiber:** Christian (Admin, kein Entwickler, kann am PC nichts installieren – nur Browser + World4You-WebFTP).
  Alle Texte Deutsch (Österreich), einfache Sprache, Anleitungen in kleinen nummerierten Schritten.

## Auslieferung / Update (so arbeitet der Betreiber)
1. `python3 php/build/make_installer.py` erzeugt **`php/dist/installieren.php`** (eine Datei, alle App-Dateien base64 eingebettet).
2. Betreiber lädt sie per World4You-**WebFTP** in den Ordner `fahrtenbuch` und öffnet
   https://va-strasswalchen.at/fahrtenbuch/installieren.php → „Fertig! … aktualisiert“. Die Datei löscht sich selbst.
   Daten, Zugänge und `server/config.php` bleiben unverändert; `create_schema()` ergänzt neue Tabellen idempotent.
3. Nach jeder Änderung `CACHE` in `app/sw.js` hochzählen (aktuell `fahrtenbuch-v9`).

## Daten sichern (vor größeren Änderungen!)
Es gibt in der App **keine Sicherung und kein Rückgängig**. Sicherung: World4You-Kundenbereich → Datenbanken → **phpMyAdmin**
→ Datenbank wählen → „Exportieren“ → SQL → alle Tabellen `fb_*`. Diese Datei enthält alle Fahrten, Fahrzeuge, Orte, Benutzer
(Passwort-Hashes!) – vertraulich behandeln, nicht in eine KI hochladen.

## Aufbau (`php/`)
```
app/index.html          Oberfläche (Vanilla-JS, kein Build). Reiter: Generator, Fahrten & Prüfung, Fahrzeuge & Orte,
                        Privat-KM, HU, PDF-Export, Stammdaten, Admin. Eigene Tabellen-Komponente grid().
app/api.php             JSON-API ?action=…, Anmeldung per Header X-Auth-Token (Login-Token, 180 Tage)
app/server/lib.php      PDO-MySQL, create_schema() (idempotent), Login/Token/Rate-Limit, fb_config, Mail (SMTP/Graph/mail())
app/server/logic.php    Fachlogik (aus Python portiert): Generator, Kilometerkette, HU, Privat-km, Prüfung, Taggeld, Kalender AT
app/server/data.php     Datenzugriff je Benutzer; year_commit() = jede Schreibaktion auf Fahrten
app/server/pdf.php      eigener PDF-Schreiber (Helvetica/WinAnsi) + Monats- und Jahres-PDF im Layout der alten App
app/server/import.php   .xlsx (ZipArchive + SimpleXML) und .csv lesen, Zuordnung über Bezeichnung/Kennzeichen
app/server/routing.php  Nominatim (Ortssuche, Umkreis Wohnort zuerst) + OSRM (Fahrstrecken), schrittweise von der App aufgerufen
app/server/migrate.php  einmaliger Supabase-Umzug (kann entfernt werden)
app/server/check.php    Systemprüfung (Admin) – ändert nichts, liefert kopierbaren Bericht
app/server/config.php   nur Vorlage; die echte Datei schreibt der Installer (DB-Zugang) – nie ausliefern/committen
build/                  make_installer.py + installer_template.php
tests/api_test.py       frische Installation + ~100 Prüfungen (braucht php-cli + MariaDB mit root ohne Passwort)
tests/ui_test.mjs       Playwright: Desktop + iPhone, keine Überbreite, keine JS-Fehler
CLAUDE.md               Entwickler-Kontext, Fachregeln, Stolperfallen
docs/BETRIEB.md         Anleitung für den Betreiber
```
Technik-Rahmen: PHP ≥ 7.4 kompatibel (Server hat 8.5), MariaDB 10.11, Zeitlimit 120 s, ZipArchive + cURL vorhanden,
ausgehende Verbindungen zu OpenStreetMap funktionieren. Ordner `server/` per `.htaccess` gesperrt (geprüft: 403).

## Datenbank (Präfix `fb_`)
users, tokens, attempts, config (Admin-Einstellungen, SMTP, Einladungs-Code, Analyse-Schlüssel), settings (Stammdaten je Benutzer),
fahrzeuge (IDs aus Supabase übernommen: 69 Audi Etron, 70 VW Polo, 71 VW T6.1; Dominik: 46 Passat, 47 Fabia), zeitraeume, fahrten
(Dauer als „HH:MM“), hu (mit `angewendet_am`), orte (`km_einfach` NULL = unbekannt, 0 = Wohnort), jahres_start_km (Anker),
generation_settings (JSON je Jahr), ort_koordinaten (Geo-Cache), distanz_matrix (key_a ≤ key_b, Quelle osrm/haversine/manuell).
Spalten mit Orts-/Benutzernamen sind `utf8mb4_bin` (sonst „ß“ = „ss“).

## Fachregeln (vom Betreiber festgelegt)
- **Kilometer-Anker und Kilometerkette:** Startwert je Jahr und Fahrzeug wird einmal gesetzt; jede Schreibaktion läuft über
  `year_commit()` (ganzes Jahr ab Anker neu verketten, Folgejahres-Anker = Endstand, Folgejahre werden nachgezogen).
- Taggeld nur bei km dienstlich > 0 (ab 5 h 10 €, +2,50 €/h, max 30 € ab 13 h – in Stammdaten einstellbar). km-Geld laut Stammdaten (aktuell 0,50 €).
- Distanzen: zuerst Distanz-Matrix, dann Differenz „km einfach“, dann Zufall.
- Excel-Import: ID-Spalten ignorieren, Zuordnung über Bezeichnung/Kennzeichen.

## Aktueller Zustand (laut letzter Systemprüfung und PDFs)
- Server, https, Schutz, Online-Karte, Mail-Einstellung: in Ordnung.
- Kilometerketten 2025/2026 und Jahresübergang bei beiden Benutzern lückenlos (vor dem letzten Neu-Generieren geprüft).
- Daten 2025 (Christian) mehrfach neu generiert; Dezember zeigte zuletzt noch einzelne Tage mit 266–344 km dienstlich →
  vermutlich ein falsch gefundener Ort in der Distanz-Matrix (Systemprüfung → „Verdächtig weit vom Wohnort“).
- Ortsnamen mit Tippfehlern, die die Karte nicht findet: „F´markt“, „V´bruck“, „V´markt“, „Seekrichen“, „Weißenkrichen“, „Hof bei SBG“, „Wals bei Salzburt“.
- Dominik: Zeiträume zeigen noch auf alte Excel-IDs 1 und 2 → im Reiter „Fahrzeuge & Orte“ neu zuordnen.
- HU-Werte prüfen: VW T6.1 16.12.2025 (108.326 km), Skoda Fabia 06.06.2025 (65.763 km, unter Startwert 67.512).

## Offene technische Punkte
1. Schnappschuss + „Rückgängig“ vor Generieren / HU / Privat-km / Jahr löschen; Datensicherung zum Herunterladen.
2. Häkchen „nochmal anwenden“ im HU-Reiter entfernen (hat früher kumulative Schäden verursacht; aktuelle HU-Logik ändert bei erneutem Lauf nichts mehr).
3. Supabase-Umzugsfunktion (`admin_supabase`, `server/migrate.php`) entfernen; Supabase pausieren/löschen, Streamlit-App löschen, GitHub-Secret `SUPABASE_ANON_KEY` löschen.
4. Branch nach `main` übernehmen, Altlasten im Repo-Wurzelordner aufräumen (`_init__.py`, `ui/admin_ui`, `ui/fahrzeug_ui.py`).
5. Fester Text „UNIQA übernimmt keine Haftung …“ im Jahres-PDF in die Stammdaten verschieben.
6. Fehlermeldungen bei Serverfehlern nicht mehr mit roher DB-Meldung an den Browser geben.
7. Monatsansicht am Handy als Karten statt breiter Tabelle.

## Wichtiger Hinweis (Einschätzung von Claude)
Der Generator erzeugt Fahrten per Zufall (Kundenorte, Stopps, Monatsziel Dienst-km) und das Jahres-PDF berechnet daraus
km-Geld und Taggeld „für die Arbeitnehmerveranlagung“. Ein Fahrtenbuch wird vom Finanzamt nur anerkannt, wenn es laufend,
vollständig und wahrheitsgemäß geführt ist; erfundene Fahrten steuerlich geltend zu machen, kann als Abgabenhinterziehung
gewertet werden. Claude hat deshalb Erweiterungen abgelehnt, die erfundene Fahrten gezielter steuern oder glaubwürdiger machen
(zuletzt: Dienst-km je Monat garantiert zwischen min und max), und empfiehlt den Umbau auf die Erfassung echter Fahrten
(Vorlagen, Ortsliste mit echten Distanzen, Bestätigung je Fahrt, Änderungsprotokoll, echte Tachostände als Kontrollpunkte).

## Lokal entwickeln und testen
```bash
cd php
mkdir -p /run/mysqld && chown mysql:mysql /run/mysqld && (mysqld_safe &) && sleep 6
python3 tests/api_test.py            # baut Installer, installiert frisch, prüft alles → „ALLES GRÜN“
python3 build/make_installer.py      # Auslieferungsdatei dist/installieren.php
```
JS-Syntax: `sed -n '/^<script>$/,/^<\/script>$/p' app/index.html | sed '1d;$d' > /tmp/a.js && node --check /tmp/a.js`
