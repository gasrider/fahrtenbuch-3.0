# Windows (PowerShell):
"logic","database","services","pdf","ui" | ForEach-Object { "" | Out-File "$_\__init__.py" }

# Linux/Mac:
touch logic/__init__.py database/__init__.py services/__init__.py pdf/__init__.py ui/__init__.py