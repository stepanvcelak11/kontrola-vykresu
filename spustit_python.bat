@echo off
rem Spusteni Kontroly vykresu pres Python (bez .exe) - vhodne pri zapnutem Inteligentnim rizeni aplikaci.
rem Okno zustane otevrene, kdyz se neco nepovede - vypis poslete autorovi.
setlocal enabledelayedexpansion
cd /d "%~dp0"
if not exist "spustit.py" (
  echo Soubor spoustite primo ze ZIPu. Nejdriv ZIP rozbalte: prave tlacitko - Extrahovat vse.
  pause
  exit /b 1
)
if exist ".venv\Scripts\pythonw.exe" goto knihovny

rem --- najit Python: spoustec py, python v PATH, bezne instalacni slozky, Microsoft Store ---
set "PY="
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY (
  python -c "import sys" >nul 2>nul && set "PY=python"
)
if not defined PY (
  for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*" "%ProgramFiles(x86)%\Python3*" "C:\Python3*") do (
    if not defined PY if exist "%%~D\python.exe" set "PY="%%~D\python.exe""
  )
)
if not defined PY (
  for %%V in (3.14 3.13 3.12 3.11 3.10) do (
    if not defined PY if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\python%%V.exe" (
      "%LOCALAPPDATA%\Microsoft\WindowsApps\python%%V.exe" -c "import sys" >nul 2>nul && set "PY="%LOCALAPPDATA%\Microsoft\WindowsApps\python%%V.exe""
    )
  )
)
if not defined PY (
  echo Python se nepodarilo najit.
  echo Nainstalujte "Python 3.12" z Microsoft Store, nebo z python.org se zaskrtnutym "Add python.exe to PATH".
  echo Kdyz uz ho mate: Start - napiste "Aliasy spousteni aplikaci" - zapnete "python.exe" a "python3.exe".
  pause
  exit /b 1
)
echo Pouzivam Python: !PY!
!PY! --version
echo Prvni spusteni: pripravuji prostredi, trva to par minut...
!PY! -m venv .venv
if errorlevel 1 (
  echo Nepodarilo se pripravit prostredi Pythonu.
  pause
  exit /b 1
)

:knihovny
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
