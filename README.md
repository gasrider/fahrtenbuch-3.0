Fahrtenbuch Generator v7.0 (Multi-User)

Fahrtenbuch-App mit Login, Fahrzeugverwaltung, Monatserfassung,Plausibilitätsprüfung und PDF-Export (Monat/Jahr). Daten liegen in Supabase.



Starten (ohne Terminal!)

Doppelklick auf Start\_Fahrtenbuch.bat – der Browser öffnet die Appautomatisch unter http://localhost:8501.Beim allerersten Start werden Pakete installiert (dauert 1–2 Minuten).



Beenden: Browser-Tab schließen + im schwarzen Fenster "Strg+C" drückenoder Fenster schließen.



Einmalige Einrichtung

Python installieren (python.org, Häkchen "Add Python to PATH" setzen)

Datei .env anlegen mit folgendem Inhalt:SUPABASE\_URL=https://xxxxx.supabase.coSUPABASE\_KEY=dein-key

Tests

Optional: Doppelklick auf Test ausführen.bat (prüft die Berechnungslogik)



Benötigte Supabase-Tabellen

users(username, password, email, force\_pw\_change)

settings(username, name, pnr, wohnort, dienstort, entfernung,taggeld\_min\_stunden, taggeld\_basis, taggeld\_stufung,taggeld\_max\_betrag, taggeld\_max\_stunden, km\_geld)

fahrzeuge(id, username, bezeichnung, kennzeichen, start\_km\_vorjahr,privat\_km\_min, privat\_km\_max, dienstlich\_quote)

zeitraeume(id, username, fahrzeug\_id, von, bis)

fahrten(id, username, jahr, monat, datum, fahrzeug\_id, fahrzeug, route,km\_d, km\_p, abf, ank, dauer, abfahrt\_km)

hu\_corrections(id, username, fahrzeug\_id, datum, km\_at\_hu, werkstattort,stopps\_vor\_hu, stopps\_nach\_hu)

system\_config(id, smtp\_server, smtp\_port, smtp\_user, smtp\_password,smtp\_from\_name)

Projektstruktur (wo finde ich was?)

config.py .............. Supabase-Verbindung

database/ .............. Alle Datenbank-Zugriffe (Laden/Speichern)

logic/ ................. Berechnungen (Taggeld, Feiertage, Prüfung)

services/email.py ...... Passwort-Reset-Mail

pdf/ ................... PDF-Erzeugung

ui/ .................... Bildschirmseiten (Login, Tabs)

tests/ ................. Automatische Tests

Wichtige Hinweise

Passwort-Reset benötigt SMTP-Einstellungen (Tabelle system\_config,Zeile id=1) oder Umgebungsvariablen.

Die "Arbeitstage-Vorlage" ist nur ein Starting Point – Zeiten/KM müssenvor dem Speichern mit den realen Fahrten abgeglichen werden.

Die automatische KM-Verteilung aus der alten Version wurde entfernt.

