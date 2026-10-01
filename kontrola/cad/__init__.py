"""CAD pro 2D kresbu v DXF (vlastní implementace; DXF čte, zapisuje a používá ho jako jediný formát).

Zdrojem pravdy je DXF dokument knihovny ezdxf (MIT) – neznámé entity a skupinové kódy zůstávají beze
změny a při uložení se vrátí zpět. Zobrazení přes ezdxf drawing add-on (MIT) do Qt (PySide6, LGPL).
"""
