# Shoda s originály (Groma, MicroStation) – co aplikace umí a co chybí

Stav se průběžně aktualizuje. ✅ hotovo a ověřeno testy · 🟡 částečně · ❌ zatím chybí.
Vše je vlastní implementace podle matematiky a norem (nic se nekopíruje ani nezpětně nevyvíjí).

## Výpočty (náhrada Gromy)

| Funkce Gromy | Stav | Ověření |
|---|---|---|
| Seznam souřadnic (číslo, Y, X, Z, kód, kvalita), třídění, hledání, hromadné úpravy, duplicity | ✅ | testy seznamu |
| Import/export TXT/CSV s formátem sloupců | ✅ | skutečné seznamy ze zadání |
| Zpracování zápisníku (.zap), redukce délek, měřítkový koeficient, refrakce a zakřivení | ✅ | protokol Gromy Husovice |
| Editor zápisníku (stanoviska, záměry v obou polohách, orientace/podrobné, uložení .zap, výpočet proti seznamu projektu, body do seznamu) | ✅ | .zap tam a zpět = stejné souřadnice |
| Opakovaná měření (dvě polohy), obousměrně měřené délky | ✅ | shoda s Gromou na mm |
| Polární metoda dávkou (orientace, posun, m0, podrobné body) | ✅ | 118 bodů vs. Groma ≤ 0,5 mm (poloha), ≤ 1,5 mm (výška) |
| Výpočetní protokol ve stejném členění (TXT/PDF) | ✅ | test protokolu |
| Směrník a délka, rajón | ✅ | ruční příklady, komplexní čísla |
| Protínání vpřed z úhlů / směrníků, z délek, zpět | ✅ | Shapely, Gauss–Newton |
| Volné stanovisko (MNČ) | ✅ | nezávislá MNČ (Gauss–Newton) |
| Transformace shodnostní, podobnostní, afinní (opravy, m0) | ✅ | přesný výpočet zlomky (1e-11 m) |
| Jungova dotransformace (opravy z identických bodů, váhy 1/d²) | ✅ | identické body přesně na cíl |
| Výměra a obvod | ✅ | přesný výpočet zlomky |
| Grafika seznamu souřadnic (čísla, výšky, kódy, výběr myší propojený s tabulkou, měření délky/směrníku/převýšení) | ✅ | test |
| Staničení a kolmice, bod ze staničení a kolmice | ✅ | zpětný výpočet |
| Kontrola dvou určení, mezní odchylky podle kódu kvality | 🟡 | hodnoty z vyhlášky k ověření |
| Kontrolní oměrné míry (měřená délka proti délce ze souřadnic, u_d = 2·m_xy·√((d+12)/(d+20))) | 🟡 | vzorec a m_xy z vyhlášky k ověření |
| Ortogonální metoda (dávka, vyrovnání na měřenou délku) | ✅ | zpětný výpočet staničení a kolmic |
| Průsečík přímek, přímky a kružnice, dvou kružnic | ✅ | náhodné příklady, body leží na obou útvarech |
| Polygonový pořad (oboustranně připojený a orientovaný, vyrovnání) | ✅ | 50 syntetických pořadů bez chyb (přesně), rozdělení zavedených chyb |
| Vytyčovací prvky (směr a délka ze stanoviska) | ✅ | zpětný rajón |
| Trigonometrické výšky, nivelační pořad | ✅ | ruční příklady, uzávěr na mm |
| Oddělování parcel rovnoběžně s hranicí | ✅ | výměra na 0,0001 m² (Shapely) |
| Oddělování dělicí čarou z bodu na hranici | ✅ | přesná výměra (lineární na straně) |
| Úprava hranic (směna pozemků) | ❌ | |
| Převod S-JTSK ↔ WGS84 (EPSG:5239, ≈ 1 m) s odkazem na mapy.cz | ✅ | shoda s PROJ na 2·10⁻⁸ ° |
| Import zápisníku Leica GSI-8 / GSI-16 (gon, stupně, mil; mm–0,01 mm) | ✅ | Husovice přes GSI = stejné souřadnice jako ze .zap |
| Další formáty totálních stanic (Trimble, Topcon, Sokkia, Nikon) | ❌ | |
| QTrig (vlastní terénní aplikace): body zakázky z firemního cloudu (přírůstkově, hlídání), export bodů, nivelace, zápisník směrů | ✅ | převod WGS84 → S-JTSK shodný s QTrig pod 0,001 mm |
| Spojnice bodů v grafice (ručně, podle kódu), přenos do CAD | ✅ | test |
| Export seznamu do DXF (body, čísla, výšky, kódy, spojnice), KML, GeoJSON, PDF k odevzdání | ✅ | DXF i WGS84 zpět na mm |
| Porovnání dvou seznamů (kontrolní měření): ΔY, ΔX, Δp, ΔZ, mezní odchylky | 🟡 | mezní odchylky k ověření ve vyhlášce |
| Body ze seznamu do výkresu (shodně se světem, hladiny a atributy podle zadání, kódy buněk) | ✅ | kontrola symbologie bez chyb |
| Vyrovnání sítě MNČ (směry + délky, apriorní přesnosti, σ0, střední chyby, elipsy chyb, opravy) | ✅ | přesná síť vyjde přesně, se šumem shoda s nezávislou MNČ na 0,01 mm |

## CAD (náhrada MicroStationu pro 2D, jen DXF)

| Funkce MicroStationu | Stav |
|---|---|
| Otevření/uložení DXF beze ztrát, zpráva o načtení, poškozené soubory, čeština v kódové stránce 1250 | ✅ |
| Zobrazení (barvy, styly, texty, bloky, šrafy), zoom, posun | ✅ |
| Souřadnice kurzoru S-JTSK, úchyty (konec, střed, průsečík, kolmice, tečna), ortho, polární | ✅ |
| Příkazový řádek (key-in), zadání souřadnic, měření vzdálenosti | ✅ |
| Propojení s Kontrolou výkresu | ✅ |
| Kreslení: bod, úsečka, polylinie, obdélník, mnohoúhelník, oblouk (3 body, středem), kružnice (střed, 3 body, průměr), elipsa, křivka, text, popisek s odkazovou čárou, šrafa, kóta (i řetězová), kóta úhlu a poloměru, oměrné míry | ✅ |
| Zadávání bodů: Y X, @dx,dy, @délka<směrník, key-iny xy= / dl= / di=, číslo bodu ze seznamu (#4001), délka číslem ve směru kurzoru (jako AccuDraw) | ✅ |
| Úpravy: výběr (klik, okno, protínající okno, ohrada, podle atributů), posun, natažení oknem (Fence Stretch), smazání části prvku (Delete Part of Element), kopie (i v řadě), pole obdélníkové a kruhové, otočení, měřítko, zrcadlení, ořez, prodloužení, rovnoběžka, zaoblení / roh, zkosení, rozdělení, body po prvku, vložení / smazání / posun vrcholu, spojení, rozpojení, mazání, úprava textu, převzetí a změna atributů | ✅ |
| Schránka Ctrl+C / Ctrl+V mezi výkresy (i s hladinami, styly a buňkami, na stejné souřadnice) | ✅ |
| Pohledy: celý výkres, přiblížit oknem, předchozí pohled, kolečko | ✅ |
| Hladiny příkazem (zhasni / rozsviť, i „vše kromě“) | ✅ |
| Zpět/Vpřed bez omezení | ✅ |
| Vrstvy: správce (zapnutí, zmrazení, zámek, barva, typ čáry, tloušťka, nová, přejmenovat, smazat, aktuální, výběr prvků vrstvy) | ✅ |
| Bloky (buňky): tvorba z výběru, vložení s měřítkem a natočením, rozpojení | ✅ |
| Knihovna buněk: buňky z knihovny MicroStationu .CEL (V8), buňky, typy čar a styly textu z jiného DXF nebo .lin (příkaz „knihovna“, „rc“) | ✅ | NORMA.CEL 170 buněk, GEO-V8.CEL 256 buněk |
| Vložení buňky s aktivní barvou, tloušťkou a měřítkem buňky ze zadání | ✅ |
| Převod atributů na jiná pravidla podle značek (buňky, styly čar) a vrstev, s poměrem měřítek (příkaz „převod“) | ✅ | úloha Zadání-převod |
| Vlastnosti prvku (dvojklik: vrstva, barva, styl, tloušťka, souřadnice, poloměr, text…), výběr podobných, výběr prvků vrstvy, najít a nahradit text | ✅ |
| Výkres podle zadání: vrstvy, typy čar, písma a buňky ze Směrnice / zadání / vzorového výkresu; druh prvku → atributy se nastaví samy (ověřeno kontrolou symbologie na obou zadáních); tahák s key-in pro MicroStation | ✅ |
| Geodetické funkce: transformace výkresu podle identických bodů (shodnostní, podobnostní, afinní, opravy a m0, jedno Zpět), souřadnicová síť s popisy, body ze seznamu podle kódů (buňky) | ✅ |
| Reference: připojení DXF podkladu (XREF) s polohou, měřítkem, natočením; zobrazení pod výkresem, úchyty na referenci, kopie prvků z reference, odpojení se Zpět | ✅ |
| Modely: Model a výkresové listy (A3), výřezy modelu v měřítku | ✅ |
| Rastrové podklady (ortofoto, sken) s georeferencí z world filu (.jgw/.pgw/.tfw), nebo umístění dvěma body; uložení jako DXF IMAGE | ✅ |
| Tisk do PDF: model v měřítku 1:N (A4–A0, ověřeno: 100 m v 1:1000 = 100 mm), list 1:1, bílá → černá; rámeček a razítko na list | ✅ |
| Makra, dávky, pluginy | ❌ |
| Výkon na velkých výkresech | 🟡 | 
|  – 50 000 prvků: otevření ≈ 10 s, výběr všeho 0,1 s, posun všeho ≈ 11 s, Zpět ≈ 9 s (překreslení knihovnou ezdxf) | |
| Skupiny prvků (Graphic Group): skupina z výběru, klik vybere celou skupinu, zámek skupin, vyjmutí; skupina vydrží úpravy i uložení | ✅ |

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
3. **Úkoly z nových zadání učitele** (materiály v `podklady/ucitel-dalsi`, uživatel k nim zatím nic dalšího nemá):
   - *Zadání-převod*: mapa plynovodu → mapa spojového vedení (zakládací UGEO.DGN, NORMA.cel, UGEO_VP.rsc),
     Směrnice pro 1:1000 → výkres 1:500. Hotovo: pravidla po objektech ze Směrnice ve Wordu + přepočet měřítka.
     Hotovo i čtení knihoven buněk .CEL (V8) do CAD (příkaz „knihovna“, .CEL v Podkladech se převezme
     při „Nový podle zadání“) a převod atributů podle značky (příkaz „převod“: buňka / styl čáry
     automaticky, zbytek po skupinách vrstev). Zbývá: styly čar z .RSC (zatím přes DXF / .lin).
   - *Zadání-Kokeš*: vlastní tabulky Kokeše (barvy = paleta MicroStationu, barva 0 → 100, kreslicí klíče KK ze
     Směrnice, styl 4 → −13, klíče 1xx pro barvy textů, font 1 → 2). Potřeba: původní obecné tabulky Kokeše
     (složka wkokes) – uživatel zatím nemá.
