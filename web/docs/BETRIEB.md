# Fahrtenbuch auf World4You – Betrieb (für den Admin)

**Adresse (Vorschlag):** https://va-strasswalchen.at/fahrtenbuch/ · **Hosting:** World4You (gleiches Paket wie das Notizbuch)

## Erste Installation (einmalig, ca. 10 Minuten)
1. Datei `dist/installieren.php` aus GitHub herunterladen (Repo `gasrider/fahrtenbuch-3.0`, Ordner `web/dist`, Knopf „Download raw file“).
2. World4You **WebFTP** öffnen, im Webspace einen Ordner **`fahrtenbuch`** anlegen (klein geschrieben!) und `installieren.php` hineinladen.
3. https://va-strasswalchen.at/fahrtenbuch/installieren.php öffnen.
4. Formular ausfüllen:
   - **Datenbank:** die Daten aus dem World4You-Kundenbereich unter „Datenbanken“. Es darf dieselbe Datenbank wie beim Notizbuch sein (Tabellen beginnen mit `fb_`).
   - **Admin-Zugang:** Benutzername `christian mayerhofer` (wie in der alten App), eigenes Passwort.
5. „Zum Fahrtenbuch und anmelden“.
6. **Admin → Daten aus der alten Streamlit-App übernehmen:** `SUPABASE_URL` und `SUPABASE_KEY` aus den Streamlit-Secrets eintragen, Knopf zweimal tippen. Alle Benutzer, Fahrzeuge (IDs 69/70/71), Fahrten, Orte, Distanzen, HU-Einträge und Startwerte werden übernommen. Alle können sich mit ihrem bisherigen Passwort anmelden.
7. **Admin → E-Mail-Versand** einrichten (Microsoft 365 wie beim Notizbuch), Test-Mail senden.
8. Kontrolle, dann Streamlit-App abschalten und Supabase pausieren/löschen.

## Update einspielen
Neue `installieren.php` per WebFTP in den Ordner `fahrtenbuch` laden und im Browser öffnen → „aktualisiert“. Daten und Zugangsdaten bleiben. Die Datei löscht sich selbst.

## Sicherheitstest
https://va-strasswalchen.at/fahrtenbuch/server/config.php muss eine leere Seite oder „403 Forbidden“ zeigen.

## Falsche Kilometer finden und reparieren
1. **Stammdaten → Sicherung herunterladen.**
2. **Fahrzeuge & Orte → „Distanzen online berechnen“** – sucht alle Orte aus Orte-Liste, Keywords, HU und gespeicherten Fahrten.
3. **Orte-Check** (gleicher Tab): Rote Zeilen oben, darunter steht der Grund.
   - **Tippfehler** (z. B. „Seekrichen“): richtigen Namen ins Feld (oft schon vorgeschlagen) → **„Umbenennen“** – ändert den Namen überall (Keywords aller Jahre, Orte, HU, gespeicherte Fahrten).
   - **Falscher Ort gefunden** (z. B. Neumarkt in der Steiermark): genaueren Suchbegriff („Neumarkt am Wallersee“) → **„Neu suchen“**.
   - „Kartendienst hat nicht geantwortet“: später nochmal.
4. **Prüfung → Gesamt-Abgleich starten** (pro Jahr): listet alle Fahrten, deren km nicht zu ihren Orten passen.
5. **„… Fahrt(en) automatisch korrigieren“**: setzt die km richtig, baut die Kilometerkette neu und richtet die HU wieder genau auf den HU-Stand aus.
