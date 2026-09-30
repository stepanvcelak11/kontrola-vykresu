"""Krátké návody, jak chybu opravit v MicroStationu (české názvy nástrojů, v závorce anglické)."""

from __future__ import annotations

import re

from .checks.base import Issue

SNAP = "Příště kreslete s přichycením (Tentative / Klíčový bod – Keypoint, průsečík – Intersection)."

_TOPO = {
    "visici_konce": "Konec čáry nikam nenavazuje. Má-li navazovat, dotáhněte ho k sousední čáře nástrojem "
                    "Prodloužit prvek k průsečíku (Extend Element to Intersection) nebo přesuňte vrchol "
                    "(Modify Element) s přichycením. Je-li to okraj mapy nebo záměr, označte chybu Ignorovat.",
    "duplicity": "Dvě stejné čáry leží na sobě. Vyberte jednu z nich (Výběr prvku, případně Tab / Reset pro "
                 "přepnutí mezi prvky na sobě) a smažte ji – pozor, ať nesmažete obě.",
    "samoprotnuti": "Čára křižuje sama sebe. Upravte vrcholy nástrojem Upravit prvek (Modify Element) nebo "
                    "Odstranit vrchol (Delete Vertex).",
    "pruseciky_bez_uzlu": "Čáry se kříží, ale nejsou v průsečíku rozdělené. Rozdělte obě čáry v průsečíku: "
                          "Částečné smazání / Rozdělit prvek (Break Element) s přichycením na průsečík, "
                          "nebo vložte vrchol (Insert Vertex).",
    "kratke_linie": "Velmi krátká čára (pod 0,09 m) bývá zbytek po editaci. Smažte ji, nebo spojte s navazující "
                    "čárou (Vytvořit složený řetězec – Create Complex Chain).",
    "nulova_delka": "Prvek nulové délky – smažte ho (Výběr prvku → Delete).",
    "nezavrene_polygony": "Plocha není uzavřená. Přesuňte poslední vrchol s přichycením na první, nebo plochu "
                          "vytvořte jako tvar (Umístit tvar / Vytvořit složený tvar – Create Complex Shape).",
    "prekryvy_polygonu": "Dvě plochy se překrývají. Upravte hranici jedné z nich tak, aby vedla po společné "
                         "hranici (vrcholy s přichycením na vrcholy sousední plochy).",
    "mezery_polygonu": "Mezi sousedními plochami je úzká mezera. Posuňte vrcholy s přichycením na hranici "
                       "sousední plochy.",
    "mimo_rozsah": "Prvek leží daleko mimo mapu – nejspíš omylem nakreslený nebo zkopírovaný. Najděte ho "
                   "(Přiblížit na prvek) a smažte nebo přesuňte.",
    "body_blizko": "Dva body jsou téměř na sobě – bod je asi zaměřený nebo naimportovaný dvakrát. "
                   "Zkontrolujte seznam souřadnic a přebytečný bod smažte.",
}

_ATTR = {
    "atribut_dle_vrstvy": "Barva, styl nebo tloušťka je nastavená „Dle vrstvy“ (ByLevel), což zadání "
                          "nepovoluje. Vyberte prvek, v Atributech prvku (Element Attributes) nastavte konkrétní "
                          "hodnoty a použijte Změnit atributy prvku (Change Element Attributes).",
    "blizke_prvky": "Lomový bod leží pár milimetrů od jiné čáry. Buď ho na čáru přichyťte (Upravit prvek + "
                    "přichycení Nearest / Intersection), nebo ho odsuňte – čáry se mají přesně dotýkat.",
    "zbytecne_lomove_body": "Odstraňte vrchol nástrojem Odstranit vrchol (Delete Vertex).",
    "spicka": "Odstraňte vrchol na konci špičky (Delete Vertex), nebo ho přesuňte na správné místo.",
    "nepatrna_plocha": "Plochu smažte, nebo upravte hranice, aby sousední plochy navazovaly přesně (přichycení).",
    "zatoulany_prvek": "Přibližte chybu, prvek vyberte a smažte (Smazat), nebo ho přesuňte na správné místo "
                       "(Přesunout). Pak Zobrazit vše (Fit View) ukáže celou kresbu.",
    "format_popisu": "Upravte text do stejného tvaru jako ostatní popisy na vrstvě (Upravit text – Edit Text), "
                     "např. výšku na 2 desetinná místa s tečkou.",
    "rozdelena_cara": "Nepovinné – čáry lze spojit (Vytvořit složený řetězec / Spojit prvky), jinak nevadí.",
    "maly_text": "Zvětšete výšku textu podle Směrnice (Změnit atributy prvku / Upravit text).",
    "prekryv_linii": "Kus čáry leží na jiné čáře. Přebytečnou čáru smažte, nebo ji zkraťte k navazujícímu bodu "
                     "(Částečné smazání – Partial Delete, Oříznout k prvku). Tab/Reset přepíná mezi prvky na sobě.",
    "popisy_pres_sebe": "Přesuňte jeden z popisů vedle (Přesunout – Move), aby se nepřekrývaly.",
    "popis_pres_caru": "Posuňte popis vedle čáry, nebo ho natočte podél ní (Přesunout / Otočit).",
    "cislo_bodu_daleko": "Přesuňte číslo hned k bodu (vpravo nahoru). Pokud se posunul bod, vraťte ho na "
                         "souřadnice ze seznamu (Ověřit seznam souřadnic).",
    "popis_vzhuru_nohama": "Otočte text o 180° (Otočit – Rotate), aby se četl zdola nebo zprava.",
    "kontrola_ploch": "Doplňte do plochy popis / definiční bod (číslo parcely, značku druhu pozemku) na vrstvu "
                      "popisů, nebo smažte přebytečný. Plocha musí být z hranic uzavřená.",
    "nepovolene_hladiny": "Celá vrstva není ve Směrnici. Všechny její prvky najednou: Správce vrstev (Level "
                          "Manager) → pravým na vrstvu → Vybrat prvky (nebo Výběr podle atributů), pak Změnit "
                          "atributy prvku → Vrstva = správná vrstva ze Směrnice a klik do výkresu. Pomocné prvky, "
                          "které do výkresu nepatří, smažte. U bodů z Gromy zkontrolujte vrstvy v nastavení importu. Je-li vrstva popsaná ve Wordu se "
                          "zadáním (např. „Vrstva 58 – podrobné body“), nahrajte Word do Zadání → Pokyny ze zadání "
                          "a přidejte vrstvy do pravidel.",
    "nekodovane": "Prvek neodpovídá žádnému pravidlu – je na vrstvě, kam takový prvek nepatří. Přesuňte ho na "
                  "vrstvu podle Směrnice nebo změňte jeho typ.",
    "jednotnost_hladiny": "Prvky na jedné vrstvě mají různou symbologii. Sjednoťte je podle Směrnice "
                          "(Změnit atributy prvku, případně výběr podle atributů – Select By Attributes).",
    "typ_geometrie": "Prvek je jiného typu, než Směrnice povoluje (např. úsečka místo lomené čáry, text místo "
                     "buňky). Nakreslete ho znovu správným nástrojem.",
    "atributy": "Prvku chybí povinný údaj – doplňte ho podle tabulky atributů.",
}


def navod(iss: Issue) -> str:
    """Návod k opravě pro jednu chybu (prázdný text, když pro typ chyby návod není)."""
    cid, msg = iss.check_id, iss.message
    low = msg.lower()
    if cid == "chybejici_napojeni":
        if "přetažen" in low:
            return ("Čára přečnívá přes jinou čáru. Zkraťte ji nástrojem Oříznout k prvku / Prodloužit prvek "
                    "k průsečíku (Trim to Element, Extend Element to Intersection) nebo přesuňte koncový vrchol "
                    "s přichycením na průsečík. " + SNAP)
        return ("Čára nedosahuje k sousední čáře (chybí kousek). Prodlužte ji nástrojem Prodloužit prvek "
                "k průsečíku (Extend Element to Intersection) nebo přesuňte koncový vrchol s přichycením. " + SNAP)
    if cid in _TOPO:
        return _TOPO[cid]
    if cid == "symbologie":
        return _symbologie(msg)
    if cid == "texty":
        if "chybí popis" in low:
            m = re.search(r"\(vrstva (\S+)\)|na vrstvě (\S+)", msg)
            return ("Doplňte popis nástrojem Umístit text (Place Text)"
                    + (f" na vrstvu {m.group(1) or m.group(2)}" if m else "") + " se správným stylem textu.")
        if "mimo" in low:
            return "Popis leží mimo svou plochu – přesuňte ho dovnitř (Přesunout – Move)."
        if "více popisů" in low or "víc popisů" in low:
            return "V ploše je víc popisů, má být jen jeden – přebytečný smažte."
        return "Upravte popis podle tabulky atributů."
    if cid == "seznam_souradnic":
        if "chybí" in low:
            return ("Bod ze seznamu souřadnic ve výkresu chybí. Naimportujte body znovu z Gromy "
                    "(nebo bod umístěte zadáním souřadnic – AccuDraw / Klávesnice: XY=).")
        if "posunutý" in low:
            return ("Bod je jinde než v seznamu souřadnic – asi byl posunut myší. Umístěte ho znovu přesně "
                    "na souřadnice ze seznamu (XY=Y,X) nebo body naimportujte znovu.")
        if "číslo bodu" in low:
            return "Text s číslem bodu nesouhlasí se seznamem – opravte text (Upravit text – Edit Text)."
        if "výška" in low:
            return "Výškový popis nesouhlasí se seznamem – opravte text (Upravit text – Edit Text)."
    if cid in _ATTR:
        return _ATTR[cid]
    return ""


def _symbologie(msg: str) -> str:
    low = msg.lower()
    steps = []
    m = re.search(r"vrstva (.+?) \(má být ([^)]+)\)", msg)
    if m:
        steps.append(f"vrstvu na {m.group(2)}")
    m = re.search(r"barva \S+ \(má být ([^)]+)\)", msg)
    if m:
        steps.append(f"barvu na {m.group(1).replace('|', ' nebo ')}")
    m = re.search(r"měřítko stylu \S+ \(má být ([^)]+)\)", msg)
    if m:
        steps.append(f"měřítko stylu čáry (Line Style Scale) na {m.group(1)}")
    elif re.search(r"\bstyl (\S+) \(má být ([^)]+)\)", msg):
        m = re.search(r"\bstyl (\S+) \(má být ([^)]+)\)", msg)
        steps.append(f"styl čáry na {m.group(2).replace('|', ' nebo ')}")
    m = re.search(r"tloušťka \S+ mm \(má být ([^)]+)\)", msg)
    if m:
        steps.append(f"tloušťku na {m.group(1)}")
    m = re.search(r"měřítko buňky \S+ \(má být ([^)]+)\)", msg)
    if m:
        steps.append(f"měřítko buňky na {m.group(1)} (buňku umístěte znovu se správným měřítkem)")
    text_steps = []
    for key, what in (("výška textu", "výšku"), ("šířka textu", "šířku"), ("zarovnání", "zarovnání"),
                      ("font", "font")):
        m = re.search(key + r" [^(]*\(má být ([^)]+)\)", msg)
        if m:
            text_steps.append(f"{what} {m.group(1)}")
    if "není tučné" in low:
        text_steps.append("tučné písmo")
    if "je tučné" in low and "není" not in low:
        text_steps.append("netučné písmo")
    if "není kurzíva" in low:
        text_steps.append("kurzívu")
    out = []
    if "neuložil" in low:
        return ("V DXF je čára Continuous, protože MicroStation uživatelský styl do DXF neuložil. Otevřete DGN "
                "a zkontrolujte v Atributech prvku, že má čára správný styl a měřítko stylu. Pokud ano, chybu "
                "označte Ignorovat.")
    if steps:
        out.append("Vyberte prvek a v Atributech prvku (Element Attributes) nastavte " + ", ".join(steps)
                   + "; pak Změnit atributy prvku (Change Element Attributes).")
    if text_steps:
        out.append("U textu nastavte " + ", ".join(text_steps) + " – nejlépe vyberte správný styl textu "
                   "(Text Style) podle tabulky a použijte Změnit atributy textu (Change Text Attributes).")
    return " ".join(out) or "Upravte atributy prvku podle Směrnice (Změnit atributy prvku)."
