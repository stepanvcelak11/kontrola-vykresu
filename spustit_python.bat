@echo off
rem Spusteni Kontroly vykresu pres Python (bez .exe) - vhodne pri zapnutem Inteligentnim rizeni aplikaci.
rem Okno zustane otevrene, kdyz se neco nepovede - vypis poslete autorovi.
cd /d "%~dp0"
if not exist "spustit.py" (
  echo Soubor spoustite primo ze ZIPu. Nejdriv ZIP rozbalte: prave tlacitko - Extrahovat vse.
  pause
  exit /b 1
)
python -c "import sys" >nul 2>nul
if errorlevel 1 (
  echo Python neni nainstalovany. Nainstalujte "Python 3.12" z Microsoft Store a spustte znovu.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\pythonw.exe" (
  echo Prvni spusteni: pripravuji prostredi, trva to par minut...
  python -m venv .venv
  if errorlevel 1 (
    echo Nepodarilo se pripravit prostredi Pythonu.
    pause
    exit /b 1
  )
)
echo Kontroluji knihovny (poprve to trva nekolik minut)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt > pip_log.txt 2>&1
if errorlevel 1 echo Instalace knihoven hlasila chybu - podrobnosti v pip_log.txt.
".venv\Scripts\python.exe" -X utf8 -m kontrola.kontrola_startu
if errorlevel 1 (
  echo.
  echo Vypis vyse (a soubor pip_log.txt) poslete autorovi aplikace.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" spustit.py
