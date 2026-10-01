# Shoda s originály (Groma, MicroStation) – co aplikace umí a co chybí

Stav se průběžně aktualizuje. ✅ hotovo a ověřeno testy · 🟡 částečně · ❌ zatím chybí.
Vše je vlastní implementace podle matematiky a norem (nic se nekopíruje ani nezpětně nevyvíjí).

## Výpočty (náhrada Gromy)

| Funkce Gromy | Stav | Ověření |
|---|---|---|
| Seznam souřadnic (číslo, Y, X, Z, kód, kvalita), třídění, hledání, hromadné úpravy, duplicity | ✅ | testy seznamu |
| Import/export TXT/CSV s formátem sloupců | ✅ | skutečné seznamy ze zadání |
| Zpracování zápisníku (.zap), redukce délek, měřítkový koeficient, refrakce a zakřivení | ✅ | protokol Gromy Husovice |
| Opakovaná měření (dvě polohy), obousměrně měřené délky | ✅ | shoda s Gromou na mm |
| Polární metoda dávkou (orientace, posun, m0, podrobné body) | ✅ | 118 bodů vs. Groma ≤ 0,5 mm (poloha), ≤ 1,5 mm (výška) |
| Výpočetní protokol ve stejném členění (TXT/PDF) | ✅ | test protokolu |
| Směrník a délka, rajón | ✅ | ruční příklady, komplexní čísla |
| Protínání vpřed z úhlů / směrníků, z délek, zpět | ✅ | Shapely, Gauss–Newton |
| Volné stanovisko (MNČ) | ✅ | nezávislá MNČ (Gauss–Newton) |
| Transformace shodnostní, podobnostní, afinní (opravy, m0) | ✅ | přesný výpočet zlomky (1e-11 m) |
| Výměra a obvod | ✅ | přesný výpočet zlomky |
| Grafika seznamu souřadnic (čísla, výšky, kódy, výběr myší propojený s tabulkou, měření délky/směrníku/převýšení) | ✅ | test |
| Staničení a kolmice, bod ze staničení a kolmice | ✅ | zpětný výpočet |
| Kontrola dvou určení, mezní odchylky podle kódu kvality | 🟡 | hodnoty z vyhlášky k ověření |
| Ortogonální metoda (dávka, vyrovnání na měřenou délku) | ✅ | zpětný výpočet staničení a kolmic |
| Průsečík přímek, přímky a kružnice, dvou kružnic | ✅ | náhodné příklady, body leží na obou útvarech |
| Polygonový pořad (oboustranně připojený a orientovaný, vyrovnání) | ✅ | 50 syntetických pořadů bez chyb (přesně), rozdělení zavedených chyb |
| Vytyčovací prvky (směr a délka ze stanoviska) | ✅ | zpětný rajón |
| Trigonometrické výšky, nivelační pořad | ✅ | ruční příklady, uzávěr na mm |
| Oddělování parcel rovnoběžně s hranicí | ✅ | výměra na 0,0001 m² (Shapely) |
| Oddělování bodem, úprava hranic | ❌ | |
| Převod S-JTSK ↔ WGS84 (EPSG:5239, ≈ 1 m) s odkazem na mapy.cz | ✅ | shoda s PROJ na 2·10⁻⁸ ° |
| Import zápisníku Leica GSI-8 / GSI-16 (gon, stupně, mil; mm–0,01 mm) | ✅ | Husovice přes GSI = stejné souřadnice jako ze .zap |
| Další formáty totálních stanic (Trimble, Topcon, Sokkia) | ❌ | |
| Kresba podle kódů, export DXF | ❌ (v CAD) | |
| Vyrovnání sítě MNČ | ❌ | |

## CAD (náhrada MicroStationu pro 2D, jen DXF)

| Funkce MicroStationu | Stav |
|---|---|
| Otevření/uložení DXF beze ztrát, zpráva o načtení, poškozené soubory, čeština v kódové stránce 1250 | ✅ |
| Zobrazení (barvy, styly, texty, bloky, šrafy), zoom, posun | ✅ |
| Souřadnice kurzoru S-JTSK, úchyty (konec, střed, průsečík, kolmice, tečna), ortho, polární | ✅ |
| Příkazový řádek (key-in), zadání souřadnic, měření vzdálenosti | ✅ |
| Propojení s Kontrolou výkresu | ✅ |
| Kreslení: bod, úsečka, polylinie, obdélník, oblouk (3 body), kružnice, elipsa, křivka, text, šrafa, kóta | ✅ |
| Úpravy: výběr (klik, okno, protínající okno), posun, kopie (i v řadě), otočení, měřítko, zrcadlení, ořez, prodloužení, rovnoběžka, zaoblení / roh, spojení, rozpojení, mazání, vlastnosti (vrstva, barva) | ✅ |
| Zpět/Vpřed bez omezení | ✅ |
| Vrstvy: správce (zapnutí, zmrazení, zámek, barva, typ čáry, tloušťka, nová, přejmenovat, smazat, aktuální, výběr prvků vrstvy) | ✅ |
| Bloky (buňky): tvorba z výběru, vložení s měřítkem a natočením, rozpojení | ✅ |
| Knihovna buněk (sdílené bloky mezi výkresy) | ❌ |
| Vlastnosti prvku (dvojklik: vrstva, barva, styl, tloušťka, souřadnice, poloměr, text…), výběr podobných, výběr prvků vrstvy, najít a nahradit text | ✅ |
| Výkres podle zadání: vrstvy, typy čar, písma a buňky ze Směrnice / zadání / vzorového výkresu; druh prvku → atributy se nastaví samy (ověřeno kontrolou symbologie na obou zadáních); tahák s key-in pro MicroStation | ✅ |
| Geodetické funkce (kódovník bodů, mřížka, transformace výkresu) | ❌ |
| Reference: připojení DXF podkladu (XREF) s polohou, měřítkem, natočením; zobrazení pod výkresem, úchyty na referenci, kopie prvků z reference, odpojení se Zpět | ✅ |
| Modely: Model a výkresové listy (A3), výřezy modelu v měřítku | ✅ |
| Rastrové reference s georeferencí (world file) | ❌ |
| Tisk do PDF: model v měřítku 1:N (A4–A0, ověřeno: 100 m v 1:1000 = 100 mm), list 1:1, bílá → černá; rámeček a razítko na list | ✅ |
| Makra, dávky, pluginy | ❌ |
| Výkon na statisících prvků | ❌ |

## Jednotné pojmenování (Kontrola, CAD, tahák, atributy)

- Barva = číslo MicroStationu 0–255 (vestavěná tabulka color.tbl, nebo tabulka z projektu); v DXF ACI jako při exportu z MicroStationu.
- Styl čáry = 0–7 (v DXF „Continuous“, „DGN Style 1“…„DGN Style 7“ jako MicroStation), vlastní styly kódem („2.103“ Dřevěný plot) – skutečný vzor se převezme ze vzorového výkresu DXF nebo souboru .lin od učitele.
- Tloušťka = wt 0–31 (převod na mm podle zadání).
- Textové styly = „Style-Arial Narrow“, kurzíva „Style-Arial Narrow IF“, nebo názvy z knihovny učitele („Popis ploch“).
- Key-iny MicroStationu (lv=, co=, lc=, wt=, th=, tw=, ac=) fungují i v příkazovém řádku CAD.

## Plán dál

1. Dokončit nejčastěji používané funkce Gromy a MicroStationu, pak méně používané
   (uživatel programy projde a řekne, co není potřeba).
2. **Potom: náhrada programu Kokeš** (přání uživatele – až bude Groma a MicroStation hotové).
