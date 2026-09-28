# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: sestavení jednoho souboru KontrolaVykresu.exe
# Spuštění:  pyinstaller --noconfirm kontrola_vykresu.spec   (nebo sestavit_exe.bat)

from PyInstaller.utils.hooks import collect_data_files

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
    hiddenimports=["kontrola.checks.topology", "kontrola.checks.attributes", "pdfplumber", "pypdfium2",
                   "openpyxl", "xlrd", "PySide6.QtSvg", "reportlab.graphics.barcode"],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="KontrolaVykresu",
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    icon="kontrola/resources/ikona.ico",
)
