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
| Bloky (buňky): vložení, tvorba, knihovna | ❌ |
| Výběr podle vrstvy/vlastností, hledání prvků | 🟡 hromadná změna vrstvy a barvy; výběr podle vlastností chybí |
| Geodetické funkce (body ze seznamu s čísly a kódy, kódovník, výměry, mřížka, transformace výkresu) | ❌ |
| Rastry s georeferencí, podkladový DXF (reference) | ❌ |
| Tisk, rámečky, razítka, PDF, layouty | ❌ |
| Makra, dávky, pluginy | ❌ |
| Výkon na statisících prvků | ❌ |
