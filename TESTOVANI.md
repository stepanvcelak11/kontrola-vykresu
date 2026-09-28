# Rychlé otestování (cca 10 minut)

1. Stáhni `KontrolaVykresu.exe`: na GitHubu **Actions → poslední běh „Testy a sestavení .exe“ →
   Artifacts → KontrolaVykresu-windows** (ZIP, uvnitř je .exe). Ukázková data jsou ve složce
   `ukazky/` v repozitáři (tlačítko *Code → Download ZIP*).
2. Spusť `KontrolaVykresu.exe`. Windows může varovat „Neznámý vydavatel“ → *Další informace →
   Přesto spustit* (program není podepsaný).
3. Přetáhni do okna `ukazky/ukazkovy_vykres.dxf` → zobrazí se výkres.
4. Záložka **Zadání → Tabulka atributů** → přetáhni `ukazky/tabulka_atributu.xlsx` → *Vytvořit
   pravidla* (má vzniknout 10 pravidel, 1 řádek nezpracovaný).
5. **F5** → vpravo ~36 problémů, ve výkresu kroužky. Klikni na řádek → výkres se přiblíží.
6. Zkus filtr (odškrtnout typ chyby), **F7/F8**, *Opraveno* / *Ignorovat*.
7. **Soubor → Export → Protokol do PDF** → otevři PDF.
8. Pak totéž s vlastním výkresem: v MicroStationu *Soubor → Uložit jako → DXF*.

## Co mi poslat zpátky

* co nefungovalo nebo spadlo (ideálně snímek obrazovky),
* skutečnou tabulku atributů od učitele a případně vzorový výkres – podle nich doladím import,
* jestli jsou čísla barev v tabulce z MicroStationu nebo z AutoCADu.
