# Rychlé otestování (cca 10 minut)

1. Stáhni [KontrolaVykresu.exe](https://github.com/stepanvcelak11/kontrola-vykresu/releases/latest/download/KontrolaVykresu.exe)
   a ukázková data ([celý repozitář jako ZIP](https://github.com/stepanvcelak11/kontrola-vykresu/archive/refs/heads/main.zip),
   složka `ukazky/`).
2. Spusť `KontrolaVykresu.exe`. Windows může varovat „Neznámý vydavatel“ → *Další informace →
   Přesto spustit* (program není podepsaný).
3. Přetáhni do okna `ukazky/ukazkovy_vykres.dxf` → zobrazí se výkres.
4. **F5** → vpravo seznam problémů, ve výkresu kroužky. Klikni na řádek → výkres se přiblíží.
   Zkus filtr (odškrtnout typ chyby), hledání, **F7/F8**, *Opraveno* / *Ignorovat*.
5. **Zadání → Vzorový výkres** → přetáhni `ukazky/vzor_ucitele.pdf` → *Porovnat s kontrolovaným
   výkresem* (vypíše popisy navíc) → *Vložit pod výkres…* a klikni 2× bod v PDF + stejný bod ve výkresu.
6. **Kontrola → Automatická oprava** (Ctrl+R) → uloží `…_opraveno.dxf`, otevře ho a zkontroluje.
7. **Soubor → Export → Protokol do PDF**.
8. Pak totéž s vlastním výkresem: v MicroStationu *Soubor → Uložit jako → DXF*. Náčrt (JPG)
   přetáhni na *Zadání → Náčrt a fotky* nebo na *Vzorový výkres* a vlož pod výkres.

## Co mi poslat zpátky

* co nefungovalo nebo spadlo (ideálně snímek obrazovky),
* PDF / náčrt od učitele a svůj DXF – podle nich doladím kontroly.
