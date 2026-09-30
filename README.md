# Kontrola výkresu

Desktopová aplikace pro Windows, která **před odevzdáním zkontroluje topologii a atributy
geodetického výkresu** z MicroStationu. Podobně jako nadstavba MGEO najde nezavřené polygony,
visící konce, průsečíky bez uzlu, duplicity, prvky na špatné hladině nebo chybějící atributy.
Každou chybu ve výkresu **zakroužkuje a popíše**.

Aplikace je určená jako předkontrola školního výkresu. Pravidla si vytvoříte z tabulky atributů
od učitele nebo ze vzorového výkresu.

![Hlavní okno](docs/obrazovka.png)

> Všechna data zůstávají na vašem počítači. Aplikace nic nikam neodesílá.

---

## Obsah

1. [Instalace a spuštění](#instalace-a-spuštění)
2. [Rychlý start s ukázkovými daty](#rychlý-start-s-ukázkovými-daty)
3. [Vyzkoušení po krocích](#vyzkoušení-po-krocích)
4. [Převod DGN na DXF](#převod-dgn-na-dxf)
5. [Kontroly](#kontroly)
6. [Zadání: tabulka atributů, náčrty, vzor, podklady](#zadání-tabulka-atributů-náčrty-vzor-podklady)
7. [Pravidla a konfigurace v YAML](#pravidla-a-konfigurace-v-yaml)
8. [Výstupy](#výstupy)
9. [Příkazová řádka](#příkazová-řádka)
10. [Sestavení .exe](#sestavení-exe)
11. [Pro vývojáře: struktura a přidání kontroly](#pro-vývojáře-struktura-a-přidání-kontroly)
12. [Známá omezení](#známá-omezení)

---

## Instalace a spuštění

### Hotový program (.exe)

**Stažení:** [KontrolaVykresu.exe](https://github.com/stepanvcelak11/kontrola-vykresu/releases/latest/download/KontrolaVykresu.exe)
(poslední verze, sestavuje se automaticky po každé změně). Program se neinstaluje, stačí ho
spustit. Windows může upozornit na neznámého vydavatele: *Další informace → Přesto spustit*.
Ukázková data jsou ve složce [`ukazky/`](ukazky/) (celý repozitář stáhnete přes
*Code → Download ZIP*). Program si můžete sestavit i sami, viz [Sestavení .exe](#sestavení-exe).

### Z Pythonu (Windows, Python 3.11 nebo novější)

```bat
git clone https://github.com/stepanvcelak11/kontrola-vykresu.git
cd kontrola-vykresu
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python spustit.py
```

Místo `python spustit.py` jde použít i `python -m kontrola`. Na Linuxu a macOS se postupuje
stejně, jen aktivace je `source .venv/bin/activate`.

Při prvním spuštění se vytvoří projekt **„Můj projekt“** ve složce
`Dokumenty\Kontrola výkresu\`. Při dalším spuštění se otevře naposledy použitý projekt.

---

## Rychlý start s ukázkovými daty

Složka `ukazky/` obsahuje:

| Soubor | Co to je |
|---|---|
| `ukazkovy_vykres.dxf` | malý polohopis v S-JTSK s **úmyslnými chybami** |
| `vzorovy_vykres.dxf` | stejný výkres bez chyb, slouží jako „vzor od učitele“ |
| `tabulka_atributu.xlsx`, `.csv` | ukázková tabulka prvků (číselník) od učitele |
| `konfigurace.yaml` | okomentovaná konfigurace: nastavení kontrol a pravidla |
| `nacrt.png` | jednoduchý náčrt |
| `vytvor_ukazky.py` | skript, který všechny ukázky znovu vytvoří |

1. Spusťte aplikaci a přetáhněte `ukazky/ukazkovy_vykres.dxf` do okna.
2. Přepněte na záložku **Zadání → Tabulka atributů** a přetáhněte sem
   `ukazky/tabulka_atributu.xlsx`. Průvodce sám rozpozná sloupce. Potvrďte **Vytvořit pravidla**.
   Souhrn ukáže, že vzniklo 10 pravidel a jeden řádek (`???`) se zpracovat nepodařilo.
3. Stiskněte **F5 (Zkontrolovat)**. Vpravo se objeví seznam chyb a ve výkresu kroužky.
4. Klikněte na řádek chyby: výkres se na ni přiblíží. Klávesy F7 a F8 přepínají předchozí
   a další chybu.
5. Opravte výkres v MicroStationu, uložte DXF a stiskněte **Zkontrolovat znovu (Ctrl+F5)**.
   Aplikace vypíše, kolik chyb ubylo.

---

## Vyzkoušení po krocích

Aplikace vznikala v šesti krocích. U každého je popsáno, jak ho vyzkoušet.

### Krok 1: načtení a zobrazení DXF

```bat
python spustit.py ukazky\ukazkovy_vykres.dxf
```

* Kolečko myši plynule přibližuje, tažení levým nebo prostředním tlačítkem posouvá.
  **Home** zobrazí celý výkres.
* Vlevo je panel **Hladiny**, kde jde každou hladinu vypnout. Ve stavovém řádku jsou
  souřadnice kurzoru.
* Menu **Zobrazení → Světlé pozadí** přepíná černé a bílé pozadí.

### Krok 2: framework kontrol a základní kontroly

```bat
python -m kontrola zkontroluj ukazky\ukazkovy_vykres.dxf
python -m kontrola zkontroluj ukazky\ukazkovy_vykres.dxf --seznam-kontrol
python -m pytest -q tests\test_zakladni_kontroly.py
```

V aplikaci otevřete **Kontrola → Nastavení kontrol**. Tam jde nastavit toleranci, zapnout
nebo vypnout jednotlivé kontroly, změnit jejich závažnost a parametry.

### Krok 3: panel chyb s kroužky, popisky a filtry

Otevřete ukázkový výkres a stiskněte F5.

* Kroužek má na obrazovce stále stejnou velikost a barvu podle závažnosti: červená je chyba,
  oranžová varování, modrá info.
* Popisky se zapínají a vypínají přes **Popisky chyb (Ctrl+L)**.
* Filtr typů chyb: odškrtnutím se skryjí kroužky i řádky. Dvojklik nebo tlačítko
  **Jen tento typ** zobrazí jen jeden typ. Dál jde filtrovat podle závažnosti a hladiny.
* Kliknutí na kroužek vybere řádek v tabulce. Tabulka se řadí kliknutím na záhlaví sloupce.
* Tlačítka **✓ Opraveno** (Ctrl+Enter) a **✕ Ignorovat** (Ctrl+Delete) uloží stav chyby do
  projektu a přejdou na další nevyřešenou chybu. Vyřešený řádek je přeškrtnutý, kroužek ve
  výkresu dostane zelenou fajfku nebo šedý křížek. Karta nahoře ukazuje, kolik chyb zbývá.
  Pod tabulkou jde ke každé chybě napsat poznámku.
* Pole **Hledat** filtruje chyby podle textu (popis, hladina, číslo chyby).
* Chyba označená jako opravená, která se při opakované kontrole znovu objeví, se vrátí do stavu
  „nová“. Ignorované chyby zůstanou ignorované.

### Rozpracovaný výkres a kontrola jen části výkresu

* **Rozpracovaný výkres** (tlačítko v horní liště, menu Kontrola): výkres ještě není hotový,
  takže se nehlásí volné konce čar, neuzavřené plochy, mezery mezi plochami a chybějící popisy.
  Všechno, co už je nakreslené, se kontroluje dál (vrstvy, barvy, styly, texty, nedotažení,
  přetažení, duplicity, křížení, krátké čáry). Nastavení se pamatuje v projektu. **Před
  odevzdáním režim vypněte.**
* **Jen tento výřez**: přibližte si hotovou část výkresu a klikněte. Seznam, kroužky i počty
  chyb se omezí na zobrazenou oblast. Dalším kliknutím se vrátíte k celému výkresu.

### Připraveno k odevzdání, hlídání souboru, návody k opravě

* **Připraveno k odevzdání?** (horní lišta): úplná kontrola s tolerancemi učitele (i když máte
  zapnutý rozpracovaný výkres). Ukáže semafor (červená: chyby, oranžová: jen varování, zelená:
  hotovo), co zbývá opravit, kontrolní seznam (pravidla, seznam souřadnic, je DXF novější než
  DGN?), graf počtu chyb v čase a **počítadlo odevzdání** (nejvýš 5 pokusů).
* **Hlídat změny výkresu** (menu Kontrola, ve výchozím stavu zapnuto): kreslíte v MicroStationu,
  uložíte DXF a aplikace během pár vteřin sama načte výkres a zkontroluje ho znovu. Nad
  seznamem chyb ukáže, co přibylo a co zmizelo. Každé uložení DGN (Ctrl+S) to nespustí – je
  potřeba uložit DXF (u DGN jen s nainstalovaným ODA File Converterem).
* **Jak opravit:** u vybrané chyby se pod seznamem ukáže postup v MicroStationu (který nástroj,
  co nastavit). Návody jsou i v PDF protokolu a v Excelu.
* **Průběh:** malý graf pod kartami ukazuje počet chyb (červeně) a varování (oranžově)
  u posledních kontrol.

### Průvodce, vysvětlení chyb, porovnání verzí a další

* **Průvodce** se ukáže při prvním spuštění (a kdykoli v menu Nápověda → Průvodce): pět krátkých
  kroků od uložení DXF po odevzdání, s tlačítky, která rovnou otevřou správné místo.
* **? Co to znamená** (nad seznamem chyb, F1, pravé tlačítko na chybě): vysvětlení typu chyby
  s obrázkem „chyba / správně“ a postupem opravy v MicroStationu. Jsou tam i pojmy (uzel,
  tolerance, chyba × varování × info).
* **Rychlé filtry** nad seznamem: *Vše*, *K opravě* (bez informací), *Topologie* (co hlásí
  MGEO), *Atributy* (co hlásí GISoft).
* **Panel Prvek:** klik na čáru, bod, text nebo buňku ve výkresu ukáže její vlastnosti, co
  o ní říká Směrnice (✓/✗ u vrstvy, barvy, stylu, tloušťky, písma) a chyby u ní.
* **Kontrola → Porovnat verze výkresu** (Ctrl+D): co se změnilo od předchozí načtené verze
  (nebo proti jinému DXF) – přidané (zeleně), odebrané (červeně čárkovaně), upravené (oranžově)
  a prvky se změněnými atributy (fialově). Kliknutím na řádek se výkres přiblíží na změnu.
* **Soubor → Export → Seznam k opravě na tisk** (Ctrl+P): PDF se zbývajícími chybami
  seskupenými podle typu, s políčkem k odškrtnutí, návodem a výřezem výkresu.
* **Zobrazení → Tmavý režim** (volba se pamatuje).
* **Kontrola aktualizací:** hotový `.exe` se jednou denně podívá na GitHub, jestli není
  novější sestavení, a nabídne odkaz ke stažení. Zjišťuje se jen číslo poslední verze
  (veřejná stránka vydání), **nic se neodesílá** – žádné výkresy ani údaje o počítači.
  Vypnout: Nápověda → Hledat aktualizace při spuštění.

### Seznam souřadnic a kontrola výpočtu ze zápisníku

* **Kontrola → Ověřit seznam souřadnic… (Ctrl+J)**: vyberte seznam (`číslo Y X Z`) a aplikace porovná
  bod po bodu s výkresem – v pořádku / chybí / posunutý / špatné číslo / špatná výška / bod navíc.
  Kartičky s počty, tabulka, dvojklik přiblíží bod, barevné zvýraznění ve výkresu, export do CSV
  a tlačítko *Uložit seznam do projektu* (pak se porovná při každé kontrole).
* **Seznam souřadnic** (výstup z Gromy, `číslo Y X Z`) přetáhněte do okna nebo přidejte na
  Podklady. Kontrola pak najde body, které ve výkresu chybí nebo jsou posunuté, špatná čísla
  bodů a špatné výšky u bodů. Osy a znaménka S-JTSK se poznají samy.
* **Kontrola → Spojnice podle náčrtu…**: zapíšete, co je v náčrtu spojené (jeden řádek = jedna čára,
  např. `plot: 1-2-3-4`, `budova 10-11-12-13-10`), a aplikace podle seznamu souřadnic ověří, že každý úsek
  máte ve výkresu nakreslený – *nakresleno / chybí / jiná vrstva / nakresleno jinak (oblouk, lomená)*.
  Slovo před čísly (plot, budova…) se porovná s názvy pravidel a hlídá se i vrstva. Do výkresu se nic
  nevkládá, kreslíte sami. Zápis se uloží do projektu.
* **Kontrola → Kontrola výpočtu souřadnic (zápisník)…**: zadejte zápisník z totální stanice
  (formát Gromy `.zap`), dané body (stanoviska, orientace a nivelační bod – např.
  `gnss_husovice.txt` a body z ČÚZK, viz `podklady/zadani2-husovice/dane_body.txt`) a svůj
  seznam z Gromy. Aplikace spočítá polární metodu stejně jako Groma (dvě polohy dalekohledu,
  měřítkový koeficient Křovák + nadmořská výška, orientační posun vážený délkami, výšky od
  nivelačního bodu, druhé určení bodu jako kontrolní) a ukáže body, které se liší víc než
  o 1 cm. Na zadání Husovice souhlasí s Gromou do 1 mm.
* **Kontrola → Porovnat s protokolem učitele…**: načte protokol z GISoftu (`.log`) a porovná ho
  s nálezy aplikace po skupinách (vrstva + chybné atributy): co učitel našel a aplikace ne,
  a naopak. Protokol se uloží do Podkladů.

### Krok 4: záložka Zadání, import tabulky atributů

**Zadání → Tabulka atributů**: přetáhněte `ukazky/tabulka_atributu.xlsx` nebo `.csv`.
Průvodce ukáže náhled a odhadne řádek s hlavičkou i přiřazení sloupců. Obojí jde opravit.
Výsledná pravidla najdete na **Zadání → Pravidla**, kde je můžete upravit a uložit do YAML.

```bat
python -m pytest -q tests\test_import_projekt_export.py
```

### Krok 5: zbylé kontroly, vzorový výkres a podklady

* **Zadání → Vzorový výkres**: načtěte `ukazky/vzorovy_vykres.dxf` a pak použijte
  **Vytvořit pravidla ze vzoru** nebo **Porovnat s kontrolovaným výkresem**.
  Porovnání najde hladinu POKUS navíc a budovu s jinou barvou.
* **Zadání → Náčrt a fotky**: přidejte `ukazky/nacrt.png` a napište k němu poznámku.
  Tlačítko **Otevřít vedle výkresu (Ctrl+B)** zobrazí náčrt v panelu vedle výkresu. Panel jde
  odpojit do samostatného okna. Vpravo se nastavuje **podklad pod výkresem** (posun, měřítko,
  natočení, průhlednost).
* **Zadání → Podklady**: seznam všech souborů projektu s náhledem, datem, smazáním
  a nahrazením.
* **Soubor → Uložit projekt jako soubor .kontrola** uloží celý projekt do jednoho souboru.

```bat
python -m pytest -q tests\test_topologie.py tests\test_atributy.py
```

### Krok 6: exporty a sestavení .exe

**Soubor → Export**: seznam chyb do CSV nebo Excelu, protokol do PDF a DXF s hladinou
`KONTROLA_CHYBY`. Sestavení .exe popisuje oddíl [Sestavení .exe](#sestavení-exe).

---

## Zadání z předmětu (MicroStation, Směrnice-výběr.xls)

Ve složce [`podklady/zadani1-microstation/`](podklady/zadani1-microstation/) je zadání, učitelova
tabulka atributů `Směrnice-výběr.xls` a hotová pravidla
[`pravidla_zadani1.yaml`](podklady/zadani1-microstation/pravidla_zadani1.yaml). Pravidla obsahují
celou Směrnici a navíc vrstvy 58–60 (podrobné body, čísla a výšky bodů) podle zadání, přepočtené
pro měřítko 1:500.

Postup:

1. Výkres uložte z MicroStationu jako DXF vedle DGN (viz níže) a přetáhněte do aplikace.
2. **Zadání → Pravidla → Načíst YAML…** a vyberte `pravidla_zadani1.yaml`. Nebo přetáhněte
   přímo `Směrnice-výběr.xls` na *Tabulka atributů*, průvodce sloupce rozpozná sám.
3. **F5**. Kontrola dělá totéž co učitelova kontrola:
   * **Atributová kontrola (jako GISoft „Kontrola a změna symbologie“):**
     * vrstva podle čísla (VR 5 = „Vrstva 5“ / „Level 5“),
     * typ prvku MicroStationu (úsečka, lomená čára, elipsa, oblouk, text, buňka),
     * barva (číslo MicroStationu), styl (0, 2, 4, 7 nebo uživatelský 2.123…) a **měřítko stylu**
       (sloupec MĚŘÍTKO, např. 0,5 u plotů), u buněk měřítko buňky,
     * u textů font, výška, šířka a zarovnání,
     * **zákaz atributu „dle vrstvy“ (ByLevel)**.
   * **Topologická kontrola (jako MGEO) se stejnými tolerancemi:** začištění **0,010 m**
     (nedotažení), přetah / křížení **0,020 m**, krátká čára **0,090 m**. Hlásí duplicity,
     nedotažení a přetažení, **nerozdělené čáry při křížení**, krátké čáry a volné konce. Volné
     konce na okraji mapy a nerozdělené čáry v T-spojení se podle zadání nehlásí. Úsečky nulové
     délky na vrstvě bodů (58) jsou body, ne chyba.
   * Uživatelské styly se značkami (např. zábradlí 5.303) MicroStation do DXF někdy neuloží a čára
     je v DXF „Continuous“. Taková čára se hlásí jen jako **varování** („ověřte v DGN“). Že je styl
     nastavený, napoví měřítko stylu (0,5), které v DXF zůstane.
4. **Soubor → Export → Protokol jako MGEO / GISoft (.log)** vytvoří protokol ve stejné podobě,
   jakou vrací učitel: prvky seskupené podle atributů, chybný atribut označený „(!)“.

> Podle zadání se výkres opravený automatickou opravou neuzná. **Kontrola → Automatická oprava**
> slouží jen k tomu, abyste viděli, co je špatně. Chyby opravujte ručně v MicroStationu.

**Barvy a tloušťky:** školní tabulka barev je v [`podklady/color.tbl`](podklady/color.tbl) a je už
vložená v obou souborech pravidel. MicroStation při uložení do DXF převede každou barvu na
nejbližší barvu palety AutoCADu (ACI), např. barva 99 se uloží jako ACI 14. Aplikace dělá stejný
převod, takže barvy v DXF porovnává přesně (ověřeno na výkresech z obou zadání). Tloušťky
MicroStationu se v DXF ukládají v mm: 0 → 0 mm, 2 → 0,30 mm, 3 → 0,40 mm, 4 → 0,53 mm
(`mapa_tloustek` v pravidlech).

**Co ukázala kontrola `Vcelak_13_navic.dxf`:** kóty na vrstvě 63 nejsou ve Směrnici, proto se
hlásí jako nepovolená hladina (jedna chyba s počtem prvků) a do topologie se nepočítají.
Zábradlí má v DXF styl Continuous s měřítkem 0,5, styl 5.303 se tedy nejspíš jen neuložil do DXF
(varování, ověřte v DGN). Schody jsou kreslené bez přichycení (mezery a přesahy desetin
milimetru), proto nedotažení a přetažení. Délky pod 1 cm se vypisují v mm.

## Zadání 2 (účelová mapa Husovice, Atributy ÚM.xlsx)

Ve složce [`podklady/zadani2-husovice/`](podklady/zadani2-husovice/) jsou podklady a hotová pravidla
[`pravidla_zadani2.yaml`](podklady/zadani2-husovice/pravidla_zadani2.yaml), vytvořená z tabulky
`Atributy ÚM.xlsx` (115 pravidel, měřítko 1:200).

* **Kontrolujte `…_Kresba.dxf`.** Hlavní výkres je v něm připojený jako reference. Aplikace
  referenci (velký blok s kresbou na mnoha vrstvách) rozbalí a zkontroluje s kresbou dohromady.
  Buňky (značky) zůstanou buňkami.
* **3D výkres:** body mají výšky, takže některé čáry a oblouky leží v šikmé rovině. Aplikace je
  správně převede do půdorysu.
* **Tabulka se čte tak, jak je:** kódy ve sloupci bez nadpisu, alternativy „0|2.09–2.17|5.30“
  (styl 0 nebo uživatelské styly 2.09 až 2.17 nebo 5.30), rozsahy buněk „4.01–4.20“ (buňka se
  v DXF jmenuje např. `4.02_3`), barvy „6|0“ a tloušťky „0|1“, sloupce Tučně a Kurzíva.
  Výšky písma v mm na papíře se přepočtou měřítkem (`meritko: 200`). Při importu v aplikaci
  vyplňte v průvodci pole **Měřítko mapy 1:**.
* Opakované kódy (např. `6.xx2` pro dešťovou, splaškovou a jednotnou kanalizaci) dostanou
  k kódu název („6.xx2 Kanalizace dešťová“). Popis sítí „ve vrstvě a barvě dle sítě“ se hledá
  i na vrstvách sítí. Šrafy svahů a vstupy se do topologie nepočítají.

**Co ukázala kontrola `Husovice_Včelák_mapa_Kresba.dxf`** (8 nálezů):
zábradlí má v DXF styl Continuous (varování, ověřte v DGN), číslo popisné a orientační není tučné
(tabulka: tučně i kurzíva), 1 průsečík bez uzlu na hranici vozovky, 1 dvojice bodů 6 mm od sebe
(bod zaměřený dvakrát?) a 4 volné konce čar (varování, zkontrolujte).

## Převod DGN na DXF

Formát DGN z MicroStationu V8 (V8i, CONNECT) nejde číst žádnou volně dostupnou knihovnou.
Výkres proto uložte z MicroStationu jako **DXF**:

* **Jeden výkres:** *Soubor → Uložit jako…*, typ *AutoCAD Drawing Interchange (\*.dxf)*,
  v *Možnostech* jednotky v metrech.
* **Všechny výkresy najednou:** *Utilities → Batch Converter* (Dávkový převod). Přetáhněte
  do něj soubory `.dgn`, jako výstupní formát zvolte DXF a spusťte *Process*.

**Ukládejte DXF vedle DGN se stejným názvem.** Když pak do aplikace přetáhnete `vykres.dgn`,
aplikace sama použije `vykres.dxf`. Pokud je DXF starší než DGN, upozorní vás, že kontrolujete
starou verzi. Po opravě v MicroStationu stačí DXF uložit znovu a stisknout
**Zkontrolovat znovu**.

Automatický převod přes ODA File Converter se zkusí, jen pokud je nainstalovaný (cestu jde
zadat v Nastavení kontrol). Běžná verze ale DGN převádět nemusí.

Návod je i v menu **Nápověda → Jak převést DGN na DXF**.

---

## Kontroly

Každá kontrola je samostatná třída se společným rozhraním. Jde ji zapnout nebo vypnout,
nastavit jí závažnost (chyba / varování / info) a parametry. Všechny délky jsou v metrech.

Obecné nastavení:

* **Tolerance** (výchozí 0,010 m = tolerance začištění MGEO) je vzdálenost, do které se hlásí
  nedotažení a body téměř na sobě. Přetah / křížení (0,020 m) a krátká čára (0,090 m) se
  nastavují u příslušných kontrol. Projekty z dřívějších verzí se na tyto hodnoty převedou samy.
* **Přesnost** (výchozí 0,0001 m) je vzdálenost, pod kterou jsou dva body totožné.

### Topologie (shapely, prostorový index STRtree)

| Kontrola (id) | Co hlídá | Výchozí |
|---|---|---|
| Nezavřený polygon (`nezavrene_polygony`) | linie, která má být polygonem, ale není uzavřená; bez pravidla lomená čára s konci blíž než `max_mezera`. Příklad hlášení: „Nezavřený polygon, mezera 0,03 m“ | chyba |
| Visící konec linie (`visici_konce`) | konec linie, u kterého v toleranci není jiná linie (dangle) | varování |
| Chybějící napojení (`chybejici_napojeni`) | konec linie je od jiné linie blíž než tolerance, ale není napojen | chyba |
| Duplicitní prvek (`duplicity`) | stejná geometrie dvakrát (i s opačným směrem), dva body na stejném místě | chyba |
| Samoprotnutí (`samoprotnuti`) | linie nebo polygon protíná sám sebe | chyba |
| Průsečík bez uzlu (`pruseciky_bez_uzlu`) | křížení linií nebo T-napojení bez lomového bodu | chyba |
| Prvek nulové délky (`nulova_delka`) | nulová délka nebo plocha, prázdný text, nulový poloměr | chyba |
| Překryv polygonů (`prekryvy_polygonu`) | polygony na stejné hladině se překrývají | chyba |
| Mezera mezi polygony (`mezery_polygonu`) | úzká štěrbina nebo malá díra mezi polygony | varování |
| Prvek mimo rozsah (`mimo_rozsah`) | prvek mimo zadaný obdélník nebo mimo území ČR v S-JTSK | chyba |
| Body téměř na sobě (`body_blizko`) | dva body blíž než tolerance, ale ne totožné | varování |
| Prvky příliš blízko – Limit (`blizke_prvky`) | lomový bod čáry leží blíž než Limit (0,01 m) u jiné čáry, ale nedotýká se jí (jako Limit v MGEO) | varování |
| Kontrola ploch (`kontrola_ploch`) | z hraničních čar sestaví plochy (jako MGEO): plocha bez popisu / definičního bodu, více čísel v jedné ploše, stejné číslo ve dvou plochách. Vrstvy se poznají samy. | vypnuto |

Topologické kontroly mají parametr **Jen hladiny**, který kontrolu omezí na vybrané
hladiny (např. `PARCELY, PLOTY*`).

### Atributy a konvence (podle pravidel)

| Kontrola (id) | Co hlídá | Výchozí |
|---|---|---|
| Atributy prvku (`atributy`) | povinné atributy a povolené hodnoty (číselníky) | chyba |
| Hladina, barva nebo styl (`symbologie`) | hladina, barva, styl a tloušťka čáry podle kódu | varování |
| Nepovolená hladina (`nepovolene_hladiny`) | prvek na hladině, která v pravidlech není | chyba |
| Nekódovaný prvek (`nekodovane`) | prvku nejde přiřadit žádný kód | varování |
| Popis (text) prvku (`texty`) | chybějící popis a text mimo polygon, ke kterému patří | varování |
| Typ geometrie (`typ_geometrie`) | bod, linie, polygon nebo text jiný, než kód očekává | chyba |

Atributy se čtou z:

* atributů bloků (ATTRIB),
* XDATA (zápis `KLIC=hodnota` nebo dvojice klíč a hodnota),
* textu u prvku: pravidlo `text.atribut` říká, že popis uvnitř polygonu, případně nejbližší
  text v okruhu, se použije jako hodnota atributu.

**Jak se prvku přiřadí kód:**

1. atribut `KOD` (případně `CODE`, `KOD_PRVKU`…),
2. jinak název buňky (bloku),
3. jinak hladina. Když je na jedné hladině víc pravidel, rozhodne typ geometrie, barva
   a styl čáry.

---

## Zadání: tabulka atributů, náčrty, vzor, podklady

Všechny soubory se kopírují do **složky projektu** a zůstanou tam i po zavření aplikace:

```
Dokumenty\Kontrola výkresu\<projekt>\
  projekt.yaml         název, zdroj výkresu, poznámky, stavy chyb, podklad pod výkresem
  pravidla.yaml        pravidla kontrol
  nastaveni.yaml       nastavení kontrol
  chyby.json           výsledek poslední kontroly
  vykres\              kopie kontrolovaného výkresu
  podklady\tabulky\    tabulky od učitele
  podklady\obrazky\    náčrty a fotky
  podklady\vzor\       vzorový výkres
```

**Soubor → Uložit projekt jako soubor .kontrola** zabalí celou složku do jednoho souboru
(je to ZIP s příponou `.kontrola`). **Otevřít projekt** ho zase rozbalí.

### Tabulka atributů od učitele

Podporované formáty jsou `.xlsx`, `.csv` (středník nebo čárka, UTF-8 i Windows-1250) a `.pdf`.
PDF musí obsahovat tabulku jako text, skeny bez OCR číst nejde. Průvodce rozpozná tyto
hlavičky, na velikosti písmen a diakritice nezáleží:

| Pole | Příklady hlaviček |
|---|---|
| Kód | Kód, Code, Číslo prvku |
| Název | Název, Název prvku, Objekt |
| Hladina | Hladina, Level, Vrstva |
| Barva | Barva, Color (číslo, název „červená“ nebo `#RRGGBB`) |
| Styl čáry | Styl čáry, Typ čáry, Linetype (také „plná“, „čárkovaná“…) |
| Tloušťka | Tloušťka, Weight (mm) |
| Typ geometrie | Typ geometrie, Geometrie (bod / linie / plocha / text) |
| Povinné atributy | Povinné atributy, Atributy (oddělené čárkou) |
| Povolené hodnoty | Povolené hodnoty, Číselník (`lípa, dub` nebo `DRUH=lípa,dub; MATERIAL=zděná`) |
| Buňka / blok | Buňka, Blok, Cell, Značka |
| Popis na hladině | Popis na hladině, Hladina popisu |

Řádky s nadpisem skupiny (jediná vyplněná buňka) se přeskočí. Řádky bez kódu, s neplatným
nebo duplicitním kódem se vypíšou v souhrnu importu jako nezpracované.

### Náčrty a fotky

Podporované formáty jsou JPG, PNG, BMP, TIFF a PDF (vícestránkové PDF lze listovat).
Prohlížeč umí přibližovat, posouvat, otáčet a přepínat mezi obrázky. Ke každému obrázku jde
napsat poznámku a v editoru pravidel lze k pravidlu připojit obrázek. Obrázek může sloužit
i jako **podklad pod výkresem** s posunem, měřítkem, natočením a průhledností. Do kontrol
nevstupuje.

### Když máte od učitele jen PDF nebo náčrt (JPG)

Bez tabulky atributů a bez vzoru v DXF aplikace pořád zkontroluje:

* **všechnu topologii** (nezavřené polygony, napojení, průsečíky, duplicity…), ta pravidla nepotřebuje,
* **jednotnost hladin**: kontrola *Nejednotná symbologie hladiny* najde prvky, které mají jinou barvu,
  styl nebo tloušťku než většina prvků na stejné hladině.

Postup:

1. **Zadání → Vzorový výkres**: přetáhněte PDF nebo JPG od učitele.
2. **Vložit pod výkres…**: klikněte na bod v obrázku a na stejný bod ve výkresu, potom na druhý
   bod. Vzor se průhledně zobrazí pod výkresem ve správném měřítku a natočení. Vyberte výrazné
   body co nejdál od sebe, třeba rohy rámu nebo lomové body hranic.
3. U **PDF** (uloženého z MicroStationu, ne naskenovaného) použijte **Porovnat s kontrolovaným
   výkresem**. Vypíšou se čísla parcel, bodů a č.p., která ve vašem výkresu chybějí nebo přebývají.
4. **Vytvořit pravidla ze vzoru** nabídne návrh pravidel z vašeho vlastního výkresu. Projděte ho
   podle PDF nebo náčrtu (hladiny, barvy) a potvrďte. Kontroly pak hlídají, že se pravidel
   držíte v celém výkresu.

### Úvodní obrazovka, skóre, tipy a další nástroje

* **Úvod** (první záložka): čtyři kroky – zadání a pravidla → výkres → kontrola → odevzdání – s tím, co je
  hotové, naposledy otevřené výkresy a nástroje na jedno kliknutí.
* **Co aplikace umí** (Nápověda, odkaz na Úvodu): přehled všech funkcí po skupinách s vyhledáváním
  a tlačítkem *Spustit* u každé.
* **Skóre připravenosti** 0–100 (u karet chyb a na Úvodu): srážky za chyby topologie, atributů a varování.
  Je orientační, není to známka – 100 = nic k opravě.
* **Rychlé tipy – MicroStation** (Nápověda, Ctrl+T): rovnoběžka, kolmice z bodu i v bodě (AccuDraw),
  prodloužení, oříznutí, rozdělení v průsečíku, uzavření plochy, souřadnice z klávesnice (XY=, DX=, DL=),
  přichytávání, AccuDraw, změna a výběr atributů – s obrázky a vyhledáváním.
* **Interaktivní protokol (HTML)** (Soubor → Export): jeden soubor pro prohlížeč – přehledka výkresu
  s klikacími kroužky, filtr Vše / K opravě / Topologie / Atributy, hledání, návod a výřez u každé chyby.
* **Zkontrolovat více výkresů najednou** (Kontrola): souhrnná tabulka (chyby, varování, skóre,
  nejčastější chyba) a export do CSV.

### Kontrola výpočtu (Groma) – kontrola měření a diagnóza

Okno *Kontrola → Kontrola výpočtu souřadnic* má záložky:

* **Porovnání bodů** – vaše souřadnice proti výpočtu ze zápisníku,
* **Diagnóza – proč se liší** – pozná typické chyby: body pootočené kolem stanoviska (jiný orientační
  posun), rozdíl úměrný délce (měřítkový koeficient – i „zapomenutý“), stejný posun všech bodů
  (souřadnice stanoviska), stejný rozdíl výšek (výška stanoviska / přístroje) a prohozená čísla bodů,
* **Kontrola měření** – rozdíl I. a II. polohy (Hz, délka), indexová chyba z, opravy na orientacích
  (v cc i mm), měřená délka na orientaci proti délce ze souřadnic, kontrolní (druhé) určení bodu,
* **Mapa odchylek** – stanoviska a body, šipky = zvětšený rozdíl vašeho bodu,
* **Postup výpočtu** – koeficient, výšky stanovisek, orientační posuny.

### Kokeš, Atlas DMT, katastr (VFK), LibreOffice

* **VFK** (výměnný formát katastru, s daty pracuje např. Kokeš) jde otevřít jako výkres: body, hranice
  parcel, budovy, vnitřní kresba a čísla parcel (v souřadnicích jako výkres z MicroStationu).
* Kresbu z **Kokeše**, **Atlasu DMT** i **AutoCADu** exportujte do DXF (Nápověda → Kokeš, Atlas DMT…).
* Tabulky atributů lze nahrát i jako **.ods** (LibreOffice / OpenOffice Calc).
* Binární seznam souřadnic (Kokeš .ss, Groma .crd) aplikace pozná a poradí export do textu.

### Automatická oprava – co dělá a co ne

Oprava (Kontrola → Oprava) vytvoří **nový** DXF, originál nemění. Dotáhne nedotažené a zkrátí přetažené
čáry (do tolerance), smaže duplicity a nulové délky, uzavře téměř uzavřené plochy a rozdělí čáry
v křížení. Nově také: **rozdělí čáry v uzlu**, kde se kříží ve společném lomovém bodě (jako MGEO),
**odstraní zbytečné lomové body** (zdvojené a úseky kratší než min. délka), **přichytí lomový bod**,
který leží těsně (pod Limitem) u jiné čáry, **smaže zdvojené body** a volitelně **přesune prvky z vrstvy
mimo Směrnici** na vrstvu, kam podle barvy a typu patří. Uzly do **T-napojení** nevkládá (učitel je nevyžaduje) a **nevytvoří krátký úsek** – takové
místo vypíše k ruční opravě. Výkres s kresbou v referenci umí také. Ověřeno na výkresech obou zadání:
geometrie se posune nejvýš o toleranci (0,018 m). Podle zadání se automaticky opravený výkres
neuznává – slouží k tomu, abyste viděli, co opravit v MicroStationu.

### Chyby přímo v MicroStationu (makro)

Kontrola → **Propojení s MicroStationem**: aplikace uloží makro **KontrolaVykresu.bas** (VBA, V8i
i CONNECT) a po zapnutí **Posílat chyby do MicroStationu** zapisuje po každé kontrole vedle výkresu
`<název>_chyby.txt`. V MicroStationu makro (`vba run KV_Nacist`, na F6) ukáže chyby jako **dočasné
kroužky** – do DGN se neukládají a výkres nijak nemění – a `KV_Dalsi` / `KV_Predchozi` (F8 / F7)
přiblíží další chybu s textem ve stavovém řádku. Postup instalace je v okně. Makro jsem nemohl
vyzkoušet v MicroStationu – kdyby hlásilo chybu, pošlete její text.

### DGN přímo, bez převodu (experimentálně)

DGN z MicroStationu V8 / V8i / CONNECT aplikace přečte sama – vlastní čtečka formátu (OLE + zlib):
úsečky, lomené čáry, tvary, složené řetězce, oblouky a elipsy (2D i 3D), texty (obsah, výška, natočení,
zarovnání), buňky (název, poloha, natočení), body, názvy vrstev a **přesná symbologie z DGN** (číslo
barvy, tloušťka 0–31, styl, „dle vrstvy“). Na výkresu Husovice sedí s DXF exportem z MicroStationu počty
všech typů prvků, vrstvy, texty i souřadnice (99–100 % vrcholů do 2 cm, oblouky jsou lomené čáry).
Nečte se písmo textu (font) a název vlastního stylu čáry (je v knihovně stylů, ne v DGN) – ty se u DGN
nekontrolují. Když je vedle DGN novější stejnojmenný DXF, použije se DXF. S **Hlídat změny výkresu** pak
stačí v MicroStationu Ctrl+S.

### Časová osa výkresu (Ctrl+H)

Při každé kontrole změněného výkresu se do projektu uloží komprimovaná verze (posledních 60, max. 300 MB;
první verze zůstává). Okno **Časová osa** ukáže všechny verze (čas, počet prvků, změna, chyby, skóre –
červeně, kde chyby přibyly), náhled každé verze, **přehrání** vzniku výkresu, porovnání vybrané verze
s aktuálním výkresem, **vytažení smazaných prvků** do DXF (zkopírujete je zpět v MicroStationu) a uložení
libovolné verze.

### Učitelův pohled – předpověď protokolu

Při každém **Porovnat s protokolem učitele** se aplikace učí, které chyby učitel hlásí (podle kombinací
chybných atributů, společně pro všechny projekty). **Kontrola → Učitelův pohled** pak odhadne, co nahlásí
u aktuálního výkresu: skupiny, které hlásí jako program, skupiny, které (zatím) nehlásí, a upozornění, kde
učitel dřív našel víc než program. Záložka **Náhled protokolu** ukáže protokol ve formátu GISoft, jaký
dostanete od učitele. Bez porovnaného protokolu je odhad stejný jako výsledek kontroly.

### Kartografická kontrola a náhled tisku

Skupina **Kartografie** (rychlý filtr nad seznamem chyb): **popisy přes sebe** (podle velikosti písma,
pracovní drobné popisy se s tiskovými nesrovnávají), **popis přeškrtnutý čarou**, **číslo bodu daleko od
bodu** (vrstvy s čísly bodů se poznají samy) a **popis vzhůru nohama**. **Soubor → Export → Náhled tisku
v měřítku (PDF)**: mapa přesně v měřítku (1 mm = M/1000 m) na bílém papíře s tloušťkami čar jako na
tisku – vytiskněte na 100 %.

### Opravný průvodce pro MicroStation (Ctrl+G)

Kontrola → **Opravný průvodce**: chyby k opravě jedna po druhé, seřazené podle polohy (od levého horního
rohu vždy k nejbližší další – v MicroStationu se nepřeskakuje po mapě). U každé chyby je přesný postup
s čísly: který konec čáry, o kolik chybí nebo přečnívá, **souřadnice cíle** (lomový bod sousední čáry,
průsečík, bod ze seznamu) a **key-iny** ke zkopírování (`WINDOW CENTER;XY=…`, `XY=…` pro AccuDraw).
Tlačítka *Opraveno – další*, *Přeskočit*, *Ignorovat*; okno zůstává nahoře vedle MicroStationu.
**Opravný list (HTML)** dá všechny kroky na jednu stránku k vytištění. Opravujete ručně v DGN, takže
výkres zůstane váš.

### Porovnání s PDF od učitele (kresba)

Zadání → **Vzor**: PDF uložené z MicroStationu (vektorové, ne sken) → *Porovnat s kontrolovaným
výkresem*. Kromě popisů se teď porovná i **kresba**: PDF se samo umístí do souřadnic výkresu (popisy, které
jsou v PDF i ve výkresu jen jednou, dají shodné body; pak se umístění zpřesní přiložením čar), a ukáže
**čáry, které ve výkresu chybí** (červeně čárkovaně) a **čáry navíc** (modře). Dvojklik na řádek přiblíží
místo. Na zadání 1 najde schválně smazanou čáru s přesností pod 1 m; přesnost umístění (typicky 20–40 cm)
je v tabulce. Slouží jen ke kontrole – nic se nepřenáší.

### Když se něco pokazí

Neočekávaná chyba se zapíše do logu a ukáže okno s tlačítky *Kopírovat podrobnosti* a *Nahlásit chybu*
(otevře předvyplněnou stránku na GitHubu – nic se neodesílá samo). Složka s logem: Nápověda →
Nahlásit chybu / složka s logy. Projekt se ukládá bezpečně (nejdřív do dočasného souboru), takže se
při pádu nepoškodí.

### Pokyny ze zadání (Word)

Zadání od učitele ve Wordu (DOC i DOCX), ODT, RTF nebo PDF přetáhněte do záložky **Zadání** – otevře se
stránka **Pokyny ze zadání**. Aplikace z dokumentu vytáhne:

* **požadavky** – měřítko, písmo, výšku písma, tolerance, souřadnicový systém a věty s „musí / nesmí“;
* **popisy vrstev** („Vrstva 58 – podrobné body polohopisu … Barva 0, Tloušťka čáry 2“) a nabídne je
  přidat do pravidel. Výšky písma se přepočtou z měřítka, pro které platí, na měřítko kresby.
  Bez toho by se body na vrstvách 58/59/60 v zadání 1 hlásily jako „vrstva není ve Směrnici“,
  protože v Excelu se Směrnicí nejsou;
* **tabulky** s vrstvami a barvami, které jde importovat jako tabulku atributů;
* **hodnoty pro kontrolu** – měřítko kresby, písmo, tolerance a formát odevzdání porovnané s projektem
  (✓ / ⚠). Toleranci jde tlačítkem **Použít v nastavení** rovnou nastavit. Přesnost mapování (uxy, třída
  přesnosti) se za toleranci kresby nepovažuje. Funguje i s PDF, pokud obsahuje text (ne sken).

Nenalezené vrstvy a počet pokynů ukáže i okno *Připraveno k odevzdání?*. Odebráním dokumentu se
odeberou i pravidla, která z něj vznikla.

### Zadání a další dokumenty

Na záložce **Podklady → Přidat… → Zadání a dokumenty** (nebo přetažením souboru .doc, .docx do
okna) si k projektu uložíte zadání od učitele, pokyny a další dokumenty. Otevřou se dvojklikem
v programu, který je ve Windows má přiřazený. Aplikace z nich nic nečte, pravidla vznikají
z tabulky atributů.

### Vzorový výkres

Ze vzoru se načtou používané hladiny, barvy, styly čar, tloušťky a buňky.

* **Vytvořit pravidla ze vzoru** navrhne pravidlo pro každou hladinu a každou buňku.
  Vy vyberete, která převzít.
* **Porovnat s kontrolovaným výkresem** vypíše chybějící a přebývající hladiny a buňky
  a jiné barvy a styly.

---

## Pravidla a konfigurace v YAML

Okomentovaný příklad je v souboru [`ukazky/konfigurace.yaml`](ukazky/konfigurace.yaml).
Obsahuje nastavení všech kontrol i pravidla pro ukázkový výkres. Zkrácená ukázka:

```yaml
verze_nastaveni: 2
nastaveni:
  tolerance: 0.010
kontroly:
  visici_konce: {zapnuto: true, zavaznost: varování}
paleta: microstation     # čísla barev: microstation (výchozí) nebo autocad (ACI)
rozsah: sjtsk            # nebo {xmin: .., ymin: .., xmax: .., ymax: ..}
povolene_hladiny: [RAM]
pravidla:
  - kod: "402"
    nazev: Strom listnatý
    geometrie: bod
    hladina: VEGETACE
    blok: STROM_L
    povinne_atributy: [DRUH]
    povolene_hodnoty:
      DRUH: [lípa, dub, javor]
```

**Barvy:** čísla barev v pravidlech jsou ve výchozím stavu **čísla MicroStationu** (0 bílá,
1 modrá, 2 zelená, 3 červená, 4 žlutá, 5 purpurová, 6 oranžová, 7 azurová…). MicroStation při
uložení do DXF barvy přečísluje na AutoCAD (ACI), proto aplikace porovnává barvy podle RGB:

* barvy 0–15 zná z výchozí barevné tabulky MicroStationu,
* pro ostatní barvy (16–255) načtěte barevnou tabulku, kterou máte v MicroStationu
  (*Nastavení kontrol → Obecné → Načíst barevnou tabulku…*). Umí binární `*.tbl` nebo text
  s řádky `číslo r g b` či `číslo;#RRGGBB`. Bez tabulky se tyto barvy neověřují
  a kontrola to napíše do poznámky,
* v hlášení je barva prvku také jako číslo MicroStationu, např. „barva 2 (má být 3)“.

Pokud učitel uvádí čísla barev z AutoCADu, přepněte „Čísla barev v pravidlech“ na *AutoCAD (ACI)*.
Tloušťky MicroStationu (wt 0–31) se v DXF ověřit nedají. Uvádějte je v mm, nebo je nechte prázdné.

---

## Srovnání s MGEO

| MGEO | Kontrola výkresu |
|---|---|
| Kontrola a oprava čárové kresby: duplicitní linie | Duplicitní prvek |
| … nedotažené linie (začištění 0,010 m) | Nedotažená / přetažená linie (tolerance 0,010 m) |
| … přetažené linie (přetah / křížení 0,020 m) | Nedotažená / přetažená linie (max. přetažení 0,020 m) |
| … průsečíky linií, linie nerozdělené v uzlu | Průsečík bez uzlu (T-spojení se podle zadání nehlásí) |
| … volné konce | Visící konec linie |
| … krátké a bodové linie (0,090 m) | Krátká linie nebo úsek (0,090 m), Prvek nulové délky |
| … blízké body | Body téměř na sobě |
| Čtení DGN | Vlastní čtení DGN V8 (experimentálně) nebo DXF |
| Topologické čištění – Limit (vzdálenost prvků) | Prvky příliš blízko (Limit 0,01 m) |
| Kontrola ploch (hranice + definiční body) | Kontrola ploch: plocha bez popisu, více čísel, duplicitní čísla |
| Kontrola a oprava duplicitních prvků | Duplicitní prvek (i body, texty, buňky) |
| Kontrola a změna symbologie | Hladina, barva nebo styl; Nepovolená hladina; Nekódovaný prvek |
| Plocha má právě jeden definiční bod | Popis (text) prvku: chybí popis / více popisů v ploše / popis mimo plochu |
| Režim „oprava“ | **Kontrola → Automatická oprava** (do nového DXF) |
| Značky chyb ve výkresu | Kroužky s popisky; export DXF s hladinou `KONTROLA_CHYBY` |

**Automatická oprava** (Ctrl+R, z příkazové řádky `--oprav vystup.dxf`) uloží opravený výkres
vždy do nového souboru. Opraví:

* duplicity a linie nulové délky,
* nedotažené a přetažené linie do tolerance,
* chybějící uzly (lomené čáry dostanou nový vrchol, úsečky se rozdělí),
* čáry nerozdělené v uzlu (rozdělí se na dvě),
* zbytečné lomové body a lomové body těsně u jiné čáry (přichytí se),
* zdvojené body, prvky na vrstvě mimo Směrnici (volitelně),
* téměř uzavřené polygony,
* volitelně symbologii podle pravidel.

Co opravit nejde (plochy, překryvy, atributy), zůstane v seznamu k ruční opravě.

MGEO pracuje přímo nad výkresem DGN v MicroStationu. Tato aplikace kontroluje výkres uložený
jako DXF a opravy zapisuje do nového DXF, který se otevře zpět v MicroStationu.

---

## Výstupy

* **CSV** se středníkem a desetinnou čárkou, v českém Excelu se otevře správně.
* **Excel** má list *Chyby* s filtrem a barvami závažnosti a list *Souhrn*.
* **Protokol PDF** obsahuje souhrn podle typů kontrol, přehledku výkresu s kroužky, tabulku
  všech chyb a výřezy problémových míst.
* **DXF s hladinou `KONTROLA_CHYBY`** je kopie výkresu doplněná o kroužky a texty chyb.
  Po otevření v MicroStationu přesně vidíte, kde opravovat.

Pokud je zapnutý filtr, aplikace se zeptá, jestli exportovat jen zobrazené chyby.

---

## Příkazová řádka

```bat
python -m kontrola zkontroluj vykres.dxf --pravidla ukazky\konfigurace.yaml ^
       --csv chyby.csv --xlsx chyby.xlsx --pdf protokol.pdf --dxf kontrola.dxf
python -m kontrola zkontroluj vykres.dxf --tolerance 0.02 --jen nezavrene_polygony duplicity
```

Návratový kód je 1, pokud výkres obsahuje chyby, jinak 0. Hodí se to například pro dávkovou
kontrolu více výkresů.

---

## Sestavení .exe

Na Windows s Pythonem 3.11 nebo novějším spusťte:

```bat
sestavit_exe.bat
```

Skript vytvoří virtuální prostředí, nainstaluje knihovny, spustí testy a pomocí PyInstalleru
sestaví jeden soubor **`dist\KontrolaVykresu.exe`**. Konfigurace je v
`kontrola_vykresu.spec`.

Stejné sestavení běží automaticky na GitHubu (`.github/workflows/build.yml`). Hotové .exe
je ke stažení jako artefakt v záložce Actions.

---

## Pro vývojáře: struktura a přidání kontroly

```
kontrola/
  model.py            prvek (Feature), výkres (Drawing), typ geometrie
  io/                 načítání: dxf_loader.py (ezdxf), dgn.py (ODA File Converter)
  checks/             kontroly: base.py (rozhraní Check, Issue, CheckContext),
                      topology.py, attributes.py
  rules.py            pravidla (číselník) a jejich YAML
  config.py           nastavení kontrol a jeho YAML
  runner.py           spuštění kontrol, porovnání, přenos stavů chyb
  importer/           tabulka atributů (table.py), vzorový výkres (template.py)
  project.py          složka projektu, soubor .kontrola
  export/             CSV/Excel, PDF protokol, DXF s KONTROLA_CHYBY
  ui/                 PySide6: hlavní okno, zobrazení výkresu, panel chyb, Zadání…
tests/                jednotkové testy (malá testovací DXF se tvoří přímo v testech)
ukazky/               ukázková data
```

**Nová kontrola** je třída v `kontrola/checks/`:

```python
from kontrola.checks.base import Check, Param, Severity, register

@register
class DlouhaLinie(Check):
    id = "dlouha_linie"
    nazev = "Příliš dlouhá linie"
    skupina = "Topologie"
    popis = "Linie delší než zadaný limit."
    vychozi_zavaznost = Severity.INFO
    parametry = [Param("limit", "Max. délka [m]", "float", 500.0)]

    def run(self, ctx):
        limit = ctx.param("limit", 500.0)
        for f in ctx.linear():
            if f.geometry.length > limit:
                yield ctx.issue(self, f, f"Linie je dlouhá {f.geometry.length:.0f} m")
```

Kontrola se sama objeví v nastavení, ve filtru i v exportech. Stačí modul naimportovat
v `kontrola/checks/__init__.py`.

**Testy:**

```bat
pip install -r requirements-dev.txt
python -m pytest -q
```

Výkon (orientačně, notebook): výkres se 120 000 prvky se načte asi za 13 s a všechny
kontroly doběhnou asi za 23 s. Načítání i kontroly běží ve vlákně na pozadí s ukazatelem
průběhu a jdou zrušit.

---

## Známá omezení

* DGN V8 se čte vlastní čtečkou experimentálně (bez písma textů a názvů vlastních stylů čar);
  starší DGN V7 jen přes DXF z MicroStationu nebo ODA File Converter.
* Oblouky a kružnice se pro kontroly nahrazují lomenou čarou s odchylkou 5 mm.
  Souřadnice Z se ignorují.
* Kružnice (CIRCLE) se považuje za bodový prvek (značku) se středem v kružnici.
* Barevná tabulka MicroStationu je vestavěná jen pro barvy 0–15. Pro ostatní barvy je potřeba
  načíst vlastní `color.tbl`.
* Starý formát Excelu `.xls` není podporován, uložte tabulku jako `.xlsx`. Skenované PDF bez
  textové vrstvy nejde přečíst.
* Kontroly jsou předkontrola. Nenahrazují kontrolu učitele ani oficiální nástroje (MGEO,
  kontroly VFK apod.).
