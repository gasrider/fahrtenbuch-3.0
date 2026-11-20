#!/usr/bin/env python3
"""Baut dist/installieren.php: eine einzelne PHP-Datei, die alle App-Dateien (base64) enthält.

Hochgeladen in den Ordner "fahrtenbuch" und im Browser geöffnet:
- erste Installation: Formular (DB-Zugang, Admin) -> schreibt Dateien + server/config.php, legt Tabellen an
- bestehende Installation: ersetzt nur die App-Dateien (server/config.php bleibt), ergänzt Tabellen, löscht sich selbst
"""
import base64, datetime, pathlib, subprocess
ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "app"
OUT = ROOT / "dist" / "installieren.php"
SKIP = {"server/config.php"}  # wird vom Installer erzeugt, nie überschrieben

entries = []
for p in sorted(APP.rglob("*")):
    if not p.is_file():
        continue
    rel = p.relative_to(APP).as_posix()
    if rel in SKIP:
        continue
    entries.append(f"  {rel!r} => '{base64.b64encode(p.read_bytes()).decode()}'")

try:
    rev = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
except Exception:
    rev = "lokal"
version = datetime.date.today().isoformat() + " (" + rev + ")"
tpl = (ROOT / "build" / "installer_template.php").read_text()
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(tpl.replace("/*__FILES__*/", ",\n".join(entries)).replace("/*__VERSION__*/", version))
print(f"{len(entries)} Dateien -> {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB), Version {version}")
