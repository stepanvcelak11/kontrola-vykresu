@echo off
rem Spusteni Kontroly vykresu pres Python (bez .exe) - vhodne pri zapnutem Inteligentnim rizeni aplikaci.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Prvni spusteni: pripravuji prostredi, trva to par minut...
  python -m venv .venv
  if errorlevel 1 (
    echo Python neni nainstalovany. Nainstalujte "Python 3.12" z Microsoft Store a spustte znovu.
    pause
    exit /b 1
  )
)
echo Kontroluji knihovny...
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 echo Knihovny se nepodarilo aktualizovat (bez internetu?) - spoustim s tim, co je nainstalovane.
start "" ".venv\Scripts\pythonw.exe" spustit.py
