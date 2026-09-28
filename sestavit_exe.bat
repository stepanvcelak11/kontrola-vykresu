@echo off
rem Sestavení KontrolaVykresu.exe (jeden soubor) pomocí PyInstalleru.
rem Předpoklad: nainstalovaný Python 3.11+ (python.org, při instalaci zaškrtnout "Add to PATH").
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist .venv (
    echo [1/4] Vytvářím virtuální prostředí .venv ...
    python -m venv .venv || goto :chyba
)
call .venv\Scripts\activate.bat || goto :chyba

echo [2/4] Instaluji knihovny ...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements-dev.txt || goto :chyba

echo [3/4] Spouštím testy ...
python -m pytest -q tests || goto :chyba

echo [4/4] Sestavuji .exe ...
pyinstaller --noconfirm --clean kontrola_vykresu.spec || goto :chyba

echo.
echo Hotovo: dist\KontrolaVykresu.exe
goto :eof

:chyba
echo.
echo Sestavení selhalo – viz výpis výše.
exit /b 1
