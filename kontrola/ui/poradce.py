"""Poradce: okénko v rohu, kam napíšete (nebo nadiktujete) otázku – odpověď najde v návodech aplikace.

Funguje bez internetu: prohledá rychlé tipy, vysvětlení chyb, návody k opravě a časté otázky.
Diktování: ve Windows stiskněte Win+H – řeč se přepíše do pole otázky.
"""

from __future__ import annotations

import re
import unicodedata
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser, QVBoxLayout, QWidget

FAQ = [
    ("Jak začít / jak to funguje", "zacit funguje postup jak pouzivat navod",
     "1) V záložce <b>Zadání</b> nahrajte Směrnici (Excel/PDF) a Word se zadáním. 2) <b>Otevřít</b> výkres – DXF "
     "uložený z MicroStationu. 3) <b>Zkontrolovat</b> (F5). 4) Klikejte na chyby – výkres se přiblíží a ukáže se "
     "návod. 5) Před odevzdáním <b>Připraveno k odevzdání?</b>"),
    ("Jak uložit DXF z MicroStationu", "dxf ulozit dgn prevod export",
     "V MicroStationu <b>Soubor → Uložit jako</b>, typ <b>DXF</b>. Uložte vedle DGN – aplikace změny sama hlídá."),
    ("Proč je vrstva „není ve Směrnici“", "vrstva neni ve smernici 58 59 60 level",
     "Vrstva chybí v pravidlech. Pokud ji popisuje Word se zadáním, nahrajte ho do <b>Zadání → Pokyny ze "
     "zadání</b> a potvrďte „Přidat do pravidel“. Jinak prvky přesuňte na vrstvu ze Směrnice."),
    ("Co je skóre připravenosti", "skore body znamka pripravenost 100",
     "Orientační číslo 0–100: srážky za chyby topologie, atributů a varování. 100 = nic k opravě. Není to známka."),
    ("Jak zkontrolovat výpočet z Gromy", "groma vypocet zapisnik souradnice polarni",
     "<b>Kontrola → Kontrola výpočtu souřadnic</b>: vyberte zápisník (.zap), dané body a svůj seznam. Záložka "
     "<b>Diagnóza</b> řekne, proč se body liší."),
    ("Rozpracovaný výkres – mnoho chyb", "rozpracovany moc chyb nedokonceny",
     "Zapněte <b>Rozpracovaný výkres</b> na liště – nehlásí se volné konce a neuzavřené plochy. Před "
     "odevzdáním vypněte."),
    ("Jak najít chybu v MicroStationu", "najit microstation misto chyby window center",
     "U chyby klikněte <b>Najít v MicroStationu</b>, v MicroStationu otevřete Key-in, vložte (Ctrl+V) a Enter."),
    ("Automatická oprava", "automaticka oprava opravit sam",
     "<b>Kontrola → Oprava</b> vytvoří nový DXF s opravenou topologií. Učitel automaticky opravený výkres "
     "neuzná – slouží k tomu, abyste viděli, co opravit ručně."),
    ("Ověřit body podle seznamu souřadnic", "seznam souradnic overit body sedi posunuty chybi cislo vyska",
     "<b>Kontrola → Ověřit seznam souřadnic</b> (Ctrl+J): vyberte seznam (číslo Y X Z). Tabulka ukáže body "
     "chybějící, posunuté, se špatným číslem nebo výškou a body navíc; dvojklik bod přiblíží."),
    ("Jak opravit chyby v MicroStationu krok za krokem", "opravit postup pruvodce microstation souradnice keyin",
     "<b>Kontrola → Opravný průvodce</b> (Ctrl+G): chyby jedna po druhé, seřazené podle polohy, s přesným "
     "postupem, souřadnicemi cíle a key-inem ke zkopírování. Opravujete sami v DGN, výkres zůstane váš."),
    ("Vybrat, co se má kontrolovat", "vybrat co kontrolovat zaskrtnout sada vse jen topologie atributy cizi "
     "vykres bez pravidel geometrie",
     "<b>Kontrola → Co zkontrolovat…</b> (Ctrl+Shift+K) nebo šipka u tlačítka <b>Zkontrolovat</b>: zaškrtněte "
     "jednotlivé kontroly nebo zvolte sadu – <i>Jako učitel</i>, <i>Vše, co jde</i>, <i>Jen topologie</i>, "
     "<i>Vzhled mapy</i> nebo <i>Cizí výkres (bez pravidel)</i> pro výkres bez Směrnice."),
    ("Spojnice podle náčrtu", "nacrt spojnice spojene body plot nakresleno chybi cara",
     "<b>Kontrola → Spojnice podle náčrtu</b>: napište např. <i>plot: 1-2-3-4</i> a aplikace ověří, že tyto "
     "čáry ve výkresu máte (a na správné vrstvě)."),
    ("Porovnat s PDF od učitele", "pdf vzor porovnat kresba chybi cara ucitel",
     "<b>Zadání → Vzor</b>: nahrajte PDF z MicroStationu a klikněte <b>Porovnat</b>. PDF se samo umístí na "
     "výkres podle popisů a ukáže čáry, které vám chybí nebo přebývají."),
    ("Chyby přímo v MicroStationu", "microstation makro vba kruzky dalsi chyba f8 propojeni",
     "<b>Kontrola → Propojení s MicroStationem</b>: uložte makro, importujte ho ve VBA editoru a zapněte "
     "<b>Posílat chyby do MicroStationu</b>. V MicroStationu pak F6 načte chyby (dočasné kroužky, do DGN se "
     "neukládají) a F8 skočí na další."),
    ("Otevřít DGN bez převodu", "dgn otevrit primo bez dxf prevod",
     "DGN z MicroStationu V8i / CONNECT otevřete přímo – aplikace ho umí číst sama (experimentálně). Když je "
     "vedle stejnojmenný novější DXF, použije ho. S hlídáním změn stačí v MicroStationu Ctrl+S."),
    ("Časová osa výkresu", "casova osa historie verze smazal omylem vratit prehrat",
     "<b>Kontrola → Časová osa výkresu</b> (Ctrl+H): každá kontrolovaná verze, přehrání, kde přibyly chyby, "
     "porovnání a vytažení smazaných prvků do DXF."),
    ("Co nahlásí učitel", "ucitel protokol predpoved nahlasi odhad",
     "<b>Kontrola → Učitelův pohled</b>: odhad protokolu od učitele. Čím víc jeho protokolů porovnáte "
     "(Porovnat s protokolem učitele), tím je odhad přesnější."),
    ("Co aplikace umí", "co umis umi funkce prehled vsechno nastroje",
     "Přehled všech funkcí s tlačítkem Spustit: <b>Nápověda → Co aplikace umí</b> nebo odkaz na Úvodu."),
    ("MGEO – limit a kontrola ploch", "mgeo gisoft limit blizko plochy definicni bod popis parcela",
     "Aplikace hlídá jako MGEO i <b>prvky příliš blízko</b> (Limit) a umí <b>kontrolu ploch</b> – každá plocha "
     "má mít jeden popis / definiční bod. Kontrolu ploch zapnete v Nastavení kontrol."),
    ("Kolik mám odevzdání", "odevzdani pocet 5 pokusu",
     "Nejvýš 5. Počítadlo je v okně <b>Připraveno k odevzdání?</b> a na Úvodu."),
    ("Mluvit místo psaní", "mikrofon diktovani hlas mluvit",
     "Klikněte do pole otázky a stiskněte <b>Win+H</b> – Windows přepíše řeč do textu. Pak Enter."),
]


def _norm(s: str) -> list[str]:
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    stop = {"jak", "co", "je", "to", "se", "na", "do", "proc", "udela", "mam", "muze", "jaky", "jake", "kde", "ktery",
            "nebo", "pro", "tak", "by", "si", "mi", "me", "ze", "po", "od", "za", "a"}
    return [w[:5] for w in re.findall(r"[a-z0-9]{2,}", s) if w[:5] not in stop and w not in stop]


def _index():
    items = []
    for t, k, a in FAQ:
        items.append((t, k, a, "Časté otázky"))
    try:
        from .tips import TIPS
        for cat, name, keys, html, _img in TIPS:
            items.append((name, keys, html, f"Rychlé tipy – {cat}"))
    except Exception:  # noqa: BLE001
        pass
    try:
        from .help_topics import TOPICS
        for cid, (title, text) in TOPICS.items():
            items.append((title, cid.replace("_", " "), text, "Vysvětlení chyb"))
    except Exception:  # noqa: BLE001
        pass
    return items


def _project_items(win) -> list:
    """Položky z otevřeného projektu: pravidla Směrnice a pokyny z Wordu se zadáním."""
    out = []
    p = getattr(win, "project", None) if win is not None else None
    if p is None:
        return out
    for r in p.rules.pravidla[:600]:
        parts = [f"vrstva <b>{escape(str(r.hladina))}</b>" if r.hladina else "",
                 f"barva <b>{escape(str(r.barva))}</b>" if r.barva is not None else "",
                 f"styl <b>{escape(str(r.styl_cary))}</b>" if r.styl_cary else "",
                 f"tloušťka <b>{escape(str(r.tloustka))}</b>" if r.tloustka is not None else "",
                 f"buňka <b>{escape(str(r.blok))}</b>" if r.blok else "",
                 f"písmo <b>{escape(str(r.font))}</b>" if r.font else "",
                 f"výška textu <b>{r.vyska_textu:g}</b>" if r.vyska_textu else ""]
        html = "Podle pravidel projektu: " + ", ".join(x for x in parts if x) + "."
        out.append((r.nazev or r.kod, f"{r.kod} {r.hladina or ''} barva vrstva styl tloustka", html,
                    "Směrnice (pravidla projektu)"))
    try:
        from ..importer.dokument import read_document, requirements
        for a in p.attachments("dokumenty"):
            if a.path.suffix.lower() in (".doc", ".docx", ".odt", ".rtf"):
                for q in requirements(read_document(a.path)):
                    out.append((f"{q.druh}: {q.hodnota}" if q.hodnota else q.druh, q.druh, escape(q.veta),
                                f"Zadání – {a.name}"))
    except Exception:  # noqa: BLE001
        pass
    return out


def answer(question: str, limit: int = 3, win=None):
    """Najde nejlepší odpovědi: [(nadpis, html, zdroj)]."""
    q = set(_norm(question))
    if not q:
        return []
    scored = []
    for title, keys, html, src in _index() + _project_items(win):
        t_words, k_words = set(_norm(title)), set(_norm(keys))
        body = set(_norm(re.sub(r"<[^>]+>", " ", html)))
        sc = 3 * len(q & t_words) + 2 * len(q & k_words) + 0.5 * len(q & body)
        if sc > 0:
            scored.append((sc, title, html, src))
    scored.sort(key=lambda t: -t[0])
    return [(t, h, s) for _, t, h, s in scored[:limit]]


def _special(text: str, win):
    """Otázky na stav práce a na vybranou chybu – odpověď z aktuálního stavu aplikace."""
    t = " ".join(_norm(text))
    if win is None:
        return None
    iss = win.issue_panel.current_issue() if hasattr(win, "issue_panel") else None
    if iss is not None and re.search(r"\b(oprav|tahle|tato|tuhle|vybra|chyba|tohle)", t):
        from ..navody import navod
        from .help_topics import TOPICS
        h = navod(iss) or ""
        extra = TOPICS.get(iss.check_id, ("", ""))[1]
        return (f"Vybraná chyba #{iss.number}: {escape(iss.check_name)}",
                f"<i>{escape(iss.message)}</i><br><b>Jak opravit:</b> {escape(h)}"
                + (f"<br><br>{extra}" if extra else ""), "Vybraná chyba")
    if re.search(r"\b(kolik|stav|zbyva|hotov)", t):
        issues = getattr(win, "issues", []) or []
        if not issues:
            return ("Stav", "Výkres zatím nebyl zkontrolován – otevřete ho a stiskněte <b>Zkontrolovat</b> (F5).",
                    "Stav práce")
        from ..skore import compute_score
        sk = compute_score(issues, bool(win.project and win.project.rules.pravidla))
        todo = [i for i in issues if i.state == "nová" and i.severity.value != "info"]
        return ("Stav", f"K opravě zbývá <b>{len(todo)}</b> (chyby {sum(1 for i in todo if i.severity.value == 'chyba')}"
                f", varování {sum(1 for i in todo if i.severity.value == 'varování')}). Skóre <b>{sk.hodnota}</b>/100 "
                f"– {escape(sk.popis)}.", "Stav práce")
    if re.search(r"\b(dal|dalsi|zacit|dele|postu)", t):
        p = win.project
        if p is not None and not p.rules.pravidla:
            step = "Nahrajte Směrnici a Word se zadáním do záložky <b>Zadání</b>."
        elif getattr(win, "drawing", None) is None:
            step = "Otevřete výkres (DXF uložený z MicroStationu) – tlačítko <b>Otevřít</b>."
        elif not getattr(win, "issues", None):
            step = "Spusťte <b>Zkontrolovat</b> (F5)."
        else:
            step = ("Procházejte chyby (F8 = další), opravujte je v MicroStationu, uložte DXF a aplikace zkontroluje "
                    "znovu. Nakonec <b>Připraveno k odevzdání?</b>")
        return ("Co dál", step, "Stav práce")
    return None


class PoradcePanel(QWidget):
    def __init__(self, parent=None, win=None):
        super().__init__(parent)
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(False)
        self.chat.setHtml("<p><b>Poradce</b> – zeptejte se, např. <i>jak udělat kolmici</i>, <i>jaká barva má "
                          "plot</i>, <i>jak opravit tuhle chybu</i>, <i>kolik mi zbývá</i>, <i>co dál</i>.</p>"
                          "<p style='color:#6B7280'>🎤 Mluvit: klikněte do pole a stiskněte <b>Win+H</b>.</p>")
        lay.addWidget(self.chat, 1)
        row = QHBoxLayout()
        self.q = QLineEdit()
        self.q.setPlaceholderText("Na co se chcete zeptat?")
        self.q.returnPressed.connect(self.ask)
        b = QPushButton("Zeptat se")
        b.setProperty("primarni", True)
        b.clicked.connect(self.ask)
        mic = QPushButton("🎤")
        mic.setToolTip("Diktování Windows: klikněte do pole a stiskněte Win+H")
        mic.setFixedWidth(40)
        mic.clicked.connect(self._mic)
        row.addWidget(self.q, 1)
        row.addWidget(mic)
        row.addWidget(b)
        lay.addLayout(row)
        self.hint = QLabel("Odpovědi jsou z návodů v aplikaci (funguje bez internetu).")
        self.hint.setObjectName("karta_popis")
        lay.addWidget(self.hint)
        self._html = []

    def _mic(self):
        self.q.setFocus()
        self.hint.setText("Stiskněte Win+H a mluvte – text se napíše do pole, pak Enter.")

    def ask(self):
        text = self.q.text().strip()
        if not text:
            return
        sp = _special(text, self.win)
        res = [sp] if sp else answer(text, win=self.win)
        out = f"<p style='text-align:right'><b>Vy:</b> {escape(text)}</p>"
        if not res:
            out += ("<p>Na tohle odpověď v návodech nemám. Zkuste jiná slova, nebo <b>Nápověda → Rychlé tipy</b> "
                    "a <b>Co znamenají chyby</b>.</p>")
        else:
            t, h, s = res[0]
            out += f"<div style='background:#EFF6FF;border-radius:6px;padding:6px'><b>{escape(t)}</b> " \
                   f"<span style='color:#6B7280'>({escape(s)})</span><br>{h}</div>"
            if len(res) > 1:
                out += "<p style='color:#6B7280'>Podobné: " + ", ".join(escape(r[0]) for r in res[1:]) + "</p>"
        self._html.append(out)
        self.chat.setHtml("".join(self._html[-8:]))
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())
        self.q.clear()
