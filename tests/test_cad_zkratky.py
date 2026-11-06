"""Vlastní klávesové zkratky a zkratky příkazového řádku v CAD."""

import pytest

from kontrola.cad import zkratky as Z


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def test_normalizace_klaves():
    assert Z.normalizuj_klavesu("ctrl + f2") == "Ctrl+F2"
    assert Z.normalizuj_klavesu("Shift+Ctrl+a") == "Ctrl+Shift+A"
    assert Z.normalizuj_klavesu("escape") == "Esc"
    assert Z.normalizuj_klavesu("") == ""


def test_nacteni_a_ulozeni():
    assert Z.nacti_zkratky(None)["F2"] == "úsečka"
    assert Z.nacti_zkratky("{rozbité")["F4"] == "polylinie"
    m = Z.nacti_zkratky(Z.uloz({"ctrl+f2": "prvek budovy", "F3": "", "": "x"}))
    assert {k: v for k, v in m.items() if k not in Z.LEVA_RUKA} == {"Ctrl+F2": "prvek budovy"}
    assert Z.nacti_aliasy(Z.uloz({"BU": "prvek budovy"})) == {"bu": "prvek budovy"}


def test_konflikty():
    k = Z.konflikty({"F3": "úsečka", "F5": "text", "F2": "bod"}, {"F5": "Zkontrolovat"})
    assert len(k) == 2 and any("F3" in x and "úchyty" in x for x in k) and any("Zkontrolovat" in x for x in k)
    assert Z.konflikty(Z.VYCHOZI, {"F1": "Nápověda", "F5": "Kontrola", "F11": "Celá obrazovka"}) == []


def test_alias_a_historie():
    al = {"bu": "prvek budovy", "z58": "zhasni vše kromě 58"}
    assert Z.rozbal_alias("bu", al) == "prvek budovy"
    assert Z.rozbal_alias("BU", al) == "prvek budovy"
    assert Z.rozbal_alias("z58", al) == "zhasni vše kromě 58"
    assert Z.rozbal_alias("bu 2", al) == "prvek budovy 2"
    assert Z.rozbal_alias("úsečka", al) == "úsečka"
    h = Z.HistorieRadku()
    for t in ("u", "u", "kr", "", "pl"):
        h.pridej(t)
    assert h.polozky == ["u", "kr", "pl"]
    assert [h.zpet(), h.zpet(), h.zpet(), h.zpet()] == ["pl", "kr", "u", "u"]
    assert [h.vpred(), h.vpred(), h.vpred()] == ["kr", "pl", ""]
    assert Z.nedavne(["a", "b", "c"], "b") == ["b", "a", "c"]


def test_zkratky_v_cad(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtGui import QKeySequence
    from PySide6.QtWidgets import QApplication

    from kontrola.ui.cad_page import CadPage
    from kontrola.ui.cad_zkratky import KLIC_ALIASY, KLIC_ZKRATKY, ZkratkyDialog
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path / "nastaveni"))
    QSettings.setDefaultFormat(QSettings.IniFormat)
    s = QSettings("KontrolaVykresu", "KontrolaVykresu")
    s.remove(KLIC_ZKRATKY)
    s.remove(KLIC_ALIASY)
    c = CadPage()
    c.novy()
    assert c.vlastni_zkratky["F2"] == "úsečka"
    keys = {sc.key().toString(QKeySequence.PortableText) for sc in c._zkratky_sc}
    assert {"F2", "F4", "Ctrl+1", "Shift+D", "Shift+A"} <= keys and "F3" not in keys
    c.zkratka("úsečka")
    assert c._prikaz == "úsečka" or c._gen is not None
    c.zrus()
    # okno: přidat vlastní klávesu a alias, uložit → zapojí se
    d = ZkratkyDialog(c)
    i = d.pridej_radek("Ctrl+Shift+K", "zhasni vše kromě 58")
    d.pridej_alias("uu", "úsečka")
    assert "Ctrl+Shift+K" in d.zkratky()
    d.tab.cellWidget(i, 0).setKeySequence(QKeySequence("F3"))
    assert "F3" in d.konflikt.text()
    d.tab.cellWidget(i, 0).setKeySequence(QKeySequence("Ctrl+Shift+K"))
    d.accept()
    assert c.vlastni_zkratky["Ctrl+Shift+K"] == "zhasni vše kromě 58" and c.vlastni_aliasy == {"uu": "úsečka"}
    assert c._je_prikaz("uu")
    c.zadej("uu")
    assert c._prikaz == "úsečka" or c._gen is not None
    c.zrus()
    # historie řádku šipkami
    c.prikaz.setText("kr")
    c._enter()
    c.zrus()
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    QApplication.sendEvent(c.prikaz, QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.NoModifier))
    assert c.prikaz.text() == "kr"
    # nedávné příkazy v nabídce mezerníku
    m = c.nabidka_naposledy(pozice=False)
    texty = [a.text() for a in m.actions()]
    assert texty[0] == "kr" and "úsečka" in texty and "Klávesové zkratky…" in texty
    # předvolba bez pravidel jen vypíše hlášku
    c.proved("předvolba 3")
    assert "Předvolba 3 není" in c.historie.toPlainText()
    c.close()


def test_leva_ruka_shift_pismena():
    from kontrola.cad import zkratky as Z
    m = Z.nacti_zkratky(None)
    assert m["Shift+D"] == "smaž" and m["Shift+A"] == "úsečka" and m["F2"] == "úsečka"
    # uložené vlastní zkratky levou ruku nepřebijí, jen doplní
    m2 = Z.nacti_zkratky('{"Shift+D": "kopie"}')
    assert m2["Shift+D"] == "kopie" and m2["Shift+Q"] == "zpět"
    assert Z.je_pismeno_se_shiftem("shift+d") and not Z.je_pismeno_se_shiftem("Shift+F2")
    assert Z.konflikty(Z.LEVA_RUKA) == []
