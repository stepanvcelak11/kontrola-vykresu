"""Test grafického okna (offscreen): tlačítka se chovají jako při kliknutí uživatele."""

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from kontrola.project import Project  # noqa: E402

UKAZKA = Path(__file__).resolve().parents[1] / "ukazky" / "ukazkovy_vykres.dxf"


@pytest.fixture
def window(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QMessageBox
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path / "nastaveni"))
    QSettings.setDefaultFormat(QSettings.IniFormat)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    app = QApplication.instance() or QApplication([])
    from kontrola.ui.main_window import MainWindow
    w = MainWindow(Project.create(tmp_path / "projekt", "test"))
    w.show()

    def wait(cond, timeout=60):
        t0 = time.time()
        while not cond() and time.time() - t0 < timeout:
            app.processEvents()
            time.sleep(0.01)
        return cond()
    w._wait = wait
    yield w
    wait(lambda: w.task is None or not w.task.is_running())
    w.close()


def _idle(w):
    return w.task is None or not w.task.is_running()


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_tlacitko_zkontrolovat_funguje_hned(window):
    w = window
    w.load_drawing_file(UKAZKA)
    # „Zkontrolovat“ klikne uživatel ještě během načítání – kontrola se má spustit po načtení
    w.a_check.trigger()
    ok = w._wait(lambda: _idle(w) and w.drawing is not None and len(w.issues) > 0, 20)
    assert ok, (w.drawing, len(w.issues), w.task, w.info_label.text(), getattr(w, "_queued_check", "-"))
    n = len(w.issues)
    w.a_check.trigger()  # druhé kliknutí po dokončení – stejný výsledek, bez pádu
    assert w._wait(lambda: _idle(w))
    assert len(w.issues) == n


def test_odebrani_tabulky_i_s_pravidly(window, tmp_path):
    w = window
    csv = tmp_path / "spatne_zadani.csv"
    csv.write_text("Kód;Název;Hladina\n101;Budova;BUDOVY\n102;Plot;PLOTY\n", encoding="utf-8")
    p = w.project
    rel = p.add_attachment("tabulky", str(csv))
    from kontrola.importer.table import generate_rules, import_table
    td, hi, m = import_table(p.root / rel)
    p.rules.merge(generate_rules(td.rows, hi, m, str(p.root / rel)).rules)
    assert len(p.rules.pravidla) == 2
    assert p.remove_table(rel) == 2
    assert p.rules.pravidla == [] and not (p.root / rel).exists()


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_opraveno_a_ignorovat(window):
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 2)
    p = w.issue_panel
    p.table.selectRow(0)
    first = p.current_issue()
    p.b_fixed.click()
    assert first.state == "opraveno"
    second = p.current_issue()  # výběr sám přeskočí na další nevyřešenou chybu
    assert second is not first and second.state == "nová"
    p.b_ignore.click()
    assert second.state == "ignorovat"
    assert p.cards[None].text() == str(len(w.issues) - 2)
    # stav se uloží do projektu a přežije novou kontrolu
    states = w.project.issue_states()
    assert first.key in states and states[first.key]["stav"] == "opraveno"


def test_nastaveni_kontrol_se_ulozi(window, monkeypatch):
    from PySide6.QtWidgets import QDialog
    from kontrola.checks.base import Severity
    monkeypatch.setattr(QDialog, "exec", lambda self: (self.accept(), 1)[1])
    w = window
    w.a_settings.trigger()
    cs = w.project.config.settings("visici_konce")
    assert isinstance(cs.zavaznost, Severity)
    w.project.save()  # dřív tady padalo: zavaznost byla text z QComboBoxu
    assert (w.project.root / "nastaveni.yaml").exists()


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_rozpracovany_a_vyrez(window):
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0)
    n_full = len(w.issues)
    w.a_wip.trigger()
    assert w.project.config.rozpracovany and w.issue_panel.banner.isVisible() is not None
    assert w._wait(lambda: _idle(w))
    assert len(w.issues) <= n_full
    w.view.scale(8, 8)  # přiblížit – výřez je menší než výkres
    w.a_region.trigger()
    shown = w.issue_panel.proxy.rowCount()
    assert shown <= len(w.issues)
    w.a_region.trigger()
    assert w.issue_panel.proxy.rowCount() == len(w.issues)


def test_editor_pravidel_upravy_se_ulozi(window):
    w = window
    ed = w.zadani.rules_editor
    ed.add_rule()
    geom = ed.table.cellWidget(ed.table.rowCount() - 1, 2)
    geom.setCurrentIndex(2)  # linie – QComboBox vrací text, pravidlo musí dostat GeomType
    ed.table.item(ed.table.rowCount() - 1, 4).setText("3")
    from kontrola.model import GeomType
    r = w.project.rules.pravidla[-1]
    assert r.geometrie == GeomType.LINIE and r.barva == 3
    w.project.save()
    from kontrola.rules import RuleSet
    assert RuleSet.load(w.project.root / "pravidla.yaml").pravidla[-1].geometrie == GeomType.LINIE
