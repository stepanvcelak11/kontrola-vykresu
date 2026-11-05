"""Novinky – co přibylo v nových verzích. Po aktualizaci se okno „Co je nového“ ukáže jednou.

Nejnovější skupina je první; ``id`` stačí zvýšit, aby se okno ukázalo znovu.
"""

from __future__ import annotations

KEY = "novinky/videno"

NOVINKY: list[tuple[int, str, list[str]]] = [
    (9, "6. listopadu 2026", [
        "<b>Styly čar MicroStationu (.rsc)</b>: CAD čte knihovny stylů od učitele (GEO.RSC, UGEO_VP.RSC – ploty, "
        "zdi, hranice, čárkované čáry…) a kreslí je stejně jako MicroStation – zuby plotů, symboly i čárky po "
        "rozteči, i v tisku do PDF. Knihovnu stačí nahrát do Zadání → Podklady, nebo „styly čar připoj“; styl prvku "
        "„styl 2.103“ (stačí číslo značky). Opraveno: příkazy „styl“ a „tloušťka“ z příkazového řádku.",
        "<b>Arch (papír) v CAD</b>: příkaz „arch“ (nebo tlačítko v paletě Zobrazení) položí pod výkres papír "
        "zvolené velikosti (A4–A0 i vlastní rozměr) v měřítku, myší ho posunete kam potřebujete a Tisk do PDF "
        "vytiskne přesně to, co je na papíře. Arch jde i natočit („arch otoč 30“ nebo dvěma body podle "
        "kresby). Arch se uloží do výkresu.",
        "<b>Popis souřadnic</b> v CAD: Y a X bodu s odkazovou čarou (vytyčovací výkresy).",
        "<b>Nastavení výpočtů</b> (Výpočty → Úlohy): účel měření (katastr s kódem kvality / polohopis s třídou "
        "přesnosti), přístroj a jeho přesnost, korekce délek – měřítko Křovákova zobrazení, redukce z nadmořské "
        "výšky, fyzikální korekce – a mezní odchylky polygonových pořadů. Korekce se použijí v rajónu, polygonech, "
        "volném stanovisku a protínání z délek a vypíšou se do protokolu.",
        "<b>Výpočty – nové úlohy</b>: Kružnice ze tří bodů, Úhel ze souřadnic, Bod na přímce (i dělení úsečky). "
        "Polární metoda dávkou (Zápisník) bere korekce délek z Nastavení výpočtů.",
        "<b>Výpočty</b>: Polygonový pořad vetknutý (bez orientací, kontrola délkou) a Centrace směrů "
        "z excentrického stanoviska.",
        "<b>CAD</b>: lomená čára s obloukovými úseky (SmartLine – „o“ = další úsek obloukem) Buňky po prvku "
        "(stromořadí, značky na hranici natočené po směru čáry) a Text podél prvku (názvy ulic a toků, vždy čitelně). Opraveno: Ctrl+V (vložit ze schránky) "
        "a další víceslovné příkazy se spouštěly jako jiný příkaz.",
        "<b>Polygonový pořad</b>: protokol po bodech – úhel, oprava, směrník, délka, ΔY, ΔX a jejich opravy. "
        "Nová úloha <b>Převod úhlů</b> (gony, stupně, ° ′ ″, radiány).",
        "<b>Export seznamu do Leica GSI</b> (81 = Y, 82 = X, 83 = výška) – body pro vytyčení rovnou do přístroje; "
        "takový GSI jde i načíst zpět jako seznam souřadnic.",
        "<b>Trigonometrická výška oboustranně</b> (průměr tam a zpět bez vlivu zakřivení a refrakce). CAD: "
        "<b>Čára pod úhlem</b> k prvku (úhel ve stupních nebo „50g“ v gonech).",
        "<b>Polygonový pořad jednostranně orientovaný</b> (připojený na obou koncích, orientace jen na začátku). "
        "CAD: <b>Zarovnat prvky</b> podle hrany vzorového prvku (legendy, tabulky textů).",
        "<b>Volné stanovisko MNČ</b>: vyrovnání směrů a délek s váhami podle přístroje (střední chyby, opravy "
        "v cc a mm, σ0); jde i jen ze směrů na 3 a více bodů. Nastavení výpočtů: zaokrouhlení souřadnic nových bodů.",
        "<b>Prostorová polární metoda</b>: rajón i volné stanovisko berou šikmou délku se zenitem a výškou "
        "přístroje / cíle – výška bodu i stanoviska (zakřivení a refrakce). Nová úloha Výměra z měr (Heron).",
        "<b>Nivelační zápisník</b>: technická nivelace ze středu – čtení vzad, vpřed a boční záměry po sestavách, "
        "kontrola zápisníku, uzávěr s mezní odchylkou a výšky přestavových i bočních bodů rovnou do seznamu (Z).",
        "<b>Vzorek plochy v CAD</b> (Pattern Area): uzavřenou plochu vyplní buňkami v mřížce, do sponu, "
        "s natočením řad a odsazením od hranice – značky louky, zahrady, lesa jako v MicroStationu. Jedno Zpět.",
        "<b>Písmo textů v CAD</b>: v okně Text vyberete písmo (styly výkresu i všechna písma v počítači), šířku "
        "a jedno z devíti zarovnání jako v MicroStationu (LT … RB). Příkaz „písmo Arial“ změní písmo nových i "
        "vybraných textů.",
        "<b>CAD → Kontrola živě</b>: co nakreslíte v CAD, se po přepnutí na Výkres samo zkontroluje – bez "
        "ukládání a nahrávání. A obráceně: pravým tlačítkem na chybě „Opravit v CAD“ vybere v CAD prvky chyby "
        "a přiblíží je; po opravě stačí přepnout zpět na Výkres.",
    ]),
    (8, "5. listopadu 2026", [
        "<b>Kokeš</b> – nová stránka v levé liště: seznam souřadnic s čísly bodů KN (k.ú., ZPMZ, pořadové číslo, "
        "zobrazení 13-1) a kódy kvality, kreslící klíče ze Směrnice (dvojklik = kreslit klíčem v CAD), tabulky "
        "pro Kokeš podle zadání (barvy s RGB, čáry, textové klíče 1xx, fonty), katastr a GP.",
        "<b>CAD ukládá a otevírá DGN</b> pro MicroStation (V7 – hladiny, barvy, tloušťky, styly a buňky v číslech "
        "Směrnice) a otevře i DGN V8. Kontrola čte DGN V7 bez převodníku.",
        "<b>CAD</b>: Kolmice z bodu na prvek, Osa úhlu, Uložené pohledy („pohled ulož …“).",
        "<b>Výpočty</b>: Protínání vpřed ze směrů (orientace vážené délkami, jako v Gromě).",
    ]),
    (7, "4. listopadu 2026", [
        "<b>Kódování v QTrig → výkres</b>: při měření dáváte bodům kódy (v QTrig tlačítka Začátek / Konec / "
        "Uzavřít linie a kódovník z kanceláře), body se stáhnou rovnou do výkresu v CAD a z kódů se nakreslí "
        "značky, linie a plochy – i průběžně při hlídání zakázky. Špatné spojení opravíte běžným kreslením, "
        "ručně upravená linie se už nepřepíše.",
        "<b>CAD rychleji</b>: vlastní klávesové zkratky (tlačítko Zkratky…, F2 úsečka, F4 polylinie, Ctrl+1…9 "
        "druh prvku), vlastní zkratky příkazového řádku, historie řádku šipkami, mezerník = naposledy použité "
        "příkazy, <b>Nahradit buňku</b> a <b>Kopie textu se zvýšením čísla</b>.",
        "<b>Kontrola</b> hlásí špatnou buňku na hladině, tloušťku i u čáry s neuloženým stylem a bez přiloženého "
        "seznamu porovná výkres s body z Výpočtů (i z QTrig). Ověřeno mutačními testy na výkresech od učitele.",
        "<b>Kokeš</b>: v Zadání → Pravidla „Výkres kreslen v: Kokeš“ – kreslící klíče ze sloupce KK Směrnice, "
        "barva 100 = 0, styl −13 = 4, texty klíčem 1xx; soubory .vyk/.ss poradí, jak je exportovat.",
        "<b>Výpočty → Úlohy</b>: Redukce délky do S-JTSK (vodorovná, nulový horizont, měřítko Křováka v místě).",
    ]),
    (6, "6. října 2026", [
        "<b>Instalace</b> místo jednoho .exe: Windows program při spuštění neblokuje, startuje rychleji a "
        "aktualizace proběhne sama (Nápověda → Zkontrolovat aktualizace).",
        "<b>Levá lišta</b>: Otevřít výkres je dole u Nastavení (už se neplete s Kontrolou), šipka vedle "
        "nabídne naposledy otevřené výkresy.",
        "<b>CAD</b> se při zavření zeptá na neuložený výkres, každou 1,5 minuty ukládá záložní kopii a po pádu "
        "nabídne výkres obnovit.",
        "<b>Malý notebook</b>: okno se vejde i při zvětšení 125–150 %, řádky tlačítek se zalomí.",
        "<b>Výpočty → Úlohy</b>: hledání úlohy, polygonový pořad <b>uzavřený</b> a <b>volný</b>, "
        "<b>testování přesnosti ÚM</b> (kontrolní body a délky podle ČSN 01 3410 a Pokynu pro tvorbu ÚM).",
        "<b>Technická zpráva</b> (Soubor → Export): kostra podle Pokynu, předvyplněná z projektu.",
        "<b>Porovnat s výkresem učitele</b> (Kontrola), <b>náležitosti mapového listu</b> (rám, měřítko, "
        "severka…), lepší <b>duplicity</b>, <b>kurzíva z DGN</b>, oprava atributů v Automatické opravě.",
    ]),
    (5, "1. října 2026 – noc", [
        "<b>CAD</b> (nová stránka v levé liště): DXF výkres na plátně, zoom a posun, souřadnice S-JTSK, "
        "úchyty (koncový bod, střed, průsečík, kolmice, tečna), ortho a polární režim, příkazový řádek "
        "(vzdálenost, souřadnice), uložení DXF beze ztrát a tlačítko Zkontrolovat (propojení s Kontrolou).",
    ]),
    (4, "1. října 2026 – večer", [
        "<b>Výpočty</b> (nová stránka v levé liště): seznam souřadnic jako v Gromě – číslo, Y, X, Z, kód, "
        "kvalita; úpravy přímo v tabulce, hledání, filtr podle kódu, řazení kliknutím na záhlaví.",
        "<b>Import TXT/CSV</b> s náhledem – formát (sloupce, oddělovač, desetinná čárka, záporné nebo "
        "prohozené souřadnice) se rozpozná sám a jde upravit. <b>Export</b> do TXT/CSV.",
        "<b>Hromadné úpravy</b> (kód, kvalita, posun, přečíslování), <b>duplicity</b> s bezpečným "
        "slučováním, <b>Zpět/Znovu</b> (Ctrl+Z / Ctrl+Y) a automatické ukládání do projektu.",
        "<b>Úlohy</b> na stránce Výpočty: rajón, protínání vpřed / z délek / zpět, volné stanovisko, "
        "transformace s opravami, výměra, staničení a kolmice, kontrola dvou určení – protokol a nové body "
        "do seznamu jedním klikem.",
        "<b>Výpočetní protokol polární metody</b> (TXT/PDF) se stejným členěním jako protokol z Gromy a "
        "tlačítko <b>Do seznamu bodů</b>; výpočet jde i bez vlastního seznamu.",
        "<b>Hlášení o problému</b> (Nápověda) – zkopírujete a pošlete; po pádu se nabídne samo.",
    ]),
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
        "<b>Seznam k opravě na tisk</b> (Ctrl+P) i <b>interaktivní HTML protokol</b> mají u chyb obrázek "
        "„chyba / správně“.",
        "<b>Režim soustředění</b> ukazuje postup (vyřešeno X z Y).",
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
