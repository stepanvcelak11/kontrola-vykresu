"""Rozcestník – úvodní obrazovka celé aplikace (zapíná se na ní vždy).

Aplikace má v sobě několik programů (Výpočty jako Groma, CAD jako MicroStation, Kokeš, Kontrola výkresu).
Tady se vybere projekt, nebo se založí nový, a zaškrtne se, které části procesu v něm budou: celý proces
(výpočet → kreslení → kontrola), nebo jen některé. Levá lišta pak ukazuje jen zvolené části."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtWidgets import (QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget)

# proces → (název, popis, stránky levé lišty, barva)
PROCESY = {
    "vypocty": ("Výpočty", "seznam souřadnic, zápisník, úlohy jako v Gromě", ["vypocty"], "#7C3AED"),
    "kresleni": ("Kreslení", "CAD jako MicroStation – MultiScale, Pasport, TM", ["cad"], "#EA580C"),
    "kokes": ("Kokeš", "čísla bodů KN, kreslící klíče, katastr", ["kokes"], "#059669"),
    "kontrola": ("Kontrola výkresu", "zadání, kontrola výkresu, protokol, odevzdání", ["uvod", "vykres", "zadani"],
                 "#2563EB"),
}
KLIC_PRI_STARTU = "start/rozcestnik"


def stranky_procesu(procesy) -> set[str]:
    """Stránky levé lišty pro zvolené procesy (prázdné / neznámé = všechny)."""
    procesy = [p for p in (procesy or []) if p in PROCESY]
    if not procesy:
        return {s for _n, _p, st, _b in PROCESY.values() for s in st}
    return {s for p in procesy for s in PROCESY[p][2]}


def seznam_projektu(win) -> list[tuple[str, Path, dict]]:
    """Projekty ve výchozí složce (a vedle otevřeného) seřazené od naposledy uloženého: (uloženo, složka, meta)."""
    import yaml

    from ..project import default_projects_dir
    cur = getattr(win, "project", None)
    dirs = {default_projects_dir()}
    if cur is not None:
        dirs.add(Path(cur.root).parent)
    out = []
    for d in dirs:
        if not d.is_dir():
            continue
        for sub in d.iterdir():
            f = sub / "projekt.yaml"
            if not f.is_file():
                continue
            r = sub.resolve()
            if cur is not None and Path(cur.root).resolve() == r:
                meta = cur.meta
            else:
                try:
                    meta = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                except Exception:  # noqa: BLE001
                    continue
            prazdny = not (meta.get("vykres_zdroj") or meta.get("vykres") or meta.get("historie")
                           or meta.get("odevzdani") or meta.get("procesy"))
            if prazdny and not (cur is not None and Path(cur.root).resolve() == r):
                continue
            out.append((str(meta.get("ulozeno", "")), r, meta))
    out.sort(key=lambda t: t[0], reverse=True)
    return out


def _karta(titul: str, popis: str = "") -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("karta")
    v = QVBoxLayout(f)
    v.setContentsMargins(16, 14, 16, 14)
    v.setSpacing(8)
    t = QLabel(titul)
    t.setObjectName("krok_nadpis")
    v.addWidget(t)
    if popis:
        p = QLabel(popis)
        p.setObjectName("karta_popis")
        p.setWordWrap(True)
        v.addWidget(p)
    return f, v


class Rozcestnik(QScrollArea):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setObjectName("rozcestnik")
        obsah = QWidget()
        obsah.setObjectName("rozcestnik_obsah")
        lay = QVBoxLayout(obsah)
        lay.setContentsMargins(26, 20, 26, 20)
        lay.setSpacing(14)
        # ---- hlavička
        hero = QFrame()
        hero.setObjectName("hero")
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(22, 14, 22, 14)
        logo = QLabel()
        try:
            from PySide6.QtGui import QPixmap

            from ..resources import resource_path
            pm = QPixmap(str(resource_path("ikona.png")))
            if not pm.isNull():
                logo.setPixmap(pm.scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:  # noqa: BLE001
            pass
        hl.addWidget(logo)
        tb = QVBoxLayout()
        nad = QLabel("Dobrý den – v čem dnes budete pracovat?")
        nad.setObjectName("uvod_nadpis")
        nad.setWordWrap(True)
        tb.addWidget(nad)
        self.podnadpis = QLabel()
        self.podnadpis.setObjectName("uvod_podnadpis")
        tb.addWidget(self.podnadpis)
        hl.addLayout(tb, 1)
        lay.addWidget(hero)

        radek = QHBoxLayout()
        radek.setSpacing(14)
        # ---- projekty
        k, v = _karta("Pokračovat v projektu", "Dvojklik otevře projekt na části, kde jste skončili. Pravé "
                                               "tlačítko: přejmenovat, složka, skrýt.")
        self.projekty = QListWidget()
        self.projekty.setObjectName("seznam_projektu")
        self.projekty.setMinimumHeight(220)
        self.projekty.setIconSize(QSize(18, 18))
        self.projekty.itemDoubleClicked.connect(lambda it: self.otevri(it.data(Qt.UserRole)))
        self.projekty.currentItemChanged.connect(lambda *_a: self._vybrany_zmenen())
        self.projekty.setContextMenuPolicy(Qt.CustomContextMenu)
        self.projekty.customContextMenuRequested.connect(self._nabidka)
        v.addWidget(self.projekty, 1)
        r = QHBoxLayout()
        self.b_otevrit = QPushButton("Otevřít projekt")
        self.b_otevrit.setProperty("primarni", True)
        self.b_otevrit.clicked.connect(lambda: self.otevri(self._vybrany()))
        b_jiny = QPushButton("Jiný ze složky…")
        b_jiny.clicked.connect(lambda: win.open_project_dialog())
        r.addWidget(self.b_otevrit)
        r.addWidget(b_jiny)
        r.addStretch(1)
        v.addLayout(r)
        radek.addWidget(k, 5)
        # ---- nový projekt / části procesu
        k, v = _karta("Nový projekt", "Zaškrtněte, které části budete dělat. Levá lišta pak ukáže jen je "
                                      "(změnit jde kdykoli tady).")
        self.nazev = QLineEdit()
        self.nazev.setPlaceholderText("Název, např. Mapování Husovice – úloha 3")
        v.addWidget(self.nazev)
        self.cely = QCheckBox("Celý proces: výpočet → kreslení → kontrola")
        self.cely.setStyleSheet("font-weight:700")
        v.addWidget(self.cely)
        self.zaskrt: dict[str, QCheckBox] = {}
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        for i, (kl, (jm, popis, _st, barva)) in enumerate(PROCESY.items()):
            c = QCheckBox(jm)
            c.setChecked(True)
            c.setToolTip(popis)
            c.setStyleSheet(f"QCheckBox {{ color: {barva}; font-weight: 600; }}")
            lbl = QLabel(popis)
            lbl.setObjectName("karta_popis")
            lbl.setWordWrap(True)
            g.addWidget(c, i, 0)
            g.addWidget(lbl, i, 1)
            self.zaskrt[kl] = c
            c.toggled.connect(lambda *_a: self._sync_cely())
        g.setColumnStretch(1, 1)
        v.addLayout(g)
        self.cely.setChecked(True)
        self.cely.toggled.connect(self._cely_prepnut)
        r = QHBoxLayout()
        self.b_zalozit = QPushButton("Založit projekt")
        self.b_zalozit.setProperty("primarni", True)
        self.b_zalozit.clicked.connect(lambda: self.zaloz())
        self.b_pouzit = QPushButton("Použít pro otevřený projekt")
        self.b_pouzit.setToolTip("Části procesu otevřeného projektu – levá lišta ukáže jen zaškrtnuté")
        self.b_pouzit.clicked.connect(lambda: self.pouzij())
        r.addWidget(self.b_zalozit)
        r.addWidget(self.b_pouzit)
        r.addStretch(1)
        v.addLayout(r)
        v.addStretch(1)
        radek.addWidget(k, 4)
        lay.addLayout(radek, 1)
        # ---- rovnou do programu
        k, v = _karta("Rovnou do programu", "Bez změny projektu – jen otevře danou část aplikace.")
        g = QHBoxLayout()
        g.setSpacing(10)
        from .theme import icon
        for stranka, jm, popis, barva in (("vypocty", "Výpočty", "jako Groma", "#7C3AED"),
                                          ("cad", "CAD", "jako MicroStation", "#EA580C"),
                                          ("kokes", "Kokeš", "katastr a KN", "#059669"),
                                          ("vykres", "Kontrola", "výkresu", "#0D9488"),
                                          ("zadani", "Zadání", "Směrnice, pokyny", "#D97706")):
            b = QToolButton()
            b.setObjectName("dlazdice")
            b.setText(f"{jm}\n{popis}")
            b.setIcon(icon(stranka, barva))
            b.setIconSize(QSize(28, 28))
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setMinimumSize(120, 84)
            b.setSizePolicy(b.sizePolicy().horizontalPolicy().Expanding, b.sizePolicy().verticalPolicy())
            from PySide6.QtGui import QColor
            c = QColor(barva)
            rgb = f"{c.red()}, {c.green()}, {c.blue()}"
            b.setStyleSheet(f"QToolButton#dlazdice {{ border: 1px solid rgba({rgb}, 90); border-radius: 10px; "
                            f"padding: 8px; font-weight: 600; background: rgba({rgb}, 12); }} "
                            f"QToolButton#dlazdice:hover {{ background: rgba({rgb}, 36); border-color: {barva}; }}")
            b.clicked.connect(lambda _c=False, s=stranka: win.show_page(s))
            g.addWidget(b)
        v.addLayout(g)
        lay.addWidget(k)
        self.pri_startu = QCheckBox("Při spuštění aplikace ukázat tento rozcestník")
        self.pri_startu.setChecked(QSettings("KontrolaVykresu", "KontrolaVykresu").value(KLIC_PRI_STARTU, True,
                                                                                          type=bool))
        self.pri_startu.toggled.connect(lambda on: QSettings("KontrolaVykresu", "KontrolaVykresu").setValue(
            KLIC_PRI_STARTU, bool(on)))
        lay.addWidget(self.pri_startu)
        self.setWidget(obsah)
        self.obnov()

    # ------------------------------------------------------------
    def _cely_prepnut(self, on: bool):
        for c in self.zaskrt.values():
            c.blockSignals(True)
            c.setChecked(on)
            c.blockSignals(False)

    def _sync_cely(self):
        self.cely.blockSignals(True)
        self.cely.setChecked(all(c.isChecked() for c in self.zaskrt.values()))
        self.cely.blockSignals(False)

    def zvolene(self) -> list[str]:
        z = [k for k, c in self.zaskrt.items() if c.isChecked()]
        return z or list(PROCESY)

    def _nabidka(self, pos) -> None:
        it = self.projekty.itemAt(pos)
        cesta = it.data(Qt.UserRole) if it is not None else None
        if not cesta:
            return
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("Otevřít", lambda: self.otevri(cesta))
        m.addAction("Přejmenovat…", lambda: self.prejmenuj(cesta))
        m.addAction("Otevřít složku projektu", lambda: self._slozka(cesta))
        m.addSeparator()
        m.addAction("Skrýt ze seznamu", lambda: self.skryj(cesta))
        m.exec(self.projekty.viewport().mapToGlobal(pos))

    def _slozka(self, cesta: str) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(cesta))

    def prejmenuj(self, cesta: str, nazev: str | None = None) -> bool:
        import yaml

        from ..safeio import write_text_atomic
        if nazev is None:
            from PySide6.QtWidgets import QInputDialog
            nazev, ok = QInputDialog.getText(self, "Přejmenovat projekt", "Nový název:")
            if not ok:
                return False
        nazev = (nazev or "").strip()
        if not nazev:
            return False
        cur = getattr(self.win, "project", None)
        if cur is not None and Path(cur.root).resolve() == Path(cesta).resolve():
            cur.meta["nazev"] = nazev
            cur.save()
        else:
            f = Path(cesta) / "projekt.yaml"
            meta = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            meta["nazev"] = nazev
            write_text_atomic(f, yaml.safe_dump(meta, allow_unicode=True, sort_keys=False))
        self.obnov()
        return True

    def skryj(self, cesta: str) -> None:
        """Skryje projekt ze seznamu (složka na disku zůstane)."""
        st = QSettings("KontrolaVykresu", "KontrolaVykresu")
        skryte = st.value("start/skryte", []) or []
        skryte = [skryte] if isinstance(skryte, str) else list(skryte)
        st.setValue("start/skryte", skryte + [str(Path(cesta).resolve())])
        self.obnov()

    def _vybrany(self) -> str | None:
        it = self.projekty.currentItem()
        return it.data(Qt.UserRole) if it is not None else None

    def _vybrany_zmenen(self):
        self.b_otevrit.setEnabled(self._vybrany() is not None)

    def obnov(self):
        cur = getattr(self.win, "project", None)
        self.podnadpis.setText(("Otevřený projekt: <b>" + cur.name + "</b> · " if cur is not None else "")
                               + "Vyberte projekt, založte nový, nebo jděte rovnou do programu.")
        self.projekty.clear()
        from .theme import icon
        skryte = QSettings("KontrolaVykresu", "KontrolaVykresu").value("start/skryte", []) or []
        skryte = {skryte} if isinstance(skryte, str) else set(skryte)
        for ulozeno, r, meta in seznam_projektu(self.win):
            if str(r) in skryte:
                continue
            try:
                kdy = dt.datetime.fromisoformat(ulozeno).strftime("%d.%m. %H:%M") if ulozeno else ""
            except ValueError:
                kdy = ulozeno
            casti = ", ".join(PROCESY[p][0] for p in (meta.get("procesy") or []) if p in PROCESY) or "celý proces"
            vyk = Path(meta.get("vykres_zdroj") or meta.get("vykres") or "").name
            jm = meta.get("nazev") or r.name
            it = QListWidgetItem(icon("vykres"), f"{jm}\n{kdy} · {casti}" + (f" · {vyk}" if vyk else ""))
            it.setData(Qt.UserRole, str(r))
            it.setToolTip(str(r))
            if cur is not None and Path(cur.root).resolve() == r:
                f = it.font()
                f.setBold(True)
                it.setFont(f)
            self.projekty.addItem(it)
        if self.projekty.count():
            self.projekty.setCurrentRow(0)
        else:
            self.projekty.addItem(QListWidgetItem("Zatím žádný projekt – založte nový vpravo."))
            self.projekty.item(0).setFlags(Qt.NoItemFlags)
        self._vybrany_zmenen()
        if cur is not None:
            pr = cur.meta.get("procesy") or list(PROCESY)
            for k, c in self.zaskrt.items():
                c.blockSignals(True)
                c.setChecked(k in pr)
                c.blockSignals(False)
            self._sync_cely()

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self.obnov()

    # ------------------------------------------------------------ akce
    def _prvni_stranka(self, procesy) -> str:
        for p in ("vypocty", "kresleni", "kokes", "kontrola"):
            if p in procesy:
                return {"vypocty": "vypocty", "kresleni": "cad", "kokes": "kokes", "kontrola": "uvod"}[p]
        return "uvod"

    def otevri(self, cesta: str | None) -> bool:
        if not cesta:
            return False
        cur = getattr(self.win, "project", None)
        if cur is None or Path(cur.root).resolve() != Path(cesta).resolve():
            self.win.open_project(cesta)
        p = getattr(self.win, "project", None)
        if p is None:
            return False
        procesy = p.meta.get("procesy") or list(PROCESY)
        self.win.nastav_procesy(procesy)
        posl = p.meta.get("posledni_stranka")
        self.win.show_page(posl if posl in stranky_procesu(procesy) else self._prvni_stranka(procesy))
        return True

    def zaloz(self, nazev: str | None = None) -> bool:
        nazev = (nazev if nazev is not None else self.nazev.text()).strip()
        if not nazev:
            self.nazev.setFocus()
            self.nazev.setPlaceholderText("Zadejte název projektu")
            return False
        procesy = self.zvolene()  # před založením – nový projekt rozcestník obnoví
        self.win.new_project(nazev)
        p = getattr(self.win, "project", None)
        if p is None:
            return False
        p.meta["procesy"] = procesy
        p.save()
        self.win.nastav_procesy(procesy)
        self.nazev.clear()
        self.win.show_page(self._prvni_stranka(procesy))
        return True

    def pouzij(self) -> None:
        p = getattr(self.win, "project", None)
        if p is None:
            return
        p.meta["procesy"] = self.zvolene()
        p.save()
        self.win.nastav_procesy(p.meta["procesy"])
        self.obnov()
