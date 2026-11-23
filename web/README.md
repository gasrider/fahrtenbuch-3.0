# Fahrtenbuch 3.0 – PHP-Version für World4You

Ersetzt die Streamlit-App. PHP + MySQL, Oberfläche ohne Build-Schritt, Auslieferung als eine Datei `dist/installieren.php`.

- Betrieb / Installation: [docs/BETRIEB.md](docs/BETRIEB.md)
- Projektkontext für Entwickler/KI: [CLAUDE.md](CLAUDE.md)

```bash
python3 build/make_installer.py   # -> dist/installieren.php
python3 tests/e2e.py              # Installation + alle Funktionen (php, MariaDB)
```
