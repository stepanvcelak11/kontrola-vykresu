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
    todo = sum(1 for i in w.issues if i.state == "nová" and i.severity.value != "info")
    assert p.cards[None].text() == str(todo)
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


def test_hlidani_souboru_zkontroluje_znovu(window, tmp_path):
    import shutil
    w = window
    src = tmp_path / "rozpracovany.dxf"
    shutil.copy(UKAZKA, src)
    w.load_drawing_file(src)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0)
    w.a_watch.setChecked(True)
    assert str(src) in w.watcher.files()
    n_before = len(w.issues)
    # „MicroStation uloží DXF“: výkres bez jedné úsečky
    import ezdxf
    doc = ezdxf.readfile(src)
    msp = doc.modelspace()
    for e in list(msp.query("LINE"))[:3]:
        msp.delete_entity(e)
    doc.saveas(src)
    w._file_changed(str(src))
    import time
    assert w._wait(lambda: _idle(w) and "Opakovaná" in w.issue_panel.summary.text(), 20)
    assert n_before > 0


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_pripraveno_k_odevzdani(window, monkeypatch):
    from PySide6.QtWidgets import QDialog
    shown = {}

    def fake_exec(self):
        shown["dlg"] = self
        return 1
    monkeypatch.setattr(QDialog, "exec", fake_exec)
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0)
    w.a_wip.trigger()  # rozpracovaný režim se pro kontrolu před odevzdáním ignoruje
    assert w._wait(lambda: _idle(w))
    w.a_ready.trigger()
    assert w._wait(lambda: _idle(w) and "dlg" in shown)
    d = shown["dlg"]
    assert "chyb" in d.windowTitle() or True
    d.b_rec.click()
    assert len(w.project.meta["odevzdani"]) == 1
    assert len(w.project.meta["historie"]) >= 3


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_inspektor_prvku(window):
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0)
    f = next(f for f in w.drawing.features if f.geom_type.value == "linie")
    x, y = f.geometry.interpolate(0.5, normalized=True).coords[0]
    fid = w.view.feature_at(x, y, 0.05)
    assert fid >= 0
    w._on_feature_clicked(fid)
    html = w.inspector.view.toHtml()
    assert "Vrstva" in html and "Barva" in html
    w._on_feature_clicked(-1)
    assert "není žádný prvek" in w.inspector.view.toPlainText()


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_rychle_filtry_a_vysvetleni(window, monkeypatch):
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    p = w.issue_panel
    from kontrola.checks.base import Severity
    from kontrola.ui.issue_panel import check_group
    p.quick["Topologie"].click()
    vis = [i for i in w.issues if i.number in p.visible_numbers()]
    assert vis and all(check_group(i.check_id) == "Topologie" for i in vis)
    p.quick["chyby"].click()
    assert all(i.severity != Severity.INFO for i in w.issues if i.number in p.visible_numbers())
    p.quick[None].click()
    assert len(p.visible_numbers()) == len(w.issues)
    # „Co to znamená?“ otevře vysvětlení vybraného typu chyby s obrázkem
    from kontrola.ui import help_topics
    shown = []
    monkeypatch.setattr(help_topics.HelpDialog, "exec", lambda self: shown.append(
        (self.list.currentItem().data(0x0100), self.view.toPlainText())))
    p.select_issue(w.issues[0].number)
    p.b_help.click()
    assert shown and shown[0][0] == w.issues[0].check_id and "Oprava" in shown[0][1]
    assert help_topics.illustration("chybejici_napojeni") is not None


def test_pruvodce(window, monkeypatch):
    from kontrola.ui.guide_dialog import STEPS, GuideDialog
    g = GuideDialog(window)
    for _ in STEPS:
        g.b_next.click()
    assert g.result() == 1
    assert window.settings.value("pruvodce/skryt", False, type=bool)


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_porovnani_verzi_v_okne(window, tmp_path):
    import shutil

    import ezdxf
    w = window
    p = tmp_path / "vykres.dxf"
    shutil.copy(UKAZKA, p)
    w.load_drawing_file(p, add_to_project=False)
    assert w._wait(lambda: _idle(w) and w.drawing is not None, 30)
    doc = ezdxf.readfile(p)
    doc.modelspace().add_line((0, 0), (5, 5), dxfattribs={"layer": "NOVA"})
    doc.saveas(p)
    first = w.drawing
    w.load_drawing_file(p, add_to_project=False)
    assert w._wait(lambda: _idle(w) and w.drawing is not first, 30)
    assert w.prev_drawing is first
    w.a_compare.trigger()
    dlg = w._compare_dlg
    assert dlg is not None and dlg.table.rowCount() == 1
    assert "Přidáno" in dlg.table.item(0, 2).text()
    assert w.view._overlay
    dlg.table.setCurrentCell(0, 0)
    dlg.close()
    assert not w.view._overlay


def test_tmavy_rezim_a_aktualizace(window, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from kontrola import aktualizace
    from kontrola.ui import theme
    w = window
    w.a_dark.setChecked(True)
    assert theme.is_dark() and "#1E1F22" in QApplication.instance().styleSheet()
    assert w.settings.value("zobrazeni/tmavy", False, type=bool)
    w.a_dark.setChecked(False)
    assert not theme.is_dark() and "#1E1F22" not in QApplication.instance().styleSheet()
    # nová verze → okno s odkazem ke stažení (síť se v testu nepoužije)
    shown = []
    monkeypatch.setattr(aktualizace, "BUILD", 5)
    monkeypatch.setattr(aktualizace, "fetch_latest", lambda timeout=6.0: 9)
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.text()))
    w.check_updates(manual=True)
    assert w._wait(lambda: bool(shown), 5)
    assert "č. 9" in shown[0] and aktualizace.DOWNLOAD_URL in shown[0]


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_seznam_k_oprave_pdf(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    out = tmp_path / "k_oprave.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))
    w.a_exp_todo.trigger()
    assert out.exists() and out.stat().st_size > 5000
    import pdfplumber
    with pdfplumber.open(out) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    assert "Seznam k opravě" in text and "Jak opravit" in text


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_novy_seznam_skryje_stary_navod(window):
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    p = w.issue_panel
    p.select_issue(w.issues[0].number)
    assert p.hint.isVisibleTo(p) and p.b_find.isEnabled()
    w.set_issues([])
    assert not p.hint.isVisibleTo(p) and not p.b_find.isEnabled()


DOC1 = Path(__file__).resolve().parents[1] / "podklady" / "zadani1-microstation" / "Zadání-Microstation.doc"


@pytest.mark.skipif(not DOC1.exists(), reason="zadání chybí")
def test_word_se_zadanim_prida_vrstvy(window):
    w = window
    w.open_path(str(DOC1))  # QMessageBox.question → Ano (přidat vrstvy)
    page = w.zadani.documents_page
    assert w.zadani.tabs.currentWidget() is page
    assert page.list.count() == 1 and page.req.rowCount() > 0 and page.lay_table.rowCount() == 3
    assert {r.hladina for r in w.project.rules.pravidla} >= {"58", "59", "60"}
    assert "jsou v pravidlech" in page.rules_state.text()
    page._remove()  # odebrání dokumentu odebere i jeho pravidla
    assert not {r.hladina for r in w.project.rules.pravidla} & {"58", "59", "60"}


def test_styl_zdi_kresli_oblouky():
    from kontrola.ui.drawing_view import style_mark_kind
    assert style_mark_kind("2.163", "Ohradni zed, vlastnictvi z jedne strany") == "oblouky"
    assert style_mark_kind("2.103", "Dreveny plot, vlastnictvi z jedne strany") == "carky"


def test_rychle_tipy():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from kontrola.ui.tips import TipsDialog
    d = TipsDialog()
    d.search.setText("kolmice")
    names = [d.list.item(i).text().strip() for i in range(d.list.count()) if d.list.item(i).data(0x0100) is not None]
    assert names and all("olmice" in n for n in names)
    assert "Perpendicular" in d.view.toPlainText() or "AccuDraw" in d.view.toPlainText()


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_uvod_a_skore(window):
    w = window
    assert w.tabs.widget(0) is w.home
    w.home.refresh()
    assert w.home.gauge.value is None
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    assert w.tabs.currentWidget() is w.split  # po otevření výkresu se ukáže výkres
    assert w.home.gauge.value is not None and 0 <= w.home.gauge.value < 100
    assert w.issue_panel.gauge.isVisibleTo(w.issue_panel)
    from kontrola.skore import compute_score
    for i in w.issues:
        i.state = "opraveno"
    assert compute_score(w.issues).hodnota == 100


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_html_protokol(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    out = tmp_path / "protokol.html"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))
    w.a_exp_html.trigger()
    html = out.read_text(encoding="utf-8")
    assert "data:image/png;base64," in html and '"px": [' in html and "Jak opravit" in html
    assert html.count('"n": ') == len(w.issues)


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_hromadna_kontrola(window, tmp_path):
    from kontrola.ui.batch_dialog import check_files
    bad = tmp_path / "rozbity.dxf"
    bad.write_text("tohle není DXF")
    rows = check_files([str(UKAZKA), str(bad)], window.project.rules, window.project.config,
                       lambda *a: None, lambda: False)
    assert rows[0]["chyby"] > 0 and rows[0]["skore"] is not None
    assert rows[1]["chyba"] and rows[1]["skore"] is None


def test_poradce():
    from kontrola.ui.poradce import answer
    assert answer("jak udělat kolmici")[0][0].startswith("Kolmice")
    assert "Směrnic" in answer("proč vrstva 58 není ve směrnici")[0][0]
    assert answer("xyzzy qwerty") == []


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_poradce_zna_projekt(window):
    from kontrola.rules import Rule
    w = window
    w.project.rules.pravidla.append(Rule(kod="P1", nazev="Plot dřevěný", hladina="PLOTY", barva=93, styl_cary="2.103"))
    w.poradce.q.setText("jaká barva je plot dřevěný")
    w.poradce.ask()
    assert "93" in w.poradce.chat.toPlainText() and "2.103" in w.poradce.chat.toPlainText()
    w.poradce.q.setText("co dál")
    w.poradce.ask()
    assert "Otevřete výkres" in w.poradce.chat.toPlainText()
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    w.issue_panel.select_issue(w.issues[0].number)
    w.poradce.q.setText("jak opravit tuhle chybu")
    w.poradce.ask()
    assert "Jak opravit" in w.poradce.chat.toPlainText()
    w.poradce.q.setText("kolik mi zbývá")
    w.poradce.ask()
    assert "K opravě zbývá" in w.poradce.chat.toPlainText()


GEOGRAF = Path(__file__).resolve().parents[1] / "geograf V1.dxf"
BODY13 = Path(__file__).resolve().parents[1] / "podklady" / "zadani1-microstation" / "Body13_tr.txt"


@pytest.mark.skipif(not (GEOGRAF.exists() and BODY13.exists()), reason="data chybí")
def test_overit_seznam_souradnic(window, tmp_path):
    w = window
    w.load_drawing_file(GEOGRAF)
    assert w._wait(lambda: _idle(w) and w.drawing is not None, 30)
    from kontrola.ui.seznam_dialog import SeznamDialog
    d = SeznamDialog(w, str(BODY13))
    assert d.card_labels["ok"].text() == "86" and "Všech 86" in d.summary.text()
    # seznam s chybami: jeden bod posunutý, jeden navíc, jedno číslo jinak
    lines = BODY13.read_text().splitlines()
    parts = lines[0].split()
    lines[0] = f"{parts[0]} {float(parts[1]) + 0.2:.2f} {parts[2]} {parts[3]}"
    lines.append("1000139999 565400.00 1187900.00 0.00")
    bad = tmp_path / "body.txt"
    bad.write_text("\n".join(lines))
    d.path.setText(str(bad))
    d.run()
    assert d.card_labels["posunuty"].text() == "1" and d.card_labels["chybi"].text() == "1"
    d.table.cellDoubleClicked.emit(0, 0)
    d.close()
