# Betrieb (für den Admin)

**Adresse:** https://va-strasswalchen.at/fahrtenbuch/ · **Hosting:** World4You „Webhosting Grow“ (dasselbe Paket wie das Notizbuch)

## Erste Installation
1. World4You-Kundenbereich → **Datenbanken**: neue MySQL-Datenbank anlegen (oder die vom Notizbuch verwenden – die Tabellen heißen hier `fb_…`).
   Server, Datenbankname, Benutzer und Passwort notieren.
2. **WebFTP** öffnen → im selben Ordner, in dem `notizen` liegt, einen Ordner **`fahrtenbuch`** (klein geschrieben) anlegen.
3. Die Datei **`installieren.php`** in den Ordner `fahrtenbuch` hochladen.
4. Im Browser **https://va-strasswalchen.at/fahrtenbuch/installieren.php** öffnen und das Formular ausfüllen
   (Datenbank-Angaben, eigener Benutzername + neues Passwort). Die Datei löscht sich danach selbst.
5. In der App anmelden → **Admin → Umzug von Supabase**: den `service_role`-Schlüssel aus Supabase
   (Project Settings → API) eintragen → „Daten aus Supabase übernehmen“ (zweimal tippen). Supabase muss dafür noch laufen.
6. Kontrolle: Fahrzeuge (Nr. 69/70/71 mit gleichen IDs), Jahre, ein Monats-PDF mit der alten App vergleichen.
7. **Admin → E-Mail-Versand** einrichten (für „Passwort vergessen“) und den Einladungs-Code setzen.
8. Erst wenn alles passt: alte Streamlit-App und Supabase abschalten (Keep-Alive auf GitHub dann deaktivieren).

## Update einspielen
Neue `installieren.php` per WebFTP in `fahrtenbuch` hochladen und https://va-strasswalchen.at/fahrtenbuch/installieren.php öffnen.
Daten, Zugänge und Datenbank-Zugang bleiben unverändert. Die Datei löscht sich selbst.

## Sicherheitstest
https://va-strasswalchen.at/fahrtenbuch/server/config.php muss „403 Forbidden“ zeigen.
