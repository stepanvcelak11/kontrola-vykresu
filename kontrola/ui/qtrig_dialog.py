"""Okno „QTrig“: body a zápisníky z terénní aplikace QTrig do Výpočtů (cloud firmy nebo soubor)."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout)

from .. import qtrig as Q


def _nastaveni() -> QSettings:
    return QSettings("KontrolaVykresu", "KontrolaVykresu")


class QTrigDialog(QDialog):
    def __init__(self, page, klient: Q.Klient | None = None, parent=None):
        super().__init__(parent or page)
        self.page = page
        self.setWindowTitle("QTrig – body a zápisníky z terénu")
        self.setMinimumWidth(560)
        s = _nastaveni()
        self.klient = klient or Q.Klient(token=s.value("qtrig/token", "") or None)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("V terénu měříte a zapisujete v QTrig, v kanceláři tady jedním tlačítkem stáhnete "
                             "body zakázky do seznamu souřadnic (S-JTSK, stejný převod jako v QTrig – sedí na mm). "
                             "V QTrig se nic nemění."))
        # --- cloud
        g = QGroupBox("Účet QTrig")
        f = QFormLayout(g)
        self.kod = QLineEdit(s.value("qtrig/kod", ""))
        self.kod.setPlaceholderText("kód účtu – stejný jako při přihlášení v QTrig")
        self.jmeno = QLineEdit(s.value("qtrig/jmeno", ""))
        self.jmeno.setPlaceholderText("jméno uživatele ve firmě")
        self.stary_ucet = QCheckBox("Starší firemní účet (kód firmy + jméno)")
        self.stary_ucet.setChecked(bool(s.value("qtrig/jmeno", "")))
        self.heslo = QLineEdit()
        self.heslo.setEchoMode(QLineEdit.Password)
        self.b_login = QPushButton("Přihlásit")
        r = QHBoxLayout()
        r.addWidget(self.heslo, 1)
        r.addWidget(self.b_login)
        f.addRow("Kód účtu", self.kod)
        f.addRow("Heslo", r)
        f.addRow(self.stary_ucet)
        f.addRow("Jméno", self.jmeno)
        self._jmeno_popisek = f.labelForField(self.jmeno)
        self.stary_ucet.toggled.connect(self._ukaz_jmeno)
        self._ukaz_jmeno(self.stary_ucet.isChecked())
        self.zakazka = QComboBox()
        self.zakazka.setEditable(False)  # po přihlášení se nabídnou všechny zakázky účtu
        self.zakazka.setToolTip("Zakázka se páruje podle názvu – jako mezi mobily v QTrig")
        self.b_obnov = QPushButton("↻")
        self.b_obnov.setToolTip("Načíst seznam zakázek ze serveru")
        r2 = QHBoxLayout()
        r2.addWidget(self.zakazka, 1)
        r2.addWidget(self.b_obnov)
        f.addRow("Zakázka", r2)
        self.smazat = QCheckBox("Body smazané v QTrig smazat i tady (jen body, které přišly z QTrig)")
        self.smazat.setChecked(s.value("qtrig/smazat", "1") == "1")
        f.addRow(self.smazat)
        self.hlidat = QCheckBox("Hlídat zakázku – stahovat nové body každou minutu, dokud je okno otevřené")
        f.addRow(self.hlidat)
        self.b_sync = QPushButton("Stáhnout body zakázky")
        self.b_sync.setDefault(True)
        self.b_odhlas = QPushButton("Odhlásit")
        r3 = QHBoxLayout()
        r3.addWidget(self.b_sync, 1)
        r3.addWidget(self.b_odhlas)
        f.addRow(r3)
        f.addRow(QLabel("<span style='color:gray'>Stačí kód účtu a heslo jako v QTrig – zobrazí se všechny zakázky z telefonu "
                        "(ze zálohy účtu, kterou QTrig posílá sám denně a po každých 20 bodech). Nejnovější body: "
                        "v QTrig Nastavení → Záloha a údržba → Zálohovat teď, pak tady ↻. Heslo se neukládá.</span>"))
        lay.addWidget(g)
        # --- soubor
        g2 = QGroupBox("Export z QTrig (soubor)")
        v2 = QVBoxLayout(g2)
        v2.addWidget(QLabel("Body (JSON „moje_body_….json“, CSV/TXT), nivelační zápisník nebo zápisník směrů (CSV)."))
        self.b_soubor = QPushButton("Načíst soubor z QTrig…")
        v2.addWidget(self.b_soubor)
        lay.addWidget(g2)
        self.stav = QLabel()
        self.stav.setWordWrap(True)
        self.stav.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.stav)
        zav = QPushButton("Zavřít")
        zav.clicked.connect(self.close)
        lay.addWidget(zav, 0, Qt.AlignRight)
        self.b_login.clicked.connect(lambda: self.prihlas())
        self.heslo.returnPressed.connect(lambda: self.prihlas())
        self.b_obnov.clicked.connect(lambda: self.obnov_zakazky())
        self.b_sync.clicked.connect(lambda: self.stahni())
        self.b_odhlas.clicked.connect(self.odhlas)
        self.b_soubor.clicked.connect(lambda: self.nacti_soubor())
        self._t = QTimer(self)
        self._t.setInterval(60_000)
        self._t.timeout.connect(lambda: self.stahni(tise=True))
        self.hlidat.toggled.connect(lambda on: self._t.start() if on else self._t.stop())
        posledni = s.value("qtrig/zakazka", "")
        if posledni:
            self.zakazka.addItem(posledni, Q.klic_zakazky(posledni))
        self._obnov_stav()

    def vyber_zakazku(self, nazev: str) -> None:
        """Zvolí zakázku podle názvu (nový projekt se jmenuje jako zakázka); neznámou přidá."""
        cil = (nazev or "").strip().lower()
        for i in range(self.zakazka.count()):
            d = self.zakazka.itemData(i)
            jm = d.get("name") if isinstance(d, dict) else self.zakazka.itemText(i)
            if (jm or "").strip().lower() == cil:
                self.zakazka.setCurrentIndex(i)
                return
        self.zakazka.addItem(nazev, {"key": Q.klic_zakazky(nazev), "name": nazev, "zdroj": "firma", "n": None})
        self.zakazka.setCurrentIndex(self.zakazka.count() - 1)

    def _ukaz_jmeno(self, on: bool):
        self.jmeno.setVisible(on)
        if self._jmeno_popisek is not None:
            self._jmeno_popisek.setVisible(on)

    # ------------------------------------------------------------ stav
    def _obnov_stav(self, text: str | None = None, warn: bool = False):
        prihlasen = bool(self.klient.token)
        self.b_sync.setEnabled(prihlasen)
        self.b_obnov.setEnabled(prihlasen)
        self.b_odhlas.setEnabled(prihlasen)
        if text is None:
            text = ("Přihlášeno" + (f" jako {self.klient.uzivatel}" if self.klient.uzivatel else "") + "."
                    if prihlasen else "Nepřihlášeno – zadejte kód a heslo účtu QTrig.")
        self.stav.setText(f"<span style='color:{'#d97706' if warn else 'gray'}'>{text}</span>")

    def _cekej(self, fn):
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            return fn()
        finally:
            QGuiApplication.restoreOverrideCursor()

    # ------------------------------------------------------------ cloud
    def prihlas(self, heslo: str | None = None) -> bool:
        kod = self.kod.text().strip()
        heslo = self.heslo.text() if heslo is None else heslo
        if not kod or not heslo:
            self._obnov_stav("Zadejte kód a heslo.", True)
            return False
        try:
            jmeno = self.jmeno.text() if self.stary_ucet.isChecked() else ""
            self._cekej(lambda: self.klient.prihlas(kod, heslo, jmeno))
        except Q.ChybaQTrig as e:
            self._obnov_stav(str(e), True)
            return False
        self.heslo.clear()
        s = _nastaveni()
        s.setValue("qtrig/kod", kod)
        s.setValue("qtrig/jmeno", self.jmeno.text().strip() if self.stary_ucet.isChecked() else "")
        s.setValue("qtrig/token", self.klient.token)
        self._obnov_stav()
        self.obnov_zakazky()
        return True

    def odhlas(self):
        self.klient.token = None
        self.hlidat.setChecked(False)
        _nastaveni().remove("qtrig/token")
        self._obnov_stav()

    def obnov_zakazky(self) -> list[dict]:
        """Zakázky účtu: ze zálohy účtu (všechny zakázky a body z telefonu – QTrig ji posílá sám) a ze sdílení
        ve firmě. Vrací seznam položek {key, name, zdroj}."""
        polozky, chyby = [], []
        self._zaloha = {}
        try:
            zal, ts = self._cekej(self.klient.zaloha_uctu)
            for z in Q.zakazky_ze_zalohy(zal):
                self._zaloha[z["key"]] = z
                polozky.append({"key": z["key"], "name": z["name"], "zdroj": "zaloha", "n": len(z["body"])})
            self._zaloha_cas = ts
        except Q.ChybaQTrig as e:
            chyby.append(str(e))
            if not self.klient.token:
                self._chyba(e)
                return []
        try:
            jmena = {p["name"].strip().lower() for p in polozky}
            for j in self._cekej(self.klient.zakazky):
                nm = j.get("name") or j.get("key")
                if nm and nm.strip().lower() not in jmena:
                    polozky.append({"key": j.get("key"), "name": nm, "zdroj": "firma", "n": None})
        except Q.ChybaQTrig as e:
            if not self.klient.token:
                self._chyba(e)
                return []
        akt = self._zvolena_zakazka()
        self.zakazka.clear()
        self.zakazka.setEditable(not polozky)
        for p in sorted(polozky, key=lambda p: p["name"].lower()):
            text = p["name"] + (f"   ({p['n']} bodů)" if p["n"] is not None else "   (sdílená ve firmě)")
            self.zakazka.addItem(text, p)
        if akt:
            self.vyber_zakazku(akt)
        if polozky:
            kdy = ""
            if getattr(self, "_zaloha_cas", 0):
                import datetime as _dt
                kdy = " Záloha z telefonu: " + _dt.datetime.fromtimestamp(self._zaloha_cas / 1000).strftime("%d. %m. %H:%M") + "."
            self._obnov_stav(f"Přihlášeno – {len(polozky)} zakázek, vyberte jednu a stáhněte body.{kdy}")
        else:
            self._obnov_stav(((chyby[0] + " ") if chyby else "") + "Zatím tu nejsou žádné zakázky.", True)
        return polozky

    def _zvolena_zakazka(self) -> str:
        d = self.zakazka.currentData()
        if isinstance(d, dict):
            return d.get("name", "")
        return self.zakazka.currentText().strip()

    def _chyba(self, e):
        if not self.klient.token:
            _nastaveni().remove("qtrig/token")
            self.hlidat.setChecked(False)
        self._obnov_stav(str(e), True)

    def _soubor_stavu(self) -> Path | None:
        p = getattr(self.page, "_path", None)
        return Path(p).with_name("qtrig_sync.json") if p is not None else None

    def _nacti_stav(self, klic: str) -> Q.StavSync:
        f = self._soubor_stavu()
        try:
            d = json.loads(f.read_text(encoding="utf-8")) if f is not None and f.exists() else {}
        except (OSError, ValueError):
            d = {}
        st = d.get(klic)
        return Q.StavSync(klic, int(st.get("kurzor", 0)), dict(st.get("body", {}))) if st else Q.StavSync(klic)

    def _uloz_stav(self, stav: Q.StavSync):
        f = self._soubor_stavu()
        if f is None:
            return
        try:
            d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except (OSError, ValueError):
            d = {}
        d[stav.klic] = asdict(stav)
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def stahni(self, tise: bool = False) -> tuple[int, int, int] | None:
        nazev = self._zvolena_zakazka()
        if not nazev:
            self._obnov_stav("Vyberte nebo napište zakázku.", True)
            return None
        d = self.zakazka.currentData()
        if isinstance(d, dict) and d.get("zdroj") == "zaloha":
            if tise:  # hlídání: záloha se obnoví nanejvýš jednou za pár minut
                try:
                    self.obnov_zakazky()
                    self.vyber_zakazku(nazev)
                    d = self.zakazka.currentData()
                except Q.ChybaQTrig:
                    return None
            z = getattr(self, "_zaloha", {}).get(d.get("key")) if isinstance(d, dict) else None
            if z is None:
                self._obnov_stav("Zakázka v záloze není – obnovte seznam (↻).", True)
                return None
            body = list(z["body"])
            stav = self._nacti_stav("zaloha:" + str(d["key"]))
            predtim = set(stav.body)
            smazane = sorted(predtim - {b.cislo for b in body})
            stav.body = {b.cislo: {} for b in body}
        else:
            klic = d.get("key") if isinstance(d, dict) else Q.klic_zakazky(nazev)
            stav = self._nacti_stav(klic)
            try:
                body, smazane, stav = (Q.sync(self.klient, stav, klic) if tise
                                       else self._cekej(lambda: Q.sync(self.klient, stav, klic)))
            except Q.ChybaQTrig as e:
                self._chyba(e)
                return None
        self._uloz_stav(stav)
        _nastaveni().setValue("qtrig/zakazka", nazev)
        _nastaveni().setValue("qtrig/smazat", "1" if self.smazat.isChecked() else "0")
        vysl = Q.sloucit(self.page.seznam, body, smazane, self.smazat.isChecked())
        if any(vysl):
            self.page.model.refresh()
            self.page._after_change()
        nove, zmenene, smaz = vysl
        cas = __import__("datetime").datetime.now().strftime("%H:%M")
        text = (f"{cas} – zakázka „{nazev}“: {len(body)} bodů v QTrig; nové {nove}, změněné {zmenene}, smazané {smaz}."
                if any(vysl) else f"{cas} – zakázka „{nazev}“: {len(body)} bodů, nic nového.")
        self._obnov_stav(text)
        if any(vysl):
            self.page.message("QTrig: " + text)
        return vysl

    # ------------------------------------------------------------ soubor
    def nacti_soubor(self, cesta: str | None = None):
        if cesta is None:
            cesta, _ = QFileDialog.getOpenFileName(self, "Export z QTrig", "",
                                                   "Export QTrig (*.json *.csv *.txt);;Vše (*)")
        if not cesta:
            return None
        try:
            obsah = Q.nacti_soubor(cesta)
        except (Q.ChybaQTrig, OSError, ValueError) as e:
            if Path(cesta).suffix.lower() in (".csv", ".txt"):  # body „název;Y;X;Z;kód“ – běžný import
                self.close()
                return self.page.import_dialog(cesta)
            self._obnov_stav(f"Soubor nejde načíst: {e}", True)
            return None
        jmeno = Path(cesta).name
        if isinstance(obsah, list):
            nove, zmenene, _s = Q.sloucit(self.page.seznam, obsah)
            self.page.model.refresh()
            self.page._after_change()
            self._obnov_stav(f"{jmeno}: {len(obsah)} bodů – nové {nove}, změněné {zmenene}.")
        elif isinstance(obsah, Q.NivelaceQTrig):
            try:
                vysky, prot = Q.nivelace_vypocet(obsah)
            except Q.ChybaQTrig as e:
                self._obnov_stav(str(e), True)
                return None
            self.page.protokol_append(prot)
            n = 0
            for bod, h in vysky:
                if self.page.seznam.najdi(bod) is not None and self.page.seznam.uprav(bod, z=round(h, 4)):
                    n += 1
            if n:
                self.page.model.refresh()
                self.page._after_change()
            self._obnov_stav(f"{jmeno}: nivelace {len(vysky)} bodů, výšky doplněny u {n} bodů seznamu; "
                             "výpočet je v protokolu.")
        else:
            st = Q.smery_na_stanovisko(obsah)
            z = self.page.zapisnik
            z.nastav(z.stanoviska + [st])
            z.seznam_st.setCurrentRow(len(z.stanoviska) - 1)
            self.page.tabs.setCurrentWidget(z)
            self._obnov_stav(f"{jmeno}: stanovisko {st.bod} s {len(st.detail)} záměrami je v Zápisníku – "
                             "doplňte výšku přístroje a přesuňte záměry na dané body do orientace.")
        return obsah

    def closeEvent(self, e):  # noqa: N802
        self._t.stop()
        super().closeEvent(e)
