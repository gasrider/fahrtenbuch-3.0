# Fahrtenbuch (PHP-Version) – Projektkontext

Nachfolger der Streamlit-App (Python im Repo-Wurzelverzeichnis). Läuft auf World4You-Webhosting (PHP 8 + MySQL), Aufbau wie das Notizbuch (`gasrider/Notizbuch`).
Betreiber: Christian (Admin, kein Entwickler, nur WebFTP im Browser). Nutzertexte Deutsch (Österreich), du-Form.

## Aufbau
```
app/                     ← wird 1:1 auf den Server gespielt (Ordner /fahrtenbuch)
  index.html             ← komplette Oberfläche (Vanilla-JS, kein Build). Tabs: Stammdaten, Generator, Fahrzeuge & Orte, Privat-KM, Prüfung, Export & HU, Admin
  api.php                ← JSON-API (?action=…), Token im Header X-Auth-Token
  server/lib.php         ← DB (Tabellen fb_*), Login, Einstellungen, Mail (SMTP / PHP / Microsoft Graph)
  server/logic.php       ← Fachlogik, 1:1 aus Python: Generator v5, baue_kette_neu, Prüfung, Taggeld, HU (Doppelschutz, km-genau), Privat-KM
  server/import.php      ← xlsx/csv-Leser (ZipArchive) + Import-Normalisierung
  server/pdf.php         ← Monats-/Jahres-PDF (FPDF 1.9, server/fpdf.php + font/)
  server/config.php      ← Vorlage; produktiv vom Installer erzeugt, NIE im Paket
build/make_installer.py  ← packt app/ in dist/installieren.php
tests/e2e.py             ← Installation + Supabase-Übernahme (Fake) + alle Funktionen (braucht php, MariaDB)
tests/ui.mjs             ← Playwright gegen laufende Instanz (KEEP=1 python3 tests/e2e.py)
```

## Regeln (aus dem Projektverlauf)
- Kilometerkette nach JEDER Änderung über `baue_kette_neu()` ab dem Jahres-Anker (`fb_start_km`), danach Startwert `jahr+1` setzen.
- Fahrzeug-IDs stabil (69/70/71): Update statt Delete+Insert, Excel-IDs ignorieren, Zuordnung über Bezeichnung.
- HU nur einmal: Tag mit „(HU)“-Route wird übersprungen (Ausnahme: Neuausrichtung nach Abgleich-Korrektur, zielt immer auf den echten HU-Stand).
- Taggeld nur bei km_d > 0.
- Passwort vergessen: erst Mail senden, dann Passwort ändern.
- Alte Streamlit-Passwörter: `sha256:<hex>` in fb_users.pass_hash, beim Login auf password_hash umgestellt.
- Ortssuche (geo_one): Wohnort zuerst; andere Orte nur im Umkreis (viewbox), nächster Treffer gewinnt, > 100 km Luftlinie wird abgelehnt. Grund: „Neumarkt“ landete in der Steiermark (≈ 290 km) → Fahrten mit hunderten Dienst-km.
- Strecken > PLAUSI_LEG_KM (120 km) ignoriert Generator und HU (Warnung „verdacht“); Prüfung meldet Dienstfahrten > 360 km.
- HU skaliert nur km, nie die Fahrzeit (sonst 14:00-Fahrten); Fahrzeit nur bei > 100 km/h verlängert.
- Orte kommen aus vielen Quellen (`orte_quellen()`): Orte-Liste, Keywords aller Jahre, HU, Routen gespeicherter Fahrten. geo_plan nimmt alle auf (und trägt sie in fb_orte ein), Orte-Check zeigt sie mit Herkunft.
- Gesamt-Abgleich (`fahrten_abgleich()`): erwartete km = Strecke laut Matrix × Median-Faktor des Monats; auffällig > 2,2× oder > 360 km. Korrektur setzt km, baut Kette neu und richtet HUs des Jahres neu aus (`wende_hu_an(..., true)`).
- Speichern immer über `speichere_mit_kette()`: zieht die Kette auch in Folgejahren mit Daten nach.
- Fahrzeuge mit Fahrten nicht löschbar; Fahrten im Monats-Editor landen im Monat ihres Datums.
- Ortssuche nutzt Nominatim (Umkreis) + Photon (Nähe-Bias, verzeiht Tippfehler) + Nominatim ohne Umkreis; nächster Treffer ≤ 100 km. Anderer Name gefunden → `vorschlag`. Dienst-Ausfall wird als solcher gemeldet. Hinweis der letzten Suche in fb_koordinaten.hinweis.
- `ort_umbenennen`: korrigiert einen Ortsnamen überall (Keywords aller Jahre, fb_orte, fb_hu, Routen in fb_fahrten), verwirft alte Koordinaten/Strecken.
- Element.prototype.append/replaceChildren sind gepatcht (null/false werden übersprungen) – sonst erscheint „null“ als Text.
- Sicherung/Wiederherstellung (JSON, nur eigene Daten) im Tab Stammdaten.
- Schema-Änderungen idempotent in `create_schema()` (läuft auch beim Update).

## Definition of Done
`php -l` auf allen PHP-Dateien, JS-Check (`sed -n '/^<script>$/,/^<\/script>$/p' app/index.html | sed '1d;$d' > /tmp/a.js && node --check /tmp/a.js`),
`python3 tests/e2e.py` grün, `tests/ui.mjs` grün, `sw.js`-CACHE hochzählen, `python3 build/make_installer.py`.
