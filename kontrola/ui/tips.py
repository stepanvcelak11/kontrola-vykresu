"""Rychlé tipy: jak v MicroStationu udělat běžné konstrukce (rovnoběžka, kolmice, prodloužení…)."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import QByteArray, QRectF, Qt, QUrl
from PySide6.QtGui import QPainter, QPixmap, QTextDocument
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
                               QTextBrowser, QVBoxLayout)

_L = 'stroke="#374151" stroke-width="3" fill="none" stroke-linecap="round"'
_N = 'stroke="#2563EB" stroke-width="3" fill="none" stroke-linecap="round"'
_D = 'stroke="#9CA3AF" stroke-width="1.5" fill="none" stroke-dasharray="5 4"'
_T = 'font-family="Segoe UI, Arial" font-size="12" fill="#6B7280"'
_P = 'fill="#DC2626"'


def _dot(x, y, label=""):
    t = f'<text x="{x + 7}" y="{y - 6}" {_T}>{label}</text>' if label else ""
    return f'<circle cx="{x}" cy="{y}" r="4.5" {_P}/>{t}'


_SVG = {
    "vrchol": f'<polyline points="20,95 90,30 170,80 240,40" {_L}/><polyline points="90,30 110,70 170,80" {_N}/>'
              f'{_dot(110, 70, "nová poloha vrcholu")}',
    "zaobleni": f'<polyline points="30,20 30,70" {_L}/><polyline points="80,100 230,100" {_L}/>'
                f'<path d="M30 70 Q30 100 80 100" {_N}/><text x="60" y="65" {_T}>poloměr</text>',
    "deleni": f'<line x1="20" y1="60" x2="240" y2="60" {_L}/>{_dot(20, 60)}{_dot(75, 60)}{_dot(130, 60)}'
              f'{_dot(185, 60)}{_dot(240, 60)}<text x="95" y="90" {_T}>4 stejné díly</text>',
    "kruznice": f'<circle cx="130" cy="62" r="45" {_N}/>{_dot(85, 62, "1")}{_dot(130, 17, "2")}{_dot(175, 62, "3")}',
    "retez": f'<polyline points="20,90 80,40 150,70" {_N}/><polyline points="150,70 230,30" {_N}/>'
             f'<text x="60" y="110" {_T}>dvě čáry → jeden řetězec</text>',
    "rovnobezka": f'<line x1="20" y1="85" x2="240" y2="55" {_L}/><line x1="20" y1="45" x2="240" y2="15" {_N}/>'
                  f'<line x1="130" y1="70" x2="125" y2="31" {_D}/><text x="135" y="55" {_T}>vzdálenost</text>',
    "kolmice_z_bodu": f'<line x1="20" y1="95" x2="240" y2="95" {_L}/>{_dot(150, 25, "bod")}'
                      f'<line x1="150" y1="25" x2="150" y2="95" {_N}/>'
                      f'<polyline points="150,83 162,83 162,95" stroke="#2563EB" stroke-width="1.5" fill="none"/>',
    "kolmice_v_bode": f'<line x1="20" y1="95" x2="240" y2="95" {_L}/>{_dot(110, 95, "bod na čáře")}'
                      f'<line x1="110" y1="95" x2="110" y2="20" {_N}/>'
                      f'<polyline points="110,83 122,83 122,95" stroke="#2563EB" stroke-width="1.5" fill="none"/>',
    "prodlouzit": f'<line x1="200" y1="10" x2="200" y2="110" {_L}/><line x1="30" y1="60" x2="140" y2="60" {_L}/>'
                  f'<line x1="140" y1="60" x2="200" y2="60" {_N}/>{_dot(200, 60, "průsečík")}',
    "oriznout": f'<line x1="150" y1="10" x2="150" y2="110" {_L}/><line x1="30" y1="60" x2="150" y2="60" {_L}/>'
                f'<line x1="150" y1="60" x2="220" y2="60" {_D}/><text x="165" y="52" {_T}>smazat</text>',
    "rozdelit": f'<line x1="20" y1="60" x2="125" y2="60" {_L}/><line x1="135" y1="60" x2="240" y2="60" {_N}/>'
                f'<line x1="130" y1="15" x2="130" y2="105" {_L}/>{_dot(130, 60, "uzel")}',
    "uzavrit": f'<polyline points="40,95 40,25 200,25 200,95 40,95" {_N}/>{_dot(40, 95, "první = poslední bod")}',
    "souradnice": f'<line x1="30" y1="100" x2="230" y2="100" stroke="#9CA3AF"/><line x1="30" y1="100" x2="30" '
                  f'y2="10" stroke="#9CA3AF"/>{_dot(170, 40, "XY=-743140,-1043512")}',
}

# (kategorie, název, klíčová slova, obsah HTML, obrázek)
TIPS: list[tuple[str, str, str, str, str | None]] = [
    ("Konstrukce", "Rovnoběžka v dané vzdálenosti", "rovnobezka paralela odsazeni offset copy parallel",
     "<ol><li>Nástroj <b>Posunout/Kopírovat rovnoběžně</b> (Move/Copy Parallel).</li>"
     "<li>V nastavení nástroje zaškrtněte <b>Vytvořit kopii</b> (Make Copy) a <b>Vzdálenost</b> (Distance) "
     "– zadejte vzdálenost v metrech.</li>"
     "<li>Klikněte na čáru a pak na stranu, kam má rovnoběžka být. Potvrďte.</li></ol>"
     "<p>Tip: ploty a zdi „vlastnictví z jedné strany“ – strana značky se řídí směrem kreslení čáry.</p>",
     "rovnobezka"),
    ("Konstrukce", "Kolmice z bodu na čáru", "kolmice kolmo perpendicular pata",
     "<ol><li>Nástroj <b>Umístit úsečku</b> (Place Line).</li>"
     "<li>První bod: přichyťte se na bod (Tentative = obě tlačítka myši / prostřední, pak Accept).</li>"
     "<li>V liště přichytávání (Snap) zvolte <b>Kolmo</b> (Perpendicular).</li>"
     "<li>Najeďte na čáru, dejte Tentative – kurzor skočí do paty kolmice – a potvrďte (Accept).</li></ol>",
     "kolmice_z_bodu"),
    ("Konstrukce", "Kolmice v bodě na čáře (AccuDraw)", "kolmice accudraw re rotate element",
     "<ol><li>Zapněte <b>AccuDraw</b> (ikona na hlavní liště, klávesa F11 dá AccuDraw fokus).</li>"
     "<li>Nástroj <b>Umístit úsečku</b>; první bod přichyťte na čáru (Keypoint / Nearest).</li>"
     "<li>Stiskněte <b>R</b> a <b>E</b> (Rotate to Element) a klikněte na čáru – osy AccuDraw se natočí podle ní.</li>"
     "<li>Táhněte kolmo (osa Y) – <b>Enter</b> zamkne směr – zadejte délku a potvrďte.</li></ol>",
     "kolmice_v_bode"),
    ("Úpravy", "Prodloužit čáru k jiné čáře", "prodlouzit extend intersection nedotazeni",
     "<ol><li>Nástroj <b>Prodloužit prvek k průsečíku</b> (Extend Element to Intersection).</li>"
     "<li>Klikněte na čáru, kterou prodlužujete (blíž ke konci, který se má prodloužit), pak na cílovou čáru.</li>"
     "<li>Potvrďte. Konec leží přesně na cílové čáře – odstraní „nedotažení“.</li></ol>",
     "prodlouzit"),
    ("Úpravy", "Zkrátit (oříznout) přetaženou čáru", "oriznout trim pretazeni intellitrim",
     "<ol><li>Nástroj <b>Oříznout</b> (Trim Element / Trim to Intersection, případně IntelliTrim).</li>"
     "<li>Nejdřív vyberte řeznou čáru (hranu), pak klikněte na část, která se má odříznout.</li></ol>"
     "<p>Opravuje „přetažení“ (konec čáry přečnívá přes jinou čáru).</p>", "oriznout"),
    ("Úpravy", "Rozdělit čáru v průsečíku (uzel)", "rozdelit break partial delete uzel krizeni",
     "<ol><li>Nástroj <b>Rozdělit prvek</b> (Break Element) – ve starších verzích <b>Částečné smazání</b> "
     "(Partial Delete) s nulovou délkou.</li>"
     "<li>Klikněte na čáru v místě průsečíku s přichycením <b>Průsečík</b> (Intersection).</li></ol>"
     "<p>Opravuje „průsečík bez uzlu“. T-napojení (čára končí na jiné) učitel rozdělit nechce.</p>", "rozdelit"),
    ("Úpravy", "Uzavřít plochu (budovu)", "uzavrit shape complex tvar polygon budova",
     "<ul><li>Novou plochu kreslete nástrojem <b>Umístit tvar</b> (Place Shape) a poslední bod přichyťte na "
     "první – tvar se uzavře sám.</li>"
     "<li>Z existujících čar: <b>Vytvořit složený tvar</b> (Create Complex Shape) – klikejte čáry po obvodu.</li>"
     "</ul>", "uzavrit"),
    ("Zadávání", "Bod na přesných souřadnicích", "souradnice xy key-in klavesnice bod",
     "<p>V okně <b>Key-in</b> (Nástroje → Key-in) napište během nástroje:</p>"
     "<ul><li><code>XY=Y,X</code> – absolutní souřadnice (S-JTSK v MicroStationu záporně, např. "
     "<code>XY=-743140.00,-1043512.00</code>),</li>"
     "<li><code>DX=dx,dy</code> – posun od posledního bodu,</li>"
     "<li><code>DL=délka,úhel</code> – délka a směr od posledního bodu.</li></ul>", "souradnice"),
    ("Zadávání", "Přichytávání (Snap) a Tentative", "snap prichyceni keypoint nearest intersection tentative",
     "<ul><li><b>Tentative</b> (dočasný bod) = obě tlačítka myši najednou (nebo prostřední) – kurzor skočí na "
     "přichycený bod; <b>Accept</b> = levé tlačítko.</li>"
     "<li>Režimy: <b>Keypoint</b> (vrcholy), <b>Nearest</b> (nejbližší místo na čáře), <b>Intersection</b> "
     "(průsečík), <b>Perpendicular</b> (kolmo), <b>Center</b> (střed kružnice).</li>"
     "<li>Bez přichycení vznikají nedotažení v řádu milimetrů – nejčastější topologická chyba.</li></ul>", None),
    ("Zadávání", "AccuDraw – nejpoužívanější klávesy", "accudraw klavesy zkratky",
     "<ul><li><b>Enter</b> – zamknout směr (smart lock), <b>X / Y</b> – zamknout osu,</li>"
     "<li><b>Mezerník</b> – přepnout pravoúhlé / polární souřadnice,</li>"
     "<li><b>O</b> – přesunout počátek AccuDraw, <b>T</b> – natočit podle výkresu (Top), "
     "<b>RE</b> – natočit podle prvku, <b>RQ</b> – rychlé natočení,</li>"
     "<li>Délku stačí napsat číslem, když AccuDraw „vede“ kurzor.</li></ul>", None),
    ("Atributy", "Změnit vrstvu, barvu, styl prvku", "zmenit atributy vrstva barva styl tloustka change",
     "<ol><li>Nástroj <b>Změnit atributy prvku</b> (Change Element Attributes).</li>"
     "<li>Zaškrtněte jen to, co měníte (Vrstva, Barva, Styl, Tloušťka) a nastavte hodnoty ze Směrnice.</li>"
     "<li>Klikněte na prvky (nebo je nejdřív vyberte a pak jednou klikněte do výkresu).</li></ol>", None),
    ("Atributy", "Shodné atributy podle jiného prvku", "shodne match atributy",
     "<p>Nástroj <b>Shodné atributy prvku</b> (Match Element Attributes): klikněte na správný prvek – "
     "převezme se jeho vrstva, barva, styl a tloušťka jako aktivní – a pak nástrojem Změnit atributy "
     "klikejte na prvky, které mají být stejné.</p>", None),
    ("Atributy", "Vybrat všechny prvky jedné vrstvy", "vyber podle atributu select by attributes vrstva level",
     "<ul><li><b>Výběr podle atributů</b> (Edit → Select By Attributes): zvolte vrstvu (Level), typ prvku, "
     "barvu… a Execute.</li>"
     "<li>Nebo <b>Správce vrstev</b> (Level Manager) → pravým tlačítkem na vrstvu → vybrat prvky.</li>"
     "<li>Vybrané prvky pak jedním krokem přesunete: Změnit atributy → Vrstva.</li></ul>", None),
    ("Konstrukce", "Rozdělit úsečku na stejné díly", "deleni body mezi divide construct points between",
     "<ol><li>Nástroj <b>Vytvořit body mezi</b> (Construct Points Between) – zadejte počet bodů.</li>"
     "<li>Klikněte na začátek a konec (s přichycením) – body se rozmístí rovnoměrně.</li></ol>"
     "<p>Pro body na prvku: <b>Vytvořit body podél prvku</b> (Construct Points Along Element).</p>", "deleni"),
    ("Konstrukce", "Kružnice / oblouk třemi body", "kruznice oblouk arc circle tri body",
     "<p>Nástroj <b>Umístit kružnici</b> (Place Circle) nebo <b>Umístit oblouk</b> (Place Arc) s metodou "
     "<b>Hrana</b> (Edge) – klikněte tři body na obvodu (s přichycením na body měření).</p>", "kruznice"),
    ("Konstrukce", "Bod v průsečíku dvou čar", "prusecik bod intersection construct",
     "<ol><li>Nástroj <b>Vytvořit bod v průsečíku</b> (Construct Point at Intersection).</li>"
     "<li>Klikněte na obě čáry – bod vznikne přesně v průsečíku (i v jejich prodloužení).</li></ol>", None),
    ("Konstrukce", "Úsečka o dané délce a směru", "delka smer uhel dl accudraw",
     "<ul><li>S AccuDraw: první bod, pak napište délku, <b>Enter</b> zamkne, mezerníkem přepnete na úhel.</li>"
     "<li>Bez AccuDraw: key-in <code>DL=12.5,90</code> (délka, úhel ve stupních od osy X).</li></ul>", None),
    ("Úpravy", "Posunout vrchol / vložit či smazat vrchol", "vrchol modify vertex insert delete",
     "<ul><li><b>Upravit prvek</b> (Modify Element): klikněte blízko vrcholu a přesuňte ho (s přichycením).</li>"
     "<li><b>Vložit vrchol</b> (Insert Vertex) / <b>Smazat vrchol</b> (Delete Vertex) – klik na místo "
     "na čáře.</li></ul><p>Tip: přebytečný vrchol těsně u jiného dělá „krátkou čáru“ – smažte ho.</p>",
     "vrchol"),
    ("Úpravy", "Spojit čáry do jedné (řetězec)", "spojit retez complex chain join",
     "<p><b>Vytvořit složený řetězec</b> (Create Complex Chain): klikejte navazující čáry – vznikne jeden "
     "prvek. Obráceně: <b>Rozložit</b> (Drop Element) rozdělí řetězec / tvar zpět na čáry.</p>", "retez"),
    ("Úpravy", "Zaoblení a zkosení rohu", "zaobleni fillet zkoseni chamfer roh",
     "<p><b>Zaoblit prvky</b> (Construct Circular Fillet) – zadejte poloměr a klikněte obě čáry; "
     "<b>Zkosit</b> (Construct Chamfer) – zadejte vzdálenosti.</p>", "zaobleni"),
    ("Úpravy", "Kopírovat / posunout o přesnou vzdálenost", "kopie posun move copy dx",
     "<ol><li><b>Kopírovat</b> (Copy) nebo <b>Posunout</b> (Move), klik na prvek, bod odkud.</li>"
     "<li>Kam: key-in <code>DX=dx,dy</code> nebo délka v AccuDraw.</li></ol>", None),
    ("Úpravy", "Vrátit krok zpět", "zpet undo ctrl z redo",
     "<p><b>Ctrl+Z</b> = zpět, <b>Ctrl+Y</b> = znovu. Pozor: po <b>Komprimovat výkres</b> se historie "
     "kroků smaže.</p>", None),
    ("Text a buňky", "Umístit a upravit text", "text popis umistit upravit edit",
     "<ul><li><b>Umístit text</b> (Place Text) – v nastavení zvolte písmo, výšku, šířku a zarovnání podle "
     "Směrnice, pak napište text a klikněte do výkresu.</li>"
     "<li><b>Upravit text</b> (Edit Text) – klik na text.</li>"
     "<li>Výška/šířka se zadává v jednotkách výkresu (m); ve Směrnici bývá v mm na papíře – přepočtěte "
     "měřítkem (1,5 mm při 1:500 = 0,75 m).</li></ul>", None),
    ("Text a buňky", "Popis natočený podél čáry", "text natoceni rotace podel",
     "<p>V nástroji Umístit text zvolte metodu <b>Nad prvkem / Podél prvku</b> (Above/Along Element) a "
     "klikněte na čáru, nebo text po umístění natočte nástrojem <b>Otočit</b> (Rotate) s AccuDraw "
     "(<b>RE</b> = podle prvku).</p>", None),
    ("Text a buňky", "Vložit značku (buňku)", "bunka cell znacka knihovna",
     "<ol><li><b>Prvek → Buňky</b> (Element → Cells) – připojte knihovnu buněk ze zadání (např. .cel).</li>"
     "<li>Vyberte buňku, tlačítko <b>Umístit</b> (Placement), nastavte měřítko a natočení podle "
     "Směrnice.</li><li>Nástroj <b>Umístit aktivní buňku</b> (Place Active Cell) – klik do výkresu.</li></ol>",
     None),
    ("Text a buňky", "Šrafa (svah, plocha)", "srafa hatch pattern svah",
     "<p><b>Šrafovat plochu</b> (Hatch Area) nebo <b>Vzorkovat</b> (Pattern Area): zvolte rozestup a úhel, "
     "metodu <b>Prvek</b> nebo <b>Zaplavit</b> (Flood) a klikněte dovnitř uzavřené plochy.</p>", None),
    ("Zobrazení", "Vypnout / zapnout vrstvy", "vrstvy zobrazeni level display vypnout",
     "<p><b>Nastavení → Zobrazení vrstev</b> (Level Display, Ctrl+E): klikem vrstvu vypnete/zapnete. "
     "Hodí se k hledání prvků na špatné vrstvě – vypněte vše kromě jedné.</p>", None),
    ("Zobrazení", "Najít místo chyby z této aplikace", "najit misto chyba window center",
     "<p>U chyby klikněte na <b>Najít v MicroStationu</b> – do schránky se uloží příkaz. V MicroStationu "
     "otevřete Key-in, vložte (Ctrl+V) a Enter – pohled se vycentruje na chybu.</p>", None),
    ("Zobrazení", "Přiblížit na celý výkres / okno", "zoom fit prizpusobit okno",
     "<p><b>Přizpůsobit pohled</b> (Fit View) – celý výkres; <b>Okno oblasti</b> (Window Area) – "
     "přiblížení výřezu; kolečko myši přibližuje ke kurzoru.</p>", None),
    ("Podklady", "Připojit referenci / rastr (náčrt, ortofoto)", "reference raster pripojit ortofoto",
     "<p><b>Soubor → Reference</b> (References) → Připojit – jiný výkres jako podklad. "
     "<b>Soubor → Správce rastrů</b> (Raster Manager) – obrázek (náčrt, ortofoto) umístíte dvěma body. "
     "Před odevzdáním reference odpojte, pokud je zadání nechce.</p>", None),
    ("Podklady", "Import bodů z Gromy do výkresu", "groma import body seznam",
     "<p>V Gromě: <b>Export do MicroStationu</b> / import seznamu souřadnic přes nadstavbu – zkontrolujte, "
     "na jaké vrstvy se body, čísla a výšky ukládají (musí sedět se Směrnicí / Wordem se zadáním).</p>", None),
    ("Odevzdání", "Komprimovat výkres a uložit", "komprimovat compress ulozit odevzdat",
     "<ol><li><b>Soubor → Komprimovat → Výkres</b> (Compress Design) – odstraní smazané prvky.</li>"
     "<li><b>Soubor → Uložit</b>, pak uložte i DXF pro kontrolu v této aplikaci.</li>"
     "<li>Název souboru podle zadání (např. Prijmeni_cz_ax_tx.dgn).</li></ol>", None),
    ("Odevzdání", "Tisk do PDF", "tisk pdf print plot",
     "<p><b>Soubor → Tisk</b> (Print): tiskárna <b>PDF</b>, oblast <b>Ohrada</b> (Fence) nebo pohled, "
     "měřítko podle zadání (např. 1:500), pero/tabulka tlouštěk podle školy.</p>", None),
    ("Kontrola", "Změřit vzdálenost / plochu", "merit vzdalenost plocha measure",
     "<p><b>Měřit vzdálenost</b> (Measure Distance) – mezi body, podél prvku nebo kolmo na prvek. "
     "<b>Měřit plochu</b> (Measure Area) – klik dovnitř plochy nebo na tvar.</p>", None),
    ("Kontrola", "Uložit DXF pro kontrolu", "dxf ulozit export save as",
     "<ol><li><b>Soubor → Uložit jako</b> (Save As), typ <b>DXF</b>.</li>"
     "<li>Uložte vedle DGN se stejným názvem – aplikace si změn všimne a zkontroluje znovu.</li></ol>", None),
]


def _pixmap(key: str, width: int = 520) -> QPixmap | None:
    body = _SVG.get(key or "")
    if not body:
        return None
    try:
        from PySide6.QtSvg import QSvgRenderer
    except ImportError:
        return None
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 120"><rect width="260" height="120" '
           f'fill="white"/>{body}</svg>')
    r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    h = int(width * 120 / 260)
    pm = QPixmap(width, h)
    pm.fill(Qt.white)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p, QRectF(0, 0, width, h))
    p.end()
    return pm


def _norm(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


class TipsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Rychlé tipy – MicroStation ({len(TIPS)})")
        self.resize(940, 600)
        lay = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Hledat… (např. kolmice, rovnoběžka, vrstva, souřadnice)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        row = QHBoxLayout()
        self.list = QListWidget()
        self.list.setMinimumWidth(300)
        self.list.setMaximumWidth(340)
        self.view = QTextBrowser()
        self.list.currentItemChanged.connect(self._show)
        row.addWidget(self.list)
        row.addWidget(self.view, 1)
        lay.addLayout(row, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText("Zavřít")
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._filter("")

    def _filter(self, text: str):
        q = _norm(text.strip())
        self.list.clear()
        last = None
        order: dict[str, int] = {}
        for t in TIPS:
            order.setdefault(t[0], len(order))
        for i, (cat, name, keys, _html, _img) in sorted(enumerate(TIPS), key=lambda t: (order[t[1][0]], t[0])):
            if q and q not in _norm(f"{cat} {name} {keys}"):
                continue
            if cat != last:
                h = QListWidgetItem(cat.upper())
                h.setFlags(Qt.NoItemFlags)
                self.list.addItem(h)
                last = cat
            it = QListWidgetItem("   " + name)
            it.setData(Qt.UserRole, i)
            self.list.addItem(it)
        for r in range(self.list.count()):
            if self.list.item(r).data(Qt.UserRole) is not None:
                self.list.setCurrentRow(r)
                return
        self.view.setHtml("<p style='color:#6B7280'>Nic nenalezeno.</p>")

    def _show(self, cur, _prev=None):
        if cur is None or cur.data(Qt.UserRole) is None:
            return
        cat, name, _k, html, img = TIPS[cur.data(Qt.UserRole)]
        doc: QTextDocument = self.view.document()
        pic = ""
        pm = _pixmap(img) if img else None
        if pm is not None:
            doc.addResource(QTextDocument.ImageResource, QUrl(f"tip://{img}"), pm)
            pic = f"<p><img src='tip://{img}' width='{pm.width()}'></p>"
        self.view.setHtml(f"<p style='color:#6B7280'>{escape(cat)}</p><h2>{escape(name)}</h2>{pic}"
                          f"<div style='font-size:11pt'>{html}</div>")
