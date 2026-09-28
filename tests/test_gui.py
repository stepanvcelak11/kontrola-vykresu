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
