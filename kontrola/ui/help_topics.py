"""Vysvětlení pojmů a typů chyb s jednoduchými obrázky („Co to znamená?“)."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt, QUrl
from PySide6.QtGui import QPainter, QPixmap, QTextDocument
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QListWidget, QListWidgetItem,
                               QTextBrowser, QVBoxLayout)

# kresba: šedé čáry = výkres, červený kroužek = místo chyby, zelená = správně
_L = 'stroke="#374151" stroke-width="3" fill="none" stroke-linecap="round"'
_OK = 'stroke="#16A34A" stroke-width="3" fill="none" stroke-linecap="round"'
_E = 'stroke="#DC2626" stroke-width="2.5" fill="none"'
_T = 'font-family="Segoe UI, Arial" font-size="12" fill="#6B7280"'


def _mark(x, y, r=11):
    return f'<circle cx="{x}" cy="{y}" r="{r}" {_E}/>'


def _pair(bad: str, good: str) -> str:
    """Dva obrázky vedle sebe: vlevo chyba, vpravo jak to má být."""
    return (f'<g>{bad}<text x="60" y="114" {_T} text-anchor="middle">chyba</text></g>'
            f'<line x1="130" y1="10" x2="130" y2="100" stroke="#E5E7EB" stroke-width="1"/>'
            f'<g transform="translate(140,0)">{good}<text x="60" y="114" {_T} text-anchor="middle">správně</text></g>')


_SVG = {
    "chybejici_napojeni": _pair(
        f'<line x1="10" y1="60" x2="110" y2="60" {_L}/><line x1="60" y1="12" x2="60" y2="50" {_L}/>'
        f'<line x1="85" y1="98" x2="85" y2="52" {_L}/>' + _mark(60, 55, 9) + _mark(85, 58, 9),
        f'<line x1="10" y1="60" x2="110" y2="60" {_L}/><line x1="60" y1="12" x2="60" y2="60" {_OK}/>'
        f'<line x1="85" y1="98" x2="85" y2="60" {_OK}/>'),
    "visici_konce": _pair(
        f'<polyline points="15,95 15,20 105,20 105,70" {_L}/>' + _mark(105, 70),
        f'<polyline points="15,95 15,20 105,20 105,95 15,95" {_OK}/>'),
    "nezavrene_polygony": _pair(
        f'<polyline points="25,30 100,30 100,90 25,90 25,40" {_L}/>' + _mark(25, 35, 9),
        f'<polygon points="25,30 100,30 100,90 25,90" {_OK}/>'),
    "duplicity": _pair(
        f'<line x1="10" y1="55" x2="110" y2="55" {_L}/><line x1="10" y1="61" x2="110" y2="61" '
        f'stroke="#9CA3AF" stroke-width="3" stroke-dasharray="6 4"/>' + _mark(60, 58, 14)
        + f'<text x="60" y="30" {_T} text-anchor="middle">2 čáry přes sebe</text>',
        f'<line x1="10" y1="58" x2="110" y2="58" {_OK}/><text x="60" y="30" {_T} text-anchor="middle">jedna čára</text>'),
    "pruseciky_bez_uzlu": _pair(
        f'<line x1="10" y1="60" x2="110" y2="60" {_L}/><line x1="60" y1="10" x2="60" y2="100" {_L}/>' + _mark(60, 60),
        f'<line x1="10" y1="60" x2="60" y2="60" {_OK}/><line x1="60" y1="60" x2="110" y2="60" {_OK}/>'
        f'<line x1="60" y1="10" x2="60" y2="60" {_OK}/><line x1="60" y1="60" x2="60" y2="100" {_OK}/>'
        f'<circle cx="60" cy="60" r="4" fill="#16A34A"/>'),
    "samoprotnuti": _pair(
        f'<polygon points="20,25 100,90 100,25 20,90" {_L}/>' + _mark(60, 57),
        f'<polygon points="20,25 100,25 100,90 20,90" {_OK}/>'),
    "kratke_linie": _pair(
        f'<polyline points="10,60 70,60 74,58 110,58" {_L}/>' + _mark(72, 59, 9)
        + f'<text x="72" y="35" {_T} text-anchor="middle">&lt; 9 cm</text>',
        f'<line x1="10" y1="59" x2="110" y2="59" {_OK}/>'),
    "nulova_delka": _pair(
        '<circle cx="60" cy="58" r="3" fill="#374151"/>' + _mark(60, 58)
        + f'<text x="60" y="30" {_T} text-anchor="middle">čára délky 0</text>',
        f'<text x="60" y="62" {_T} text-anchor="middle">smazat</text>'),
    "body_blizko": _pair(
        '<circle cx="57" cy="58" r="4" fill="#374151"/><circle cx="64" cy="61" r="4" fill="#374151"/>' + _mark(60, 60, 14),
        '<circle cx="60" cy="60" r="4" fill="#16A34A"/>'),
    "prekryvy_polygonu": _pair(
        f'<rect x="15" y="25" width="55" height="60" {_L}/><rect x="55" y="25" width="55" height="60" {_L}/>'
        f'<rect x="55" y="25" width="15" height="60" fill="#FCA5A5" opacity="0.6"/>',
        f'<rect x="10" y="25" width="50" height="60" {_OK}/><rect x="60" y="25" width="50" height="60" {_OK}/>'),
    "mezery_polygonu": _pair(
        f'<rect x="10" y="25" width="48" height="60" {_L}/><rect x="62" y="25" width="48" height="60" {_L}/>'
        + _mark(60, 55, 9),
        f'<rect x="10" y="25" width="50" height="60" {_OK}/><rect x="60" y="25" width="50" height="60" {_OK}/>'),
    "mimo_rozsah": _pair(
        f'<rect x="10" y="20" width="80" height="70" stroke="#9CA3AF" stroke-dasharray="5 4" fill="none"/>'
        f'<line x1="20" y1="70" x2="70" y2="40" {_L}/><circle cx="112" cy="15" r="3" fill="#374151"/>' + _mark(112, 15, 8),
        f'<rect x="10" y="20" width="80" height="70" stroke="#9CA3AF" stroke-dasharray="5 4" fill="none"/>'
        f'<line x1="20" y1="70" x2="70" y2="40" {_OK}/>'),
    "symbologie": _pair(
        '<line x1="10" y1="40" x2="110" y2="40" stroke="#2563EB" stroke-width="3"/>'
        '<line x1="10" y1="75" x2="110" y2="75" stroke="#DC2626" stroke-width="6"/>' + _mark(60, 75, 12)
        + f'<text x="60" y="100" {_T} text-anchor="middle">jiná barva/tloušťka</text>',
        f'<line x1="10" y1="40" x2="110" y2="40" stroke="#2563EB" stroke-width="3"/>'
        f'<line x1="10" y1="75" x2="110" y2="75" stroke="#2563EB" stroke-width="3"/>'
        f'<text x="60" y="100" {_T} text-anchor="middle">podle Směrnice</text>'),
    "jednotnost_hladiny": _pair(
        ''.join(f'<line x1="10" y1="{y}" x2="110" y2="{y}" stroke="#374151" stroke-width="3"/>' for y in (25, 50, 100))
        + '<line x1="10" y1="75" x2="110" y2="75" stroke="#F59E0B" stroke-width="3"/>' + _mark(60, 75, 12),
        ''.join(f'<line x1="10" y1="{y}" x2="110" y2="{y}" stroke="#374151" stroke-width="3"/>' for y in (25, 50, 75, 100))),
    "texty": _pair(
        f'<rect x="20" y="30" width="80" height="50" {_L}/><text x="60" y="100" {_T} text-anchor="middle">bez popisu</text>'
        + _mark(60, 55, 16),
        f'<rect x="20" y="30" width="80" height="50" {_OK}/><text x="60" y="60" font-size="14" '
        f'font-family="Arial" fill="#111827" text-anchor="middle">1234</text>'),
}


def _txt(x, y, t, size=12, col="#374151", rot=0, anchor="middle"):
    tr = f' transform="rotate({rot} {x} {y})"' if rot else ""
    return (f'<text x="{x}" y="{y}" font-family="Segoe UI, Arial" font-size="{size}" fill="{col}" '
            f'text-anchor="{anchor}"{tr}>{t}</text>')


def _pt(x, y, col="#374151"):
    return f'<circle cx="{x}" cy="{y}" r="3.5" fill="{col}"/>'


# další obrázky (kartografie, geometrie, čísla bodů)
_SVG.update({
    "prekryv_linii": _pair(
        f'<line x1="10" y1="60" x2="80" y2="60" {_L}/><line x1="45" y1="66" x2="110" y2="66" {_L}/>'
        f'<line x1="45" y1="60" x2="80" y2="60" stroke="#DC2626" stroke-width="5" opacity="0.45"/>'
        + _txt(62, 40, "úsek 2×", 11, "#6B7280"),
        f'<line x1="10" y1="60" x2="60" y2="60" {_OK}/><line x1="60" y1="60" x2="110" y2="60" {_OK}/>'
        + _pt(60, 60, "#16A34A")),
    "blizke_prvky": _pair(
        f'<line x1="10" y1="60" x2="110" y2="60" {_L}/><polyline points="30,20 58,56 90,20" {_L}/>'
        + _mark(58, 57, 9) + _txt(60, 92, "2 mm od čáry", 11, "#6B7280"),
        f'<line x1="10" y1="60" x2="110" y2="60" {_L}/><polyline points="30,20 60,60 90,20" {_OK}/>'
        + _pt(60, 60, "#16A34A")),
    "popisy_pres_sebe": _pair(
        _txt(55, 60, "245.37", 18) + _txt(68, 66, "Plot", 18) + _mark(62, 58, 22),
        _txt(45, 45, "245.37", 18) + _txt(70, 85, "Plot", 18)),
    "popis_pres_caru": _pair(
        f'<line x1="10" y1="56" x2="110" y2="56" {_L}/>' + _txt(60, 62, "1203", 20) + _mark(60, 55, 22),
        f'<line x1="10" y1="56" x2="110" y2="56" {_L}/>' + _txt(60, 44, "1203", 20)),
    "cislo_bodu_daleko": _pair(
        _pt(25, 75) + _txt(95, 30, "17", 16) + f'<line x1="28" y1="72" x2="88" y2="36" stroke="#DC2626" '
        f'stroke-width="1.5" stroke-dasharray="4 3"/>' + _mark(95, 26, 14),
        _pt(40, 65) + _txt(52, 58, "17", 16, anchor="start")),
    "duplicitni_cislo_bodu": _pair(
        _pt(30, 60) + _txt(38, 54, "12", 16, anchor="start") + _pt(85, 70) + _txt(93, 64, "12", 16, anchor="start")
        + _mark(46, 49, 13) + _mark(101, 59, 13),
        _pt(30, 60) + _txt(38, 54, "12", 16, anchor="start") + _pt(85, 70) + _txt(93, 64, "13", 16, anchor="start")),
    "bod_bez_cisla": _pair(
        _pt(30, 50) + _txt(38, 44, "21", 16, anchor="start") + _pt(80, 75) + _mark(80, 75, 12),
        _pt(30, 50) + _txt(38, 44, "21", 16, anchor="start") + _pt(80, 75) + _txt(88, 69, "22", 16, anchor="start")),
    "popis_vzhuru_nohama": _pair(
        f'<line x1="10" y1="65" x2="110" y2="65" {_L}/>' + _txt(60, 48, "chodník", 16, rot=180) + _mark(60, 52, 24),
        f'<line x1="10" y1="65" x2="110" y2="65" {_L}/>' + _txt(60, 55, "chodník", 16)),
    "zbytecne_lomove_body": _pair(
        f'<polyline points="10,60 40,60 70,60 110,60" {_L}/>' + _pt(40, 60) + _pt(70, 60)
        + _mark(40, 60, 8) + _mark(70, 60, 8),
        f'<line x1="10" y1="60" x2="110" y2="60" {_OK}/>'),
    "zdvojeny_vrchol": _pair(
        f'<polyline points="10,80 60,30 110,80" {_L}/>' + _pt(60, 30) + _mark(60, 30, 10)
        + _txt(60, 100, "2 body na sobě", 11, "#6B7280"),
        f'<polyline points="10,80 60,30 110,80" {_OK}/>' + _pt(60, 30, "#16A34A")),
    "spicka": _pair(
        f'<polyline points="10,70 60,70 100,25 62,68" {_L}/>' + _mark(100, 25, 10),
        f'<polyline points="10,70 60,70" {_OK}/>'),
    "nepatrna_plocha": _pair(
        f'<polygon points="15,30 105,30 105,90 15,90" {_L}/><line x1="60" y1="30" x2="60" y2="90" {_L}/>'
        f'<line x1="63" y1="30" x2="63" y2="90" {_L}/>' + _mark(61.5, 60, 10),
        f'<polygon points="15,30 105,30 105,90 15,90" {_OK}/><line x1="60" y1="30" x2="60" y2="90" {_OK}/>'),
    "zatoulany_prvek": _pair(
        f'<polygon points="10,40 60,40 60,90 10,90" {_L}/><line x1="100" y1="15" x2="112" y2="22" {_L}/>'
        + _mark(106, 18, 11),
        f'<polygon points="10,40 60,40 60,90 10,90" {_OK}/>'),
    "rozdelena_cara": _pair(
        f'<line x1="10" y1="60" x2="60" y2="60" {_L}/><line x1="60" y1="60" x2="110" y2="60" '
        f'stroke="#6B7280" stroke-width="3" stroke-linecap="round"/>' + _mark(60, 60, 9),
        f'<line x1="10" y1="60" x2="110" y2="60" {_OK}/>'),
    "kontrola_ploch": _pair(
        f'<polygon points="10,25 110,25 110,95 10,95" {_L}/><line x1="60" y1="25" x2="60" y2="95" {_L}/>'
        + _txt(35, 64, "15", 14) + _txt(85, 64, "?", 16, "#DC2626") + _mark(85, 60, 13),
        f'<polygon points="10,25 110,25 110,95 10,95" {_OK}/><line x1="60" y1="25" x2="60" y2="95" {_OK}/>'
        + _txt(35, 64, "15", 14) + _txt(85, 64, "16", 14)),
})

# id: (nadpis, vysvětlení v HTML)
TOPICS: dict[str, tuple[str, str]] = {
    "chybejici_napojeni": (
        "Nedotažená / přetažená linie",
        "Čára má končit přesně na jiné čáře (např. plot na rohu budovy), ale chybí jí kousek "
        "(<b>nedotažení</b>) nebo přes ni kousek přečnívá (<b>přetažení</b>). Na obrazovce to není vidět, "
        "rozdíl bývá v milimetrech. Učitelova kontrola (MGEO) hlásí mezery nad <b>0,010 m</b> a přetahy nad "
        "<b>0,020 m</b>.<br><br><b>Oprava:</b> v MicroStationu použijte <i>Prodloužit prvek k průsečíku</i> "
        "(Extend to Intersection) nebo <i>Ořezat</i>, a kreslete vždy s přichytáváním (snap) na koncový bod "
        "či průsečík."),
    "visici_konce": (
        "Visící (volný) konec linie",
        "Konec čáry, který se nenapojuje na žádnou jinou čáru – typicky nedokreslený roh budovy nebo plot, "
        "který „nedojde“. Volné konce <b>na okraji kresby</b> se nepočítají (učitelova kontrola je taky "
        "nehlásí), proto je program uvádí jen jako informaci.<br><br><b>Oprava:</b> dotáhněte čáru na "
        "sousední prvek s přichytáváním, nebo ji zkraťte, pokud přečnívá."),
    "nezavrene_polygony": (
        "Nezavřený polygon",
        "Plocha (budova, parcela) musí být uzavřená – první a poslední bod musí být stejný. Pokud je mezi "
        "nimi byť malá mezera, plocha není uzavřená a nejde jí spočítat výměra ani vyplnit šrafou.<br><br>"
        "<b>Oprava:</b> v MicroStationu <i>Vytvořit oblast</i> nebo tvar zavřít příkazem <i>Uzavřít prvek</i> "
        "(Close Element); u lomené čáry přichyťte poslední bod na první."),
    "duplicity": (
        "Duplicitní prvek",
        "Dvě stejné čáry (nebo body, texty) leží přesně přes sebe. Na výkrese to vypadá jako jedna čára, "
        "ale při kontrole a tisku to vadí (dvojitá tloušťka, chybná topologie).<br><br><b>Oprava:</b> "
        "klikněte na místo, vyberte prvek a smažte jednu z kopií (v MicroStationu se mezi překrytými prvky "
        "přepíná klávesou Reset / pravým tlačítkem)."),
    "pruseciky_bez_uzlu": (
        "Průsečík bez uzlu (křížení)",
        "Dvě čáry se kříží, ale ani jedna není v místě křížení rozdělená – chybí tam společný bod (uzel). "
        "Pokud se čáry opravdu protínají (např. dva ploty), mají být v průsečíku rozdělené. "
        "Čára končící na jiné čáře (tvar T) nerozdělená být nemusí – to učitel nepočítá.<br><br>"
        "<b>Oprava:</b> nástroj <i>Rozdělit prvek</i> (Break Element) v místě průsečíku, nebo pokud se "
        "čáry křížit nemají, jednu zkraťte."),
    "samoprotnuti": (
        "Samoprotnutí",
        "Hranice plochy protíná sama sebe (tvar „osmičky“). Obvykle vznikne přehozením pořadí bodů "
        "nebo omylem kliknutým bodem navíc.<br><br><b>Oprava:</b> upravte vrcholy (Modify Element) tak, "
        "aby hranice nešla přes sebe, případně tvar překreslete."),
    "kratke_linie": (
        "Krátká linie nebo úsek",
        "Čára nebo úsek lomené čáry kratší než <b>0,090 m</b>. Většinou vznikne omylem (dvojklik, "
        "neúmyslný bod navíc) a v měřítku mapy nemá smysl.<br><br><b>Oprava:</b> smažte přebytečný vrchol "
        "(Delete Vertex) nebo krátkou čáru a napojte sousední prvky."),
    "nulova_delka": (
        "Prvek nulové délky",
        "Čára, jejíž začátek i konec jsou ve stejném bodě – na výkrese není vidět, ale je v souboru. "
        "<br><br><b>Oprava:</b> vyberte ji (přiblížením na místo) a smažte."),
    "body_blizko": (
        "Body téměř na sobě",
        "Dva body (nebo značky) leží pár milimetrů od sebe – nejspíš jde o tentýž bod zadaný dvakrát, "
        "nebo byl jeden omylem posunut.<br><br><b>Oprava:</b> nechte jen jeden bod na správných "
        "souřadnicích (ze seznamu souřadnic)."),
    "prekryvy_polygonu": (
        "Překryv polygonů",
        "Dvě plochy, které mají sousedit, se částečně překrývají. Hranice sousedních ploch má být společná."
        "<br><br><b>Oprava:</b> upravte vrcholy tak, aby sousední plochy sdílely stejné body."),
    "mezery_polygonu": (
        "Mezera mezi polygony",
        "Mezi dvěma sousedními plochami je úzká mezera – hranice nejsou na sobě.<br><br><b>Oprava:</b> "
        "přichyťte vrcholy jedné plochy na vrcholy sousední."),
    "mimo_rozsah": (
        "Prvek mimo rozsah",
        "Prvek leží daleko od zbytku kresby (např. omylem zadaná souřadnice 0,0). Ve výkrese pak "
        "„Přiblížit vše“ ukáže jen malou tečku.<br><br><b>Oprava:</b> prvek najděte (tlačítko Najít "
        "v MicroStationu) a smažte nebo přesuňte na správné místo."),
    "symbologie": (
        "Symbologie (vrstva, barva, styl, písmo)",
        "Každý prvek musí mít vzhled přesně podle <b>Směrnice</b> (zadání od učitele): správnou vrstvu "
        "(level), barvu, styl čáry, tloušťku, u textu písmo a velikost, u buněk název a měřítko. Tohle "
        "kontroluje učitelův program GISoft – v protokolu je chybný atribut označen „(!)“.<br><br>"
        "<b>Oprava:</b> vyberte prvek a v MicroStationu změňte atributy (Change Element Attributes) na "
        "hodnoty ze Směrnice; hodnoty najdete v panelu Prvek (klikněte na prvek ve výkresu)."),
    "atribut_dle_vrstvy": (
        "Atribut dle vrstvy (ByLevel)",
        "Barva, styl nebo tloušťka jsou nastavené „podle vrstvy“ místo pevné hodnoty. Učitelova kontrola "
        "často vyžaduje pevné hodnoty u prvku.<br><br><b>Oprava:</b> nastavte atributy prvku na "
        "konkrétní hodnoty ze Směrnice."),
    "jednotnost_hladiny": (
        "Prvek jiný než ostatní na vrstvě",
        "Na vrstvě je většina prvků stejná (barva, styl, tloušťka), ale tento se liší. Často jde o prvek, "
        "který jste nakreslili s jiným aktivním nastavením.<br><br><b>Oprava:</b> použijte nástroj "
        "<i>Shodné atributy</i> (Match Element Attributes) – nejdřív klikněte na správný prvek, pak na "
        "tento."),
    "nepovolene_hladiny": (
        "Vrstva není ve Směrnici",
        "Prvky leží na vrstvě (levelu), kterou Směrnice nezná – třeba „Default“ nebo pomocná vrstva. "
        "Při odevzdání tam nesmí nic zůstat.<br><br><b>Oprava:</b> přesuňte prvky na správnou vrstvu "
        "(Change Element Attributes → Level) nebo pomocné prvky smažte."),
    "nekodovane": (
        "Nekódovaný prvek",
        "Prvek neodpovídá žádnému pravidlu ze Směrnice – program neví, co to je.<br><br><b>Oprava:</b> "
        "zkontrolujte vrstvu a atributy prvku, případně ho smažte, pokud je navíc."),
    "texty": (
        "Popis (text) prvku",
        "Prvek, který má mít podle Směrnice popis (číslo budovy, parcely, výška…), ho nemá, nebo je popis "
        "daleko od prvku.<br><br><b>Oprava:</b> doplňte text na správnou vrstvu blízko prvku."),
    "typ_geometrie": (
        "Typ geometrie",
        "Prvek je jiného druhu, než požaduje Směrnice – např. budova nakreslená jako jednotlivé čáry místo "
        "uzavřeného tvaru, nebo bod jako krátká čára místo buňky.<br><br><b>Oprava:</b> prvek překreslete "
        "správným nástrojem (Tvar / Lomená čára / Buňka)."),
    "seznam_souradnic": (
        "Seznam souřadnic",
        "Porovnání bodů ve výkresu s vaším seznamem souřadnic (z Gromy): chybí bod, je posunutý, nebo "
        "u něj chybí číslo či výška.<br><br><b>Oprava:</b> vložte bod znovu podle souřadnic ze seznamu "
        "(v MicroStationu klávesnicí: key-in <tt>XY=Y,X</tt>)."),
    "atributy": (
        "Atributy prvku",
        "Kontrola doplňkových atributů (dat) prvku podle pravidel projektu."),
    "blizke_prvky": (
        "Prvky příliš blízko (Limit)",
        "MGEO hlídá, aby dva prvky, které se nedotýkají, nebyly blíž než <b>Limit</b> (obvykle 1 cm). Lomový bod "
        "čáry 3 mm vedle jiné čáry je skoro jistě chyba – měl na ní ležet.<br><br><b>Oprava:</b> vrchol přesuňte "
        "s přichycením na čáru (Nearest), nebo ho odsuňte dál."),
    "zbytecne_lomove_body": (
        "Zbytečné lomové body",
        "Lomový bod na rovné čáře, na který nic nenavazuje. Nevadí, ale zbytečně zatěžuje výkres a při "
        "editaci se na něm snadno udělá chyba.<br><br><b>Oprava:</b> Odstranit vrchol (Delete Vertex)."),
    "spicka": (
        "Špička",
        "Čára se v lomovém bodě otočí skoro o 180° a vede zpět po sobě – omylem kliknutý bod nebo „zub“ po "
        "úpravě vrcholu. Na výkrese ji často není vidět.<br><br><b>Oprava:</b> Odstranit vrchol (Delete Vertex) "
        "na konci špičky."),
    "nepatrna_plocha": (
        "Nepatrná nebo úzká plocha",
        "Uzavřená plocha s nepatrnou výměrou nebo štěrbina – zbytek po editaci.<br><br><b>Oprava:</b> plochu "
        "smažte, nebo upravte hranice tak, aby sousední plochy navazovaly přesně."),
    "zdvojeny_vrchol": (
        "Zdvojený lomový bod",
        "Dva lomové body čáry leží na sobě – na výkrese to není vidět, ale čára má úsek nulové délky."
        "<br><br><b>Oprava:</b> jeden z vrcholů odstraňte (Odstranit vrchol – Delete Vertex) nebo čáru "
        "nakreslete znovu."),
    "zatoulany_prvek": (
        "Zatoulaný prvek daleko od kresby",
        "Prvek leží daleko od ostatní kresby – omylem kliknutý bod, prvek v počátku souřadnic nebo kopie mimo "
        "mapu. Kvůli němu je „Zobrazit vše“ skoro prázdné.<br><br><b>Oprava:</b> přibližte si chybu, prvek "
        "vyberte a smažte, nebo ho přesuňte na správné místo."),
    "bod_bez_cisla": (
        "Bod bez čísla",
        "Ostatní body na vrstvě mají u sebe číslo, tento ne – zapomenutý nebo smazaný popis, nebo bod navíc."
        "<br><br><b>Oprava:</b> doplňte číslo bodu podle seznamu souřadnic (Umístit text), nebo bod smažte."),
    "duplicitni_cislo_bodu": (
        "Stejné číslo bodu dvakrát",
        "Stejné číslo bodu je ve výkresu na dvou místech – překlep, zkopírovaný popis nebo bod vložený dvakrát."
        "<br><br><b>Oprava:</b> podle seznamu souřadnic zjistěte, který bod je správně, a číslo opravte "
        "(Upravit text) nebo přebytečný bod smažte."),
    "format_popisu": (
        "Nejednotný formát popisů na vrstvě",
        "Většina popisů na vrstvě má stejný tvar (např. výšky 245.37), tento se liší – jiný počet desetinných "
        "míst, čárka místo tečky, písmeno navíc.<br><br><b>Oprava:</b> upravte text do stejného tvaru jako "
        "ostatní (Upravit text)."),
    "rozdelena_cara": (
        "Zbytečně rozdělená čára",
        "Dvě stejné čáry navazují v přímém směru a v místě napojení nic není – mohla by to být jedna.<br><br>"
        "<b>Oprava:</b> nepovinné; čáry lze spojit (Vytvořit složený řetězec / Spojit prvky)."),
    "vychozi_vrstva": (
        "Prvek na výchozí vrstvě",
        "Prvek je na vrstvě <b>Default</b> (v DXF <b>0</b>) – v MicroStationu se před kreslením nepřepnula "
        "aktivní vrstva. Učitel ho bere jako prvek na špatné vrstvě.<br><br><b>Oprava:</b> vyberte prvek a "
        "změňte mu vrstvu (Změnit atributy prvku → Level); příště nejdřív zvolte aktivní vrstvu."),
    "vypnuta_vrstva": (
        "Prvky na vypnuté vrstvě",
        "Vrstva je ve výkresu vypnutá nebo zmrazená, takže její prvky na obrazovce nevidíte – ale v souboru "
        "jsou a učitelova kontrola je najde (zapomenuté pomocné čáry, kopie staré kresby).<br><br>"
        "<b>Oprava:</b> zapněte vrstvu ve Správci vrstev, prvky prohlédněte a smažte nebo přesuňte."),
    "maly_text": (
        "Nečitelně malý text",
        "Text je po vytištění v měřítku výkresu menší než zadaná mez a nepůjde přečíst.<br><br><b>Oprava:</b> "
        "zvětšete výšku textu podle Směrnice (Změnit atributy textu)."),
    "prekryv_linii": (
        "Překrývající se čáry",
        "Kus čáry leží na jiné čáře – úsek je nakreslený dvakrát (často po kopírování nebo když se čára kreslí "
        "znovu přes starou). Ve výkresu to není vidět, ale MGEO to hlásí.<br><br><b>Oprava:</b> přebytečnou "
        "čáru (nebo její část) smažte, případně ji zkraťte k navazujícímu bodu (Částečné smazání / Oříznout)."),
    "popisy_pres_sebe": (
        "Popisy přes sebe",
        "Dva texty se na mapě překrývají a nejdou přečíst. Aplikace to počítá z velikosti písma, takže to sedí "
        "i s tiskem.<br><br><b>Oprava:</b> Přesunout (Move) jeden z popisů kousek vedle."),
    "popis_pres_caru": (
        "Popis přeškrtnutý čarou",
        "Přes text vede čára. Na mapě se popisy kladou vedle kresby, ne přes ni.<br><br><b>Oprava:</b> popis "
        "posuňte, případně natočte podél čáry."),
    "cislo_bodu_daleko": (
        "Číslo bodu daleko od bodu",
        "Číslo bodu je daleko od značky bodu – nejspíš se po posunu bodu nebo textu rozpojily.<br><br>"
        "<b>Oprava:</b> číslo přesuňte hned k bodu (vpravo nahoru), nebo zkontrolujte, že bod je na správném místě "
        "(Ověřit seznam souřadnic)."),
    "popis_vzhuru_nohama": (
        "Popis vzhůru nohama",
        "Text natočený mezi 90° a 270° se čte vzhůru nohama. Popisy se otáčejí tak, aby se četly zdola nebo "
        "zprava.<br><br><b>Oprava:</b> Otočit (Rotate) o 180°, nebo v Atributech textu změnit natočení."),
    "kontrola_ploch": (
        "Kontrola ploch",
        "Z hraničních čar se sestaví plochy (parcely, druhy pozemků) a hlídá se, že každá má <b>právě jeden</b> popis "
        "nebo definiční bod a že stejné číslo není ve dvou plochách. Kontrola je ve výchozím stavu vypnutá – zapněte "
        "ji v Nastavení kontrol, když zadání plochy vyžaduje.<br><br><b>Oprava:</b> doplňte chybějící číslo / značku, "
        "smažte přebytečné, uzavřete hranici plochy."),
    "_uzel": (
        "Pojem: uzel a tolerance",
        "<b>Uzel</b> je místo, kde se čáry setkávají – mají tam společný koncový bod. <b>Tolerance</b> "
        "je největší rozdíl, který se ještě považuje za „stejný bod“. Učitel používá: začištění 0,010 m, "
        "přetah/křížení 0,020 m, krátká čára 0,090 m. Tyto hodnoty jsou i v Nastavení kontrol."),
    "_zavaznost": (
        "Pojem: chyba, varování, info",
        "<b>Chyba</b> – učitel ji najde a strhne body, je nutné ji opravit.<br><b>Varování</b> – "
        "pravděpodobně problém, ale posuďte sami (např. neobvyklé nastavení).<br><b>Info</b> – jen "
        "pro vaši informaci, neopravuje se (např. volný konec na okraji kresby).<br><br>Stav "
        "<b>Opraveno</b>/<b>Ignorovat</b> si nastavujete sami, program si ho pamatuje v projektu."),
}


def topic_for(check_id: str) -> str | None:
    return check_id if check_id in TOPICS else None


def illustration_svg(check_id: str) -> str | None:
    """Obrázek „chyba / správně“ jako samostatné SVG (pro HTML protokol – bez Qt)."""
    body = _SVG.get(check_id)
    if body is None:
        return None
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 120" width="260" height="120">'
            f'<rect width="260" height="120" fill="white"/>{body}</svg>')


def illustration(check_id: str, width: int = 520) -> QPixmap | None:
    body = _SVG.get(check_id)
    if body is None:
        return None
    try:
        from PySide6.QtSvg import QSvgRenderer
    except ImportError:
        return None
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 120" width="260" height="120">'
           f'<rect width="260" height="120" fill="white"/>{body}</svg>')
    r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    h = int(width * 120 / 260)
    pm = QPixmap(width, h)
    pm.fill(Qt.white)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p, QRectF(0, 0, width, h))
    p.end()
    return pm


def topic_html(check_id: str, doc: QTextDocument | None = None) -> str:
    title, text = TOPICS.get(check_id, (check_id, "K tomuto typu zatím není vysvětlení."))
    img = ""
    pm = illustration(check_id)
    if pm is not None and doc is not None:
        url = QUrl(f"img://{check_id}")
        doc.addResource(QTextDocument.ImageResource, url, pm)
        img = f"<p><img src='img://{check_id}' width='{pm.width()}'></p>"
    return f"<h2>{title}</h2>{img}<p style='font-size:11pt'>{text}</p>"


class HelpDialog(QDialog):
    """Seznam pojmů vlevo, vysvětlení s obrázkem vpravo."""

    def __init__(self, parent=None, check_id: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Co to znamená? – vysvětlení chyb a pojmů")
        self.resize(900, 560)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.list = QListWidget()
        self.list.setMinimumWidth(300)
        self.list.setMaximumWidth(320)
        for cid, (title, _) in TOPICS.items():
            it = QListWidgetItem(title)
            it.setData(Qt.UserRole, cid)
            self.list.addItem(it)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.list.currentItemChanged.connect(self._show)
        row.addWidget(self.list)
        row.addWidget(self.view, 1)
        lay.addLayout(row, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Close).setText("Zavřít")
        lay.addWidget(bb)
        self.select(check_id or "chybejici_napojeni")

    def select(self, check_id: str):
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == check_id:
                self.list.setCurrentRow(i)
                return
        self.list.setCurrentRow(0)

    def _show(self, cur, _prev=None):
        if cur is None:
            return
        cid = cur.data(Qt.UserRole)
        self.view.setHtml(topic_html(cid, self.view.document()))
