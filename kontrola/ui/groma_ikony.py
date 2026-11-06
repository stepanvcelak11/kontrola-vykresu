"""Jednoduché ikony nástrojů pásu Výpočtů (jako obrázky u nástrojů Gromy) a barvy skupin.

Ikona = čárová kresba 24×24 v barvě své skupiny, takže se skupiny pásu dají rozlišit na první pohled."""

from __future__ import annotations

from PySide6.QtGui import QColor, QIcon

# barva skupiny pásu (světlý vzhled; v tmavém se zesvětlí)
BARVY_SKUPIN = {
    "Soubor": "#2563EB", "Import": "#2563EB", "Editace": "#475569", "Seznam": "#0D9488", "Kódování": "#EA580C",
    "Nastavení": "#64748B", "Pohledy": "#7C3AED", "Protokol": "#B45309", "Měření": "#CA8A04",
    "Podrobné": "#2563EB", "Protínání": "#7C3AED", "Průsečíky": "#DB2777", "Oměrné": "#EA580C",
    "Bodové pole": "#059669", "Vyrovnání": "#0F766E", "Výšky": "#0891B2", "Vytyčovací prvky": "#DC2626", "Speciální": "#4F46E5",
    "Další": "#64748B",
}

_B = '<circle cx="{x}" cy="{y}" r="1.7" fill="currentColor"/>'


def _bod(x, y):
    return _B.format(x=x, y=y)


IKONY = {
    # Soubor
    "Import souřadnic…": '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 20h16"/>',
    "Export souřadnic…": '<path d="M12 15V3"/><path d="M7 8l5-5 5 5"/><path d="M4 20h16"/>',
    "Načíst z QTrig…": '<rect x="7" y="2.5" width="10" height="19" rx="2"/><path d="M11 18h2"/>',
    "Trimble (File and Report)…": '<rect x="8" y="4" width="8" height="8" rx="1.5"/><path d="M12 12v3"/>'
                                  '<path d="M7 21l5-6 5 6"/><circle cx="12" cy="8" r="1.4"/>',
    "Krok zpět": '<path d="M4 11a8 8 0 1 1 2.3 5.7"/><path d="M4 5v6h6"/>',
    "Krok vpřed": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>',
    "Odstranit": '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>',
    "Přidej bod…": '<circle cx="9" cy="12" r="3.2"/><path d="M18 8v8M14 12h8"/>',
    "Hromadné změny…": '<path d="M4 6h16M4 12h16M4 18h10"/><path d="M17 16l2 2 3-4"/>',
    "Porovnání souřadnic…": '<path d="M4 8h14l-3-3"/><path d="M20 16H6l3 3"/>',
    "Identické body…": '<circle cx="9" cy="12" r="4.5"/><circle cx="15" cy="12" r="4.5"/>',
    "Kresba z kódů…": '<path d="M4 19l5-11 4 7 7-11"/>' + _bod(4, 19) + _bod(9, 8) + _bod(13, 15) + _bod(20, 4),
    "Kódovací tabulka…": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v16"/>',
    "Nastavení…": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/>'
                  '<circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    "Výchozí rozvržení": '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M14 4v16M3 13h11"/>',
    "Okna / záložky": '<path d="M3 8h6V5h6v3h6v12H3z"/><path d="M3 8v12"/>',
    "Mozaika horizontálně": '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M3 12h18"/>',
    "Mozaika vertikálně": '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M12 4v16"/>',
    "Kaskáda": '<rect x="3" y="3" width="12" height="10" rx="1"/><rect x="9" y="11" width="12" height="10" rx="1"/>',
    "Okna": '<rect x="3" y="7" width="13" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v9a2 2 0 '
            '0 1-2 2h-3"/>',
    # Protokol
    "Zobrazit": '<path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4"/><path d="M9 12h7M9 16h7"/>',
    "Uložit do PDF…": '<path d="M14 3H6v18h12V7z"/><path d="M14 3v4h4"/><path d="M12 10v7M9 14l3 3 3-3"/>',
    "Seznam měření": '<path d="M9 6h11M9 12h11M9 18h11"/>' + _bod(4.5, 6) + _bod(4.5, 12) + _bod(4.5, 18),
    "Zpracování zápisníku…": '<path d="M5 3h10l4 4v14H5z"/><path d="M9 14l2 2 4-4"/>',
    # Výpočty
    "Podrobné/Polární": '<path d="M5 19L19 6"/><path d="M5 12a7 7 0 0 1 5 2.2"/>' + _bod(5, 19) + _bod(19, 6),
    "Polární dávkou": '<path d="M6 18L19 5M6 18l14-6M6 18l5-14"/>' + _bod(6, 18),
    "Podrobné/Ortogonální": '<path d="M3 18h18"/><path d="M9 18V7M15 18v-6"/><path d="M9 15h2.5v3"/>'
                            + _bod(9, 7) + _bod(15, 12),
    "Ze směrů": '<path d="M3 20L12 5L21 20"/>' + _bod(3, 20) + _bod(21, 20) + _bod(12, 5),
    "Z úhlů": '<path d="M3 20h18"/><path d="M3 20L12 6L21 20"/><path d="M8 20a5 5 0 0 0-2-4"/>'
              '<path d="M16 20a5 5 0 0 1 2-4"/>',
    "Z délek": '<circle cx="9" cy="14" r="6"/><circle cx="15" cy="14" r="6"/>' + _bod(12, 9.3),
    "Protínání/Zpět": '<path d="M12 17L4 5M12 17V4M12 17l8-12"/>' + _bod(12, 17) + _bod(4, 5) + _bod(12, 4)
                      + _bod(20, 5),
    "Přímka - přímka": '<path d="M4 4l16 16M20 4L4 20"/>' + _bod(12, 12),
    "Bod na přímce": '<path d="M3 18L21 6"/>' + _bod(3, 18) + _bod(21, 6) + '<circle cx="12" cy="12" r="2.6"/>',
    "Kružnice ze 3 bodů": '<circle cx="12" cy="12" r="8"/>' + _bod(12, 4) + _bod(5, 16) + _bod(19, 16),
    "Kontrolní": '<rect x="3" y="8" width="18" height="8" rx="1"/><path d="M7 8v3M11 8v4M15 8v3M19 8v4"/>',
    "Výměra z měr": '<path d="M4 19L12 5L20 19Z"/><path d="M8 19l6-6M12 19l4-4"/>',
    "Volné stanovisko": '<path d="M12 10l3 5H9z"/><path d="M12 12L4 4M12 12L20 4M12 13l8 7"/>' + _bod(4, 4)
                        + _bod(20, 4) + _bod(20, 20),
    "Polygonový pořad": '<path d="M3 18L8 9l6 4 7-8"/>' + _bod(3, 18) + _bod(8, 9) + _bod(14, 13) + _bod(21, 5),
    "Transformace": '<rect x="3" y="11" width="8" height="8"/><path d="M14 3l7 3-3 7-7-3z"/><path d="M8 8l3-3M11 5h-3"/>',
    "Trigonometrická výška": '<path d="M3 20h18"/><path d="M5 20L19 6"/><path d="M19 6v14" stroke-dasharray="2 2"/>'
                             + _bod(19, 6),
    "Výškový pořad": '<path d="M3 21h18"/><rect x="4" y="6" width="3" height="15"/><rect x="17" y="10" width="3" '
                     'height="11"/><path d="M7 13h10"/>',
    "Redukce délky": '<path d="M3 9L21 4"/><path d="M3 17h18"/><path d="M3 9v8M21 4v13" stroke-dasharray="2 2"/>',
    "Směrník a délka": '<path d="M7 21V3"/><path d="M4.5 5.5L7 3l2.5 2.5"/><path d="M7 15l12-8"/>' + _bod(7, 15)
                       + _bod(19, 7),
    "Úhel": '<path d="M4 19h16"/><path d="M4 19L15 6"/><path d="M11 19a7 7 0 0 0-2.2-5.1"/>',
    "Výměry": '<path d="M4 7l8-3 8 4-2 12H6z"/><path d="M9 12h6M9 15h4"/>',
    "Kubatury": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12L4 7.5M12 12v9"/>',
    "Vytyčovací prvky/Polární": '<path d="M12 3v14"/><path d="M8.5 17h7L12 21z"/><path d="M12 5l6 2.2-6 2.2"/>',
    "Vytyčovací prvky/Ortogonální": '<path d="M3 19h18"/><path d="M12 19V8"/><path d="M12 8l5 2-5 2"/>'
                                    '<path d="M12 16h2.5v3"/>',
    "Rozložení oblouku": '<path d="M4 18a10 10 0 0 1 16 0"/>' + _bod(4, 18) + _bod(12, 10) + _bod(20, 18),
    "Centrace": '<circle cx="12" cy="12" r="7"/><path d="M12 8v8M8 12h8"/>' + _bod(17, 7),
    "Křovák": '<path d="M3 20L21 4"/><path d="M5 9l3-5 3 5"/><path d="M13 20l3-5 3 5"/>' + _bod(12, 12),
    "S-JTSK ↔ WGS84": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/>'
                      '<path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18"/>',
    "Převod úhlů": '<circle cx="12" cy="12" r="8"/><path d="M12 12V4"/><path d="M12 12l6 4"/>',
    "Testování přesnosti": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/>' + _bod(12, 12),
    "Přímka - směr": '<path d="M3 17L21 9"/><path d="M5 4l9 17"/>' + _bod(5, 4) + _bod(11.6, 13.2),
    "Přímka - kružnice": '<circle cx="13" cy="12" r="6.5"/><path d="M2 18L22 8"/>',
    "Na přímku": '<path d="M3 18L21 8"/><path d="M11 5l3.5 8"/>' + _bod(11, 5) + _bod(14.2, 12.7),
    "Na kružnici": '<circle cx="12" cy="13" r="7"/><path d="M12 13l5-9"/>' + _bod(17.5, 3.5),
    "MNČ": '<path d="M3 19L21 6"/>' + _bod(5, 15) + _bod(9, 15.5) + _bod(13, 9) + _bod(17, 10) + _bod(20, 5),
    "Konstrukční": '<path d="M4 20V8h8v5h8v7z"/><path d="M4 5h8M20 10v-0"/>',
    "Výška stanoviska": '<path d="M3 21h18"/><path d="M12 21V9"/><path d="M8 9l4-6 4 6"/><path d="M16 15h4"/>',
    "Výšky dávkou": '<path d="M3 21h18"/><rect x="4" y="12" width="3" height="9"/><rect x="10.5" y="8" width="3" '
                    'height="13"/><rect x="17" y="5" width="3" height="16"/>',
    "Nivelace": '<path d="M3 15l4-4 4 3 4-6 6 5"/><path d="M3 20h18"/>',
    "Trojúhelníková kalkulačka": '<path d="M4 19L12 5L20 19Z"/><path d="M9 15h6"/>',
    "Další výpočty": _bod(5, 12) + _bod(12, 12) + _bod(19, 12),
}


def barva_skupiny(skupina: str) -> str:
    from .theme import is_dark
    c = QColor(BARVY_SKUPIN.get(skupina, "#64748B"))
    return c.lighter(150).name() if is_dark() else c.name()


def ikona(skupina: str, text: str, velikost: int = 36) -> QIcon:
    """Ikona tlačítka pásu: nejdřív „Skupina/Text“ (Polární je v Podrobných i ve Vytyčení), pak „Text“."""
    telo = IKONY.get(f"{skupina}/{text}") or IKONY.get(text)
    if telo is None:
        return QIcon()
    from .theme import svg_ikona
    return svg_ikona(telo, barva_skupiny(skupina), velikost)
