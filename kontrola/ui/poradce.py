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


def answer(question: str, limit: int = 3):
    """Najde nejlepší odpovědi: [(nadpis, html, zdroj)]."""
    q = set(_norm(question))
    if not q:
        return []
    scored = []
    for title, keys, html, src in _index():
        t_words, k_words = set(_norm(title)), set(_norm(keys))
        body = set(_norm(re.sub(r"<[^>]+>", " ", html)))
        sc = 3 * len(q & t_words) + 2 * len(q & k_words) + 0.5 * len(q & body)
        if sc > 0:
            scored.append((sc, title, html, src))
    scored.sort(key=lambda t: -t[0])
    return [(t, h, s) for _, t, h, s in scored[:limit]]


class PoradcePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(False)
        self.chat.setHtml("<p><b>Poradce</b> – napište otázku, např. <i>jak udělat kolmici</i>, <i>co je "
                          "přetažená linie</i>, <i>proč vrstva 58 není ve Směrnici</i>.</p>"
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
        res = answer(text)
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
