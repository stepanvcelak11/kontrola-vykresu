# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: sestavení programu KontrolaVykresu
# Spuštění:  pyinstaller --noconfirm kontrola_vykresu.spec   (nebo sestavit_exe.bat)
#
# Výchozí je SLOŽKA dist/KontrolaVykresu/ (z ní se dělá instalátor instalace.iss). Program se nerozbaluje
# při každém spuštění do %TEMP%, takže startuje rychle a Windows Defender / SmartScreen ho nepovažuje
# za podezřelý. KV_JEDEN_SOUBOR=1 sestaví přenosný jeden soubor dist/KontrolaVykresu.exe (bez instalace).

import os
import re

from PyInstaller.utils.hooks import collect_data_files

JEDEN_SOUBOR = os.environ.get("KV_JEDEN_SOUBOR") == "1"

datas = [
    ("kontrola/resources", "kontrola/resources"),
    ("ukazky/ukazkovy_vykres.dxf", "ukazky"),
    ("ukazky/vzorovy_vykres.dxf", "ukazky"),
    ("ukazky/tabulka_atributu.xlsx", "ukazky"),
    ("ukazky/tabulka_atributu.csv", "ukazky"),
    ("ukazky/konfigurace.yaml", "ukazky"),
    ("ukazky/nacrt.png", "ukazky"),
    ("ukazky/vzor_ucitele.pdf", "ukazky"),
]
datas += collect_data_files("ezdxf")
datas += collect_data_files("pypdfium2")
datas += collect_data_files("pypdfium2_raw")

excludes = [
    "tkinter", "matplotlib", "IPython", "pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick", "PySide6.QtQml",
    "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtPdf", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSensors",
]

a = Analysis(
    ["spustit.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=["qrcode", "kontrola.checks.topology", "kontrola.checks.attributes", "pdfplumber", "pypdfium2",
                   "openpyxl", "xlrd", "olefile", "PySide6.QtSvg", "reportlab.graphics.barcode"],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

# Údaje o programu ve vlastnostech .exe (Windows i antiviry je u neznámého programu čtou)
VERZE = re.search(r'__version__ = "([^"]+)"', open("kontrola/__init__.py", encoding="utf-8").read()).group(1)
cisla = tuple(int(x) for x in (VERZE.split(".") + ["0"] * 4)[:4])
try:
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                     VarFileInfo, VarStruct, VSVersionInfo)
    udaje = VSVersionInfo(
        ffi=FixedFileInfo(filevers=cisla, prodvers=cisla),
        kids=[StringFileInfo([StringTable("040504b0", [
            StringStruct("CompanyName", "Kontrola výkresu"),
            StringStruct("FileDescription", "Kontrola výkresu"),
            StringStruct("FileVersion", VERZE),
            StringStruct("InternalName", "KontrolaVykresu"),
            StringStruct("LegalCopyright", "github.com/stepanvcelak11/kontrola-vykresu"),
            StringStruct("OriginalFilename", "KontrolaVykresu.exe"),
            StringStruct("ProductName", "Kontrola výkresu"),
            StringStruct("ProductVersion", VERZE)])]),
              VarFileInfo([VarStruct("Translation", [0x0405, 1200])])])
except ImportError:  # pragma: no cover
    udaje = None

spolecne = dict(name="KontrolaVykresu", debug=False, strip=False, upx=False, console=False,
                icon="kontrola/resources/ikona.ico", version=udaje)

if JEDEN_SOUBOR:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], runtime_tmpdir=None, **spolecne)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **spolecne)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="KontrolaVykresu")
