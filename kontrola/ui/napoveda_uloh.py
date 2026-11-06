"""Krátké návody k výpočetním úlohám (ikonka ⓘ ve výpočetním okně): co úloha počítá, kdy ji použít,
postup krok za krokem a co znamenají jednotlivá pole. Psáno pro studenta, který úlohu dělá poprvé.

NACRT říká, jak se body úlohy spojí v náčrtu (paprsky ze stanoviska, lomená čára pořadu, obrazec …)."""

from __future__ import annotations

from html import escape

# název úlohy → (co počítá, postup, pole a jejich význam)
NAVODY: dict[str, tuple[str, list[str], list[tuple[str, str]]]] = {
    "Směrník a délka": (
        "Spočítá směrník (směr vůči severu v gonech) a vodorovnou délku mezi dvěma body ze souřadnic. "
        "Mají-li body výšku, i převýšení, šikmou délku, sklon a spád.",
        ["Do Počátečního bodu napište číslo bodu (nebo ho přetáhněte myší ze seznamu souřadnic).",
         "Totéž pro Koncový bod.", "Stiskněte Výpočet – výsledky se objeví dole v polích."],
        [("Počáteční / koncový bod", "odkud a kam se měří; směrník je od počátečního ke koncovému"),
         ("Směrník", "úhel od kladné osy +X po směru hodinových ručiček (v S-JTSK míří +X k jihu)"),
         ("Spád", "převýšení / délka v procentech")]),
    "Rajón (polární bod)": (
        "Polární metoda: nový bod ze stanoviska, kde jste měřili vodorovný směr a délku. Osnova směrů se "
        "nejdřív zorientuje na známé body (orientace).",
        ["Záložka Stanovisko: číslo stanoviska (musí být v seznamu souřadnic) a výška stroje.",
         "Do tabulky Orientace přidejte známé body, na které jste měřili, a jejich měřený směr (délka je jen "
         "pro kontrolu). Rychleji: přetáhněte červené číslo stanoviska ze Seznamu měření – orientace se doplní "
         "samy.",
         "Záložka Určovaný bod: číslo nového bodu, měřený směr a vodorovná délka (výška cíle a zenit pro výšku).",
         "Výpočet → zkontrolujte opravy orientací v tabulce → zeleným ✓ uložte bod do seznamu."],
        [("Výška stroje / cíle", "pro výpočet výšky Z (fialová pole)"),
         ("Oprava (v tabulce orientací)", "rozdíl orientace od průměru – velká oprava = špatný bod nebo směr"),
         ("Výpočet ze směrníků", "když místo směrů znáte rovnou směrníky"),
         ("Výpočet pro bodové pole", "přísnější testy pro body bodového pole")]),
    "Protínání vpřed z úhlů": (
        "Nový bod ze dvou úhlů měřených na koncích známé základny A–B (bez délek).",
        ["Zadejte body A a B (známé).", "Úhel α měřený na A (od B k novému bodu) a β na B.",
         "Číslo nového bodu, Výpočet."],
        [("α, β", "úhly v gonech uvnitř trojúhelníku A–B–nový bod")]),
    "Protínání vpřed ze směrů": (
        "Nový bod ze směrů měřených ze dvou známých stanovisek. Každé stanovisko se nejdřív zorientuje.",
        ["Záložka Stanovisko A: číslo stanoviska a orientace (jako u polární metody).",
         "Záložka Stanovisko B: totéž pro druhé stanovisko.",
         "Na obou záložkách zapište směr na určovaný bod, nahoře číslo nového bodu, Výpočet."],
        [("Úhel protnutí", "ideálně kolem 100 g; pod 30 g je výsledek nejistý (test v protokolu)")]),
    "Protínání z délek": (
        "Nový bod ze dvou vodorovných délek měřených od dvou známých bodů (jako kružítkem).",
        ["Levé stanovisko: známý bod a délka k novému bodu.", "Pravé stanovisko: druhý bod a jeho délka.",
         "Výpočet. Nový bod leží vpravo od spojnice levé → pravé; jinak stanoviska prohoďte."],
        [("Levé / pravé", "při pohledu z nového bodu na oba známé body")]),
    "Protínání zpět": (
        "Souřadnice stanoviska ze směrů měřených na tři známé body (bez délek).",
        ["Tři známé body a směry na ně měřené ze stanoviska.", "Výpočet."],
        [("Nebezpečná kružnice", "leží-li stanovisko na kružnici přes tři body, úloha nemá řešení")]),
    "Volné stanovisko": (
        "Stanovisko, které nemá souřadnice: z měřených směrů a délek na aspoň dva známé body se spočítá "
        "jeho poloha i orientace (vyrovnání).",
        ["Nahoře číslo nového stanoviska a výška stroje.",
         "Do tabulky Orientace přidejte známé body se směrem a délkou (nejméně 2, lépe 3 a více).",
         "Typ výpočtu: podobnostní transformace (běžně), shodnostní (měřítko 1) nebo MNČ.",
         "Výpočet → podívejte se na opravy v tabulce → ✓ uložte stanovisko."],
        [("Opravy", "jak moc jednotlivé body nesedí; velká oprava = chybný bod"),
         ("Měřítko", "u podobnostní transformace by mělo být velmi blízko 1")]),
    "Transformace": (
        "Převede body z jedné souřadnicové soustavy do druhé (např. místní → S-JTSK). Klíč se spočítá z "
        "identických bodů, které znáte v obou soustavách.",
        ["Identické body: vlevo nahoře cílové souřadnice (S-JTSK), pod nimi místní souřadnice téhož bodu, "
         "Přidat. Opakujte (aspoň 2 body, u afinní 3).",
         "Zvolte typ transformace.",
         "Do pole Transformovat body přetáhněte body, které chcete převést (nebo Všechny body seznamu).",
         "Výpočet → zkontrolujte opravy dY, dX, dP na identických bodech → ✓ uložte."],
        [("Shodnostní", "posun + otočení, měřítko 1 – tvar i velikost se zachová (2 body)"),
         ("Podobnostní", "posun + otočení + jedno měřítko – tvar se zachová (2 body)"),
         ("Afinní", "6 parametrů, různé měřítko v různých směrech, nezachová pravé úhly (3 body)"),
         ("Uživatelská", "vlastní rovnice Y' = …, X' = … bez identických bodů"),
         ("Jungova dotransformace", "rozdělí zbylé opravy na okolní body – identické body sedí přesně")]),
    "Výměra a obvod": (
        "Výměra plochy (parcely) a obvod ze souřadnic lomových bodů.",
        ["Body zapisujte nebo přetahujte postupně po obvodu (jedním směrem).",
         "Je-li hranice oblouk, přidejte jeho vrchol (prostřední bod oblouku) se zaškrtnutým Oblouk.",
         "Výpočet. Kalkulačkou + / − sčítáte výměry více ploch."],
        [("Parcela / Díl", "jen označení do protokolu")]),
    "Kružnicový oblouk": (
        "Vytyčení kruhového oblouku mezi dvěma tečnami: hlavní body (začátek, konec, střed oblouku) a podrobné "
        "body po zvolené délce.",
        ["Vrchol tečen = průsečík obou přímých úseků.", "Body na první a druhé tečně (směry tečen).",
         "Poloměr oblouku a způsob rozložení (krok po oblouku), Výpočet."],
        [("ZO / KO / VO", "začátek, konec a vrchol (střed) oblouku")]),
    "Výměry parcel dávkou": (
        "Výměry více parcel najednou.",
        ["Na každý řádek: označení parcely, dvojtečka a čísla bodů po obvodu.", "Výpočet."],
        []),
    "Staničení a kolmice": (
        "Pro body spočítá staničení (vzdálenost podél přímky od počátku) a kolmici (kolmou vzdálenost) k přímce "
        "A–B. Používá se pro oměrné míry a kontrolu ortogonální metody.",
        ["Počáteční a koncový bod přímky.", "Do pole Vytyčované body přetáhněte body.", "Výpočet."],
        [("Kolmice", "kladná = vpravo od přímky ve směru A → B")]),
    "Bod ze staničení a kolmice": (
        "Opak předchozí úlohy: nový bod ze zadaného staničení a kolmice k přímce A–B.",
        ["Body přímky A a B.", "Staničení (od A) a kolmice (+ vpravo).", "Číslo nového bodu, Výpočet."], []),
    "Kontrola dvou určení": (
        "Porovná dvě určení téhož bodu (např. ze dvou stanovisek) a otestuje rozdíl proti mezní odchylce.",
        ["Dvě čísla bodů (nebo bod a ručně zadané souřadnice).", "Výpočet."], []),
    "Kontrolní oměrné míry": (
        "Porovná v terénu změřené délky (oměrné míry) s délkami spočtenými ze souřadnic.",
        ["Body přidávejte v pořadí, jak jdou po sobě, a ke každému měřenou oměrnou od předchozího bodu.",
         "Výpočet – v protokolu je rozdíl a mezní odchylka podle kódu kvality."], []),
    "Testování přesnosti ÚM – body": (
        "Test přesnosti účelové mapy: výsledné souřadnice proti nezávislému kontrolnímu zaměření.",
        ["Řádky: číslo bodu ze seznamu a souřadnice z kontrolního měření.", "Výpočet."], []),
    "Testování přesnosti ÚM – délky": (
        "Test přesnosti: kontrolně změřené délky proti délkám ze souřadnic.",
        ["Řádky: dva body a měřená délka.", "Výpočet."], []),
    "Výměra z měr": (
        "Výměra plochy rozdělené na trojúhelníky, z nichž znáte všechny tři strany (Heronův vzorec).",
        ["Na každý řádek tři strany jednoho trojúhelníku.", "Výpočet."], []),
    "Kružnice ze tří bodů": ("Střed a poloměr kružnice procházející třemi body.",
                             ["Zadejte tři body na kružnici.", "Výpočet."], []),
    "Úhel ze souřadnic": ("Vrcholový úhel mezi dvěma rameny ze souřadnic.",
                          ["Vrchol, bod na levém a bod na pravém rameni.", "Výpočet (úhel po směru hodin)."],
                          []),
    "Bod na přímce": ("Nový bod na přímce A–B v zadané vzdálenosti od A, nebo dělení úsečky.",
                      ["Body A a B.", "Vzdálenost od A (nebo počet dílů).", "Výpočet."], []),
    "Průsečíky": (
        "Průsečík dvou přímek. Každá přímka je dána dvěma body; přímku lze i rovnoběžně odsadit.",
        ["První přímka: počáteční a koncový bod.", "Druhá přímka: počáteční a koncový bod.",
         "Číslo nového bodu, Výpočet."],
        [("Odsazení", "posune přímku rovnoběžně (+ vpravo ve směru přímky), např. o šířku zdi")]),
    "Ortogonální metoda": (
        "Body zaměřené staničením a kolmicí od měřické přímky (dávkou).",
        ["Body přímky A a B, měřená délka přímky.", "Řádky: číslo bodu, staničení, kolmice.", "Výpočet."], []),
    "Polygonový pořad": ("Oboustranně připojený a orientovaný polygonový pořad (formulář).",
                         ["Doporučuji okno Polygonový pořad z pásu Bodové pole – pozná typ pořadu sám."], []),
    "Polygonový pořad uzavřený": ("Pořad, který začíná i končí na stejném bodě.", ["Vyplňte body a měření."], []),
    "Polygonový pořad volný": ("Jednostranně připojený pořad bez kontroly – jen výjimečně.",
                               ["Vyplňte body a měření."], []),
    "Polygonový pořad jednostranně orientovaný": ("Připojený na obou koncích, orientovaný jen na začátku.",
                                                  ["Vyplňte body a měření."], []),
    "Polygonový pořad vetknutý": ("Připojený na dva body bez orientací.", ["Vyplňte body a měření."], []),
    "Centrace směrů": ("Převod směrů měřených z excentrického stanoviska na centr.",
                       ["Excentricita (délka a směr) a měřené směry.", "Výpočet."], []),
    "Vytyčovací prvky": (
        "Spočítá, co nastavit na přístroji pro vytyčení bodu: směr (úhel od orientace) a délku.",
        ["Stanovisko (a výška stroje).", "Orientace: známý bod a směr, který na něj přístroj ukazuje.",
         "Vytyčované body přetáhněte ze seznamu souřadnic.", "Výpočet – v tabulce je směr a délka ke každému."],
        [("Směr", "hodnota Hz, kterou otočíte na přístroji"), ("Směrník", "směr vůči severu")]),
    "Trigonometrická výška": ("Výška bodu ze šikmé délky a zenitového úhlu.",
                              ["Výška stanoviska, výška stroje a cíle.", "Šikmá délka a zenitový úhel.",
                               "Výpočet."], []),
    "Trigonometrická výška oboustranně": ("Převýšení měřené tam i zpět – průměr vyloučí zakřivení a refrakci.",
                                          ["Měření tam a zpět.", "Výpočet."], []),
    "Redukce délky": ("Převod měřené délky do roviny S-JTSK (vodorovná, nadmořská výška, měřítko zobrazení).",
                      ["Šikmá délka a zenitový úhel, nadmořská výška, souřadnice.", "Výpočet."], []),
    "Nivelační pořad": ("Výšky bodů pořadu mezi dvěma výškově danými body s rozdělením uzávěru.",
                        ["Počáteční a koncový bod s výškou.", "Převýšení a délky oddílů.", "Výpočet."], []),
    "Nivelační zápisník": (
        "Technická nivelace ze středu: čtení na lati vzad a vpřed, kontrola zápisníku a výšky bodů.",
        ["Počáteční a koncový bod (známé výšky).", "Do tabulky přidávejte body: čtení Zpět, Vpřed, případně "
                                                    "Bočně a délku.", "Výpočet – uzávěr se rozdělí."],
        [("Zpět / Vpřed", "čtení na lati na zadní a přední bod sestavy")]),
    "Vyrovnání nivelační sítě": ("Výšky bodů sítě z převýšení metodou nejmenších čtverců.",
                                 ["Pevné body s výškou a měřená převýšení s délkami.", "Výpočet."], []),
    "Oddělení parcely": ("Oddělí část parcely zadané výměry dělicí čarou.",
                         ["Body parcely po obvodu, výměra oddělované části, směr dělicí čáry.", "Výpočet."], []),
    "Model terénu a kubatura": (
        "Kubatura: z bodů s výškou se vytvoří model terénu a spočítá objem nad / pod srovnávací rovinou.",
        ["Body terénu přetáhněte ze seznamu (musí mít výšku Z).", "Výška srovnávací roviny.", "Výpočet."],
        [("Výkop / násyp", "objem terénu nad / pod rovinou")]),
    "Výkaz výměr GP": ("Geometrický plán: výměry dosavadního a nového stavu ze souřadnic.",
                       ["Parcely a díly s body po obvodu.", "Výpočet."], []),
    "Převod úhlů": ("Převod úhlů mezi gony, stupni a radiány.", ["Na každý řádek jeden úhel.", "Výpočet."], []),
    "Převod S-JTSK ↔ WGS84": ("Zeměpisné souřadnice bodů (přibližně, ±1 m) a opačně.",
                              ["Body ze seznamu nebo zeměpisné souřadnice.", "Výpočet."], []),
    "Ortogonální metoda (Groma)": (
        "Body zaměřené od měřické přímky: staničení (podél přímky) a kolmice (kolmo k ní). Přímka se umístí "
        "transformací na identické body (body, které znáte i v souřadnicích).",
        ["Identické body: číslo, staničení a kolmice aspoň dvou známých bodů na přímce (obvykle začátek a konec).",
         "Měřené hodnoty: číslo nového bodu, jeho staničení a kolmice, Výpočet.",
         "✓ uloží bod; pokračujte dalším bodem."],
        [("Staničení", "vzdálenost od začátku přímky podél ní"),
         ("Kolmice", "kolmá vzdálenost od přímky, + vpravo, − vlevo"),
         ("Oprava délky", "rozdíl měřené a ze souřadnic spočtené délky mezi identickými body")]),
    "Výška stanoviska": (
        "Výška (Z) stanoviska z měření na body se známou výškou (trigonometricky).",
        ["Číslo stanoviska a výška stroje.", "Do tabulky Orientace přidejte body s výškou: délku a zenitový úhel "
                                             "(nebo převýšení) a výšku cíle.", "Výpočet – výška je průměr."],
        []),
    "Vyrovnání na přímku": (
        "Posune bod kolmo na přímku (pata kolmice). Používá se, když má bod ležet přesně na přímce (např. lomový "
        "bod na hranici) a vlivem měření o kousek „uletěl“.",
        ["Počáteční a koncový bod přímky (ty se nehýbou).", "Vyrovnávaný bod = bod, který má ležet na přímce.",
         "Výpočet – vypočtené souřadnice jsou průmět bodu na přímku, vzdálenost ukazuje, jak daleko byl."],
        [("Vyrovnaný bod", "nové souřadnice bodu přesně na přímce (✓ uloží; číslo může zůstat stejné)")]),
    "Vyrovnání na kružnici": (
        "Posune bod na kružnici (oblouk) danou třemi body – např. bod obrubníku na oblouku, který má ležet "
        "přesně na kružnici.",
        ["1., 2. a 3. bod = tři body, kterými kružnice prochází (definují ji).",
         "Vyrovnávaný bod = bod, který chcete posunout na kružnici.",
         "Výpočet – bod se posune po spojnici se středem na kružnici; vidíte i poloměr a jak daleko byl."],
        [("Bod 1, 2, 3", "body na kružnici, ze kterých se spočítá střed a poloměr"),
         ("Vypočtené souřadnice", "kde bod leží po posunu na kružnici")]),
    "Vyrovnávací přímka": (
        "Nejlépe padnoucí přímka mnoha body (metoda nejmenších čtverců) – např. přímá hrana zdi zaměřená více "
        "body. Body pak lze na tu přímku posunout.",
        ["Do tabulky přidejte body, které na přímce mají ležet (Definiční).",
         "Výpočet – u každého bodu vidíte vzdálenost od přímky.",
         "Volbou Vyrovnat body je posunete na přímku, ✓ uloží."], []),
    "Vyrovnávací kružnice": (
        "Nejlépe padnoucí kružnice mnoha body (MNČ), volitelně s pevným poloměrem.",
        ["Do tabulky přidejte body na oblouku.", "Výpočet – střed, poloměr a vzdálenosti bodů.",
         "Volbou Vyrovnat body je posunete na kružnici."], []),
    "Průsečík přímka - směr": (
        "Průsečík přímky A–B se směrem měřeným ze stanoviska (např. roh budovy, na který nejde měřit délka).",
        ["Záložka Stanovisko: stanovisko a orientace.", "Druhá záložka: body A a B přímky a měřený směr.",
         "Číslo nového bodu, Výpočet."], []),
    "Průsečík přímka - kružnice": (
        "Průsečík přímky (2 body) a kružnice (3 body). Úloha má obvykle dvě řešení – vybere se bližší.",
        ["Kružnice: tři body.", "Přímka: body A a B.", "Číslo nového bodu, Výpočet."], []),
    "Konstrukční oměrné": (
        "Obrazec (např. budova) z oměrných měr s pravými úhly. Program sestaví tvar a umístí ho na zaměřené "
        "rohy transformací.",
        ["Do tabulky zapište body obrazce po obvodu a délky stran (oměrné).",
         "Aspoň dva body musí být zaměřené (v seznamu souřadnic).",
         "Výpočet – nové body dostanou souřadnice."], []),
    "Trojúhelníková kalkulačka": (
        "Dopočítá trojúhelník ze tří zadaných údajů (strany a úhly v gonech) a jeho výměru.",
        ["Vyplňte tři údaje (např. 3 strany, nebo 2 strany a úhel).", "Výpočet – zbytek se doplní."],
        [("a, b, c", "strany; úhel α leží proti straně a")]),
    "Polygonový pořad (Groma)": (
        "Polygonový pořad: body bodového pole z měřených směrů a délek. Typ pořadu (oboustranně připojený, "
        "uzavřený, volný …) se pozná sám podle toho, co vyplníte.",
        ["Počáteční bod: stanovisko a orientace (známé body a směry).",
         "Koncový bod: totéž na konci pořadu (pokud je připojený).",
         "Měřená data: vrcholy pořadu postupně – směr a délka zpět a vpřed.",
         "Výpočet → záložka Výsledky: úhlový uzávěr, odchylky a souřadnice → ✓ uložit."],
        [("Úhlový uzávěr", "součet chyb úhlů, rozdělí se rovnoměrně"),
         ("Polohová odchylka", "jak moc pořad „nedojde“ na koncový bod; musí být pod mezní")]),
    "Výškový pořad": (
        "Trigonometrický výškový pořad měřený tam i zpět, s rozdělením uzávěru.",
        ["Počáteční a koncový bod se známou výškou.", "Měřená data: body a délky, zenitové úhly, výšky stroje "
                                                     "a cíle zpět i vpřed.", "Výpočet."], []),
    "Polární metoda dávkou": (
        "Spočítá celý zápisník najednou: orientace všech stanovisek, podrobné body a výšky (jako v Gromě).",
        ["Načtěte měření (zápisník .zap nebo GSI) a mějte otevřený seznam souřadnic s danými body.",
         "Zkontrolujte Měřítko na liště nahoře (tlačítko Z bodů… ho spočítá).",
         "Volby zpracování (polohy, refrakce, …) nastavíte v Seznamu měření → Zpracování….",
         "Výpočet – body se uloží do aktivního seznamu, protokol do okna Protokol."], []),
    "Výšky dávkou": (
        "Doplní výšky bodům ze zápisníku (trigonometricky) do seznamu souřadnic.",
        ["Načtěte měření.", "Výpočet."], []),
}

# jak body spojit v náčrtu
NACRT = {
    "Rajón (polární bod)": "polar", "Výška stanoviska": "polar", "Vytyčovací prvky": "polar",
    "Volné stanovisko": "volne", "Protínání zpět": "volne",
    "Protínání vpřed ze směrů": "protinani", "Protínání vpřed z úhlů": "protinani", "Protínání z délek": "protinani",
    "Směrník a délka": "lomena", "Polygonový pořad (Groma)": "lomena", "Polygonový pořad": "lomena",
    "Polygonový pořad uzavřený": "lomena", "Polygonový pořad volný": "lomena",
    "Polygonový pořad jednostranně orientovaný": "lomena", "Polygonový pořad vetknutý": "lomena",
    "Výškový pořad": "lomena", "Nivelační pořad": "lomena", "Kontrolní oměrné míry": "lomena",
    "Výměra a obvod": "uzavrena", "Konstrukční oměrné": "uzavrena", "Oddělení parcely": "uzavrena",
    "Průsečíky": "primky", "Průsečík přímka - kružnice": "primky", "Vyrovnání na přímku": "primky",
    "Staničení a kolmice": "primky", "Bod ze staničení a kolmice": "primky", "Ortogonální metoda (Groma)": "primky",
    "Průsečík přímka - směr": "polar", "Vyrovnání na kružnici": "body", "Kružnicový oblouk": "lomena",
}


def html(nazev: str, popis: str = "", pole=()) -> str:
    """Návod jako HTML do okna úlohy."""
    co, kroky, vyznam = NAVODY.get(nazev, (popis, [], []))
    if not kroky and pole:  # obecný návod z polí formuláře
        kroky = ["Vyplňte pole (body můžete přetáhnout ze seznamu souřadnic).", "Stiskněte Výpočet.",
                 "Vypočtené body uložíte tlačítkem ✓ / Do seznamu."]
        vyznam = [(p.label, p.napoveda) for p in pole if getattr(p, "napoveda", "")]
    r = [f"<p><b>{escape(nazev)}</b> – {escape(co or popis)}</p>"]
    if kroky:
        r.append("<p style='margin-bottom:2px'><b>Postup:</b></p><ol style='margin-top:0'>"
                 + "".join(f"<li>{escape(k)}</li>" for k in kroky) + "</ol>")
    if vyznam:
        r.append("<p style='margin-bottom:2px'><b>Co znamená:</b></p><ul style='margin-top:0'>"
                 + "".join(f"<li><b>{escape(a)}</b> – {escape(b)}</li>" for a, b in vyznam) + "</ul>")
    r.append("<p style='color:#6B7280'>Tip: body přetahujte myší ze seznamu souřadnic, měření ze Seznamu "
             "měření. Náčrt vpravo ukazuje, jak body leží – porovnejte ho se skutečností.</p>")
    return "".join(r)
