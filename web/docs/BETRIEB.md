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
