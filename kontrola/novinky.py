"""Novinky – co přibylo v nových verzích. Po aktualizaci se okno „Co je nového“ ukáže jednou.

Nejnovější skupina je první; ``id`` stačí zvýšit, aby se okno ukázalo znovu.
"""

from __future__ import annotations

KEY = "novinky/videno"

NOVINKY: list[tuple[int, str, list[str]]] = [
    (3, "1. října 2026 – odpoledne", [
        "<b>Nové kontroly:</b> prvek na výchozí vrstvě Default / 0 a prvky na vypnuté nebo zmrazené vrstvě, "
        "které v MicroStationu nevidíte.",
        "<b>Připraveno k odevzdání</b> hlídá název souboru podle zadání (Prijmeni_cz_ax_tx.dgn) a poradí název "
        "pro další opravu.",
        "<b>⧉ Hned vedle jsou další chyby</b> – u chyby se ukážou chyby na stejném místě nebo prvku; často "
        "mají jednu příčinu.",
        "<b>Zpět (Ctrl+Z)</b> vrátí omylem kliknuté Opraveno / Ignorovat.",
        "<b>Velikost písma</b> celé aplikace v Nabídka → Zobrazení.",
        "<b>Hromadně ignorovat</b> všechny chyby jednoho typu nebo vrstvy (pravé tlačítko na chybě).",
        "<b>Seznam k opravě na tisk</b> (Ctrl+P) má u každé skupiny chyb obrázek „chyba / správně“.",
    ]),
    (2, "1. října 2026 – dopoledne", [
        "<b>Okno „Další chyba“</b> (Ctrl+Shift+N) – malé okénko nad MicroStationem s postupem a key-inem.",
        "<b>Režim soustředění</b> (F11) – jen výkres a jedna chyba velkým písmem.",
        "<b>Tepelná mapa chyb</b> (Ctrl+Shift+H) – kde je chyb nejvíc.",
        "<b>Barva vzhledu</b> – modrá, zelená, fialová nebo oranžová.",
        "<b>Upozornění Windows</b> po uložení výkresu, <b>osobní tahák</b> nejčastějších chyb na úvodní "
        "stránce a obrázek „jak to má vypadat“ u chyby.",
        "<b>Aktualizace jedním klikem</b> a úvodní okénko při spuštění.",
    ]),
]


def latest_id() -> int:
    return max(n[0] for n in NOVINKY)


def unseen(settings) -> list[tuple[int, str, list[str]]]:
    """Novinky, které uživatel ještě neviděl (prázdné při úplně prvním spuštění – tam je průvodce)."""
    seen = settings.value(KEY, None)
    if seen is None:
        if not settings.contains("okno/geometrie"):
            return []  # nový uživatel: novinky nejsou „nové“, ukáže se průvodce
        seen = 0  # aplikaci už používal před zavedením novinek
    try:
        seen = int(seen)
    except (TypeError, ValueError):
        seen = 0
    return [n for n in NOVINKY if n[0] > seen]


def mark_seen(settings) -> None:
    settings.setValue(KEY, latest_id())


def html(items: list[tuple[int, str, list[str]]]) -> str:
    out = []
    for _id, title, points in items:
        out.append(f"<h3 style='margin:10px 0 4px 0'>{title}</h3><ul style='margin-top:0'>"
                   + "".join(f"<li style='margin-bottom:4px'>{p}</li>" for p in points) + "</ul>")
    return "".join(out)
