"""Propojení s MicroStationem: seznam chyb vedle výkresu pro makro KontrolaVykresu.bas.

Makro v MicroStationu seznam jen čte a chyby ukáže jako dočasné kroužky (do DGN se neukládají),
takže výkres zůstává studentův – opravuje se ručně.

Formát souboru ``<název výkresu>_chyby.txt`` (ANSI / cp1250 kvůli VBA, oddělovač tabulátor)::

    # komentář
    číslo<TAB>x<TAB>y<TAB>závažnost<TAB>text
"""

from __future__ import annotations

from pathlib import Path

from .checks.base import Issue, Severity
from .resources import resource_path

MACRO_NAME = "KontrolaVykresu.bas"


def errors_file_for(drawing_path: str | Path) -> Path:
    p = Path(drawing_path)
    return p.with_name(p.stem + "_chyby.txt")


def write_errors(drawing_path: str | Path, issues: list[Issue]) -> Path:
    from .opravny_postup import poradi
    todo = poradi([i for i in issues if i.state == "nová" and i.severity != Severity.INFO])
    lines = [f"# Kontrola výkresu – {len(todo)} míst k opravě, pořadí podle polohy",
             "# číslo\tx\ty\tzávažnost\ttext"]
    for i in todo:
        msg = " ".join((i.message or "").split()).replace("\t", " ")
        lines.append(f"{i.number}\t{i.x:.3f}\t{i.y:.3f}\t{i.severity.value}\t{msg}")
    out = errors_file_for(drawing_path)
    out.write_bytes(("\r\n".join(lines) + "\r\n").encode("cp1250", errors="replace"))
    return out


def install_macro(dest_dir: str | Path) -> Path:
    """Uloží makro pro MicroStation (ANSI + CRLF, jak ho čeká import ve VBA editoru)."""
    src = resource_path("microstation", MACRO_NAME).read_text(encoding="utf-8")
    out = Path(dest_dir) / MACRO_NAME
    out.write_bytes(src.replace("\r\n", "\n").replace("\n", "\r\n").encode("cp1250", errors="replace"))
    return out


NAVOD = """<h3>Chyby přímo v MicroStationu</h3>
<p>Aplikace po každé kontrole uloží vedle výkresu soubor <b>&lt;název&gt;_chyby.txt</b>. Makro v MicroStationu
ho načte a ukáže chyby jako <b>dočasné kroužky</b> – do DGN se neukládají a výkres nijak nemění. Klávesou
pak skáčete z chyby na chybu.</p>
<p><b>Důležité:</b> DXF ukládejte vedle DGN se <b>stejným názvem</b> (Vykres.dgn → Vykres.dxf), aby makro
seznam našlo.</p>
<h4>Jednou – instalace makra</h4>
<ol>
<li>Tlačítkem níže uložte makro <b>KontrolaVykresu.bas</b> (třeba do Dokumentů).</li>
<li>V MicroStationu: <b>Nástroje → Makro → Správce projektů</b> (Utilities → Macro → Project Manager),
tlačítko <b>Nový</b> (New) – projekt např. „KontrolaVykresu“, a <b>Načíst</b> (Load).</li>
<li>Tlačítko <b>Visual Basic Editor</b> → nabídka <b>File → Import File…</b> → vyberte KontrolaVykresu.bas →
<b>File → Save</b>.</li>
<li>Funkční klávesy: <b>Pracovní prostředí → Funkční klávesy</b> (Workspace → Function Keys) – F8:
<code>vba run KV_Dalsi</code>, F7: <code>vba run KV_Predchozi</code>, F6: <code>vba run KV_Nacist</code>.</li>
</ol>
<h4>Při práci</h4>
<ol>
<li>V aplikaci zapněte <b>Kontrola → Posílat chyby do MicroStationu</b> a <b>Hlídat změny výkresu</b>.</li>
<li>V MicroStationu uložte DXF (Uložit jako → DXF) – aplikace výkres sama zkontroluje a zapíše chyby.</li>
<li>V MicroStationu <b>F6</b> (načíst chyby, ukáže kroužky), <b>F8</b> další chyba, <b>F7</b> předchozí.
Text chyby je ve stavovém řádku; <code>vba run KV_Znovu</code> ho ukáže v okně, <code>vba run KV_Skryt</code>
kroužky schová.</li>
</ol>
<p style='color:#6B7280'>Makro je napsané pro MicroStation V8i i CONNECT (VBA). Kdyby něco nešlo, pošlete
text chyby z VBA – upravím ho.</p>
"""
