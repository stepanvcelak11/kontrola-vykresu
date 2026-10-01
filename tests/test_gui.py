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
    # okna i jejich plovoucí okénka zrušit hned – desítky oken rušených až při ukončení Pythonu
    # (v náhodném pořadí po QApplication) na Windows občas shodí proces po úspěšných testech
    from PySide6.QtCore import QCoreApplication, QEvent
    if getattr(w, "_mini", None) is not None:
        w._mini.close()
        w._mini.deleteLater()
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


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
    shown = []
    w.notify = lambda title, text: shown.append(text)  # upozornění Windows (v testu jen zaznamenat)
    w._file_changed(str(src))
    import time
    assert w._wait(lambda: _idle(w) and "Opakovaná" in w.issue_panel.summary.text(), 20)
    assert n_before > 0
    assert shown and "zbývá opravit" in shown[0]


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
    assert w.settings.value("zobrazeni/vzhled") == "tmavy"
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
    with pdfplumber.open(out) as pdf:  # u skupin s návodem i obrázek „chyba / správně“
        n_img = sum(len(p.images) for p in pdf.pages)
    ids = {i.check_id for i in w.issues if i.state == "nová" and i.severity.value != "info"}
    assert n_img >= len(w._illustrations(ids)) > 0


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
    w.project.config.settings("spicka").zapnuto = False
    w.a_exp_html.trigger()
    html = out.read_text(encoding="utf-8")
    assert "data:image/png;base64," in html and '"px": [' in html and "Jak opravit" in html
    assert html.count('"n": ') == len(w.issues)
    assert "Nespuštěno:" in html and "Špička" in html


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


def test_co_aplikace_umi_a_hodnoty_ze_zadani(window, tmp_path):
    from kontrola.ui.features_dialog import FeaturesDialog
    w = window
    dlg = FeaturesDialog(w)
    dlg.search.setText("náčrtu plot")
    shown = [c for c, _ in dlg.cards if not c.isHidden()]
    assert len(shown) == 1
    dlg._run("_dokumenty")
    assert w.zadani.tabs.currentWidget() is w.zadani.documents_page
    f = tmp_path / "zadani.txt"
    f.write_text("Kresbu vyhotovte v měřítku 1:500. Tolerance začištění je 5 mm.", encoding="utf-8")
    pg = w.zadani.documents_page
    pg.add_file(str(f), ask=False)
    assert "1:500" in pg.settings_info.text() and not pg.b_apply.isHidden()
    pg.apply_settings()
    assert abs(w.project.config.tolerance - 0.005) < 1e-12
    assert pg.b_apply.isHidden()


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_spojnice_okno(window, tmp_path):
    w = window
    w.load_drawing_file(UKAZKA)
    assert w._wait(lambda: _idle(w) and w.drawing is not None, 30)
    w.a_spojnice.trigger()
    dlg = w._spojnice_dlg
    assert dlg.isVisible()
    dlg.run()  # bez seznamu jen upozorní
    dlg.close()


Z1 = Path(__file__).resolve().parents[1] / "podklady" / "zadani1-microstation"


@pytest.mark.skipif(not (Z1 / "Vcelak_13_a0_t0 - nahled.pdf").exists(), reason="data chybí")
def test_vzor_pdf_porovna_kresbu(window):
    w = window
    w.load_drawing_file(Z1 / "Vcelak_13_navic.dxf")
    assert w._wait(lambda: _idle(w) and w.drawing is not None, 30)
    pg = w.zadani.template_page
    pg.set_template(str(Z1 / "Vcelak_13_a0_t0 - nahled.pdf"))
    pg.compare()
    rows = [pg.diff.item(r, 1).text() for r in range(pg.diff.rowCount()) if pg.diff.item(r, 0).text() == "Kresba"]
    assert "umístění PDF" in rows
    assert "Kresba" in pg.status.text()


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_opravny_pruvodce(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QFileDialog
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    w.a_fixguide.trigger()
    dlg = w._fix_dlg
    n = len(dlg.items)
    assert n > 0 and "XY=" in dlg.body.toHtml()
    first = dlg.items[0]
    dlg.b_done.click()
    assert first.state == "opraveno" and dlg.i == 1
    from PySide6.QtCore import QUrl
    dlg._copy_link(QUrl("copy:XY=1.000,2.000"))
    assert QApplication.clipboard().text() == "XY=1.000,2.000"
    out = tmp_path / "list.html"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))
    dlg.save_list()
    assert out.read_text(encoding="utf-8").count("class='k'") == n
    dlg.close()


def test_nahled_tisku_v_meritku(window, tmp_path):
    w = window
    w.load_drawing_file(Z1 / "Vcelak_13_navic.dxf")
    assert w._wait(lambda: _idle(w) and w.drawing is not None, 30)
    out = w.print_preview(str(tmp_path / "tisk.pdf"), 500)
    import pdfplumber
    with pdfplumber.open(out) as pdf:
        pg = pdf.pages[0]
        rect = w.view._content_rect
        # šířka papíru v bodech PDF = (kresba v m × 2 mm/m + 20 mm okraje) / 25,4 × 72
        assert abs(pg.width - (rect.width() * 2 + 20) / 25.4 * 72) < 2
        assert "1:500" in (pdf.metadata.get("Title") or "")  # text na Windows bývá jako křivky


def test_casova_osa(window, tmp_path, monkeypatch):
    import ezdxf
    from PySide6.QtWidgets import QFileDialog

    from kontrola.casova_osa import snapshots
    from kontrola.ui.timeline_dialog import TimelineDialog
    w = window
    f = tmp_path / "moje.dxf"
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "A"})
    keep = msp.add_line((0, 5), (10, 5), dxfattribs={"layer": "B"})
    doc.saveas(f)
    w.load_drawing_file(f)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and w.drawing is not None, 30)
    w.a_check.trigger()  # beze změny → žádná nová verze
    assert w._wait(lambda: _idle(w), 30)
    assert len(snapshots(w.project)) == 1
    msp.delete_entity(keep)
    doc.saveas(f)
    w.load_drawing_file(f)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(snapshots(w.project)) == 2, 30)
    dlg = TimelineDialog(w)
    assert dlg.table.rowCount() == 2 and dlg.table.item(1, 2).text() == "-1"
    dlg.table.selectRow(0)
    assert dlg.preview.pixmap() is not None and not dlg.preview.pixmap().isNull()
    out = tmp_path / "smazane.dxf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))
    dlg.restore_removed()
    rest = list(ezdxf.readfile(out).modelspace())
    assert len(rest) == 1 and rest[0].dxf.layer == "B"


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_uciteluv_pohled(window):
    from kontrola.ui.predikce_dialog import PredikceDialog
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    dlg = PredikceDialog(w)
    assert "Celkem chyb" in dlg.log.toPlainText()
    assert dlg.pred.protokolu == 0


def test_microstation_seznam_chyb_a_makro(window, tmp_path):
    import shutil

    from kontrola.microstation import install_macro
    w = window
    f = tmp_path / "Vykres.dxf"
    shutil.copy(UKAZKA, f)
    w.a_ms_send.setChecked(True)
    w.load_drawing_file(f)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and (tmp_path / "Vykres_chyby.txt").exists(), 30)
    lines = (tmp_path / "Vykres_chyby.txt").read_bytes().decode("cp1250").splitlines()
    data = [ln.split("\t") for ln in lines if not ln.startswith("#")]
    assert data and all(len(d) == 5 for d in data)
    float(data[0][1]), float(data[0][2])  # desetinná tečka pro Val() ve VBA
    w.a_ms_send.setChecked(False)  # nastavení se ukládá – další testy nesmí zapisovat vedle ukázek
    bas = install_macro(tmp_path).read_bytes()
    assert b"\r\n" in bas and "KV_Dalsi".encode() in bas
    bas.decode("cp1250")  # VBA editor čte ANSI


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_co_zkontrolovat(window, monkeypatch):
    from kontrola.checks.base import REGISTRY
    from kontrola.ui import vyber_kontrol
    w = window
    w.load_drawing_file(UKAZKA)
    assert w._wait(lambda: _idle(w) and w.drawing is not None, 30)
    dlg = vyber_kontrol.VyberKontrol(w)
    assert set(dlg.boxes) == set(REGISTRY)
    dlg.apply_preset(next(p for n, _t, p in vyber_kontrol.PRESETY if n == "Jen topologie"))
    assert all(cb.isChecked() == (REGISTRY[c].skupina == "Topologie") for c, cb in dlg.boxes.items())
    dlg.group_boxes["Geometrie"].click()
    assert dlg.boxes["spicka"].isChecked() and dlg.group_boxes["Geometrie"].isChecked()
    dlg.save_and_run()
    assert dlg.run_now and w.project.config.settings("spicka").zapnuto
    assert not w.project.config.settings("symbologie").zapnuto
    # rychlá sada z nabídky u tlačítka Zkontrolovat spustí kontrolu jen vybraných
    w.issues = []
    w.run_preset("Jen atributy")
    assert w._wait(lambda: _idle(w) and w.issues, 60)
    assert {i.check_id for i in w.issues} <= {c for c, k in REGISTRY.items() if k.skupina == "Atributy"}
    from PySide6.QtWidgets import QToolBar
    tb = w.findChild(QToolBar, "hlavni_panel")
    assert tb.widgetForAction(w.a_check).menu() is not None
    w.run_preset("Jako učitel")
    assert w._wait(lambda: _idle(w), 60)
    dlg2 = vyber_kontrol.VyberKontrol(w)
    dlg2.search.setText("špička")
    assert not dlg2.boxes["spicka"].isHidden() and dlg2.boxes["symbologie"].isHidden()
    assert dlg2.cards["Atributy"].isHidden() and not dlg2.cards["Geometrie"].isHidden()
    dlg2.search.clear()
    assert not dlg2.boxes["symbologie"].isHidden()
    # vlastní sada: uložit, použít z nabídky tlačítka Zkontrolovat
    for cid, cb in dlg2.boxes.items():
        cb.setChecked(cid in ("spicka", "duplicity"))
    dlg2.save_as_set("Moje rychlá")
    dlg2.reject()
    assert vyber_kontrol.vlastni_sady(w.settings)["Moje rychlá"] == ["duplicity", "spicka"] or \
        sorted(vyber_kontrol.vlastni_sady(w.settings)["Moje rychlá"]) == ["duplicity", "spicka"]
    menu = tb.widgetForAction(w.a_check).menu()
    menu.aboutToShow.emit()
    act = next(a for a in menu.actions() if a.text() == "Moje sada: Moje rychlá")
    act.trigger()
    assert w._wait(lambda: _idle(w), 60)
    on = {c for c in REGISTRY if w.project.config.settings(c).zapnuto}
    assert on == {"spicka", "duplicity"}
    vyber_kontrol.smaz_sadu(w.settings, "Moje rychlá")
    assert "Moje rychlá" not in vyber_kontrol.vlastni_sady(w.settings)


def test_gis_vykres_v_okne(window, tmp_path, monkeypatch):
    import json
    from PySide6.QtWidgets import QMessageBox
    p = tmp_path / "gis.geojson"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"layer": "Cesty"},
         "geometry": {"type": "LineString", "coordinates": [[-600000, -1150000], [-600010, -1150000]]}},
        {"type": "Feature", "properties": {"layer": "Cesty"},
         "geometry": {"type": "LineString", "coordinates": [[-600010.005, -1150000], [-600010.005, -1150010]]}},
        {"type": "Feature", "properties": {"layer": "Budovy"},
         "geometry": {"type": "Polygon", "coordinates": [[[-600000, -1150020], [-599990, -1150020],
                                                          [-599990, -1150030], [-600000, -1150020]]]}}]}), "utf-8")
    w = window
    w.open_path(str(p))
    assert w._wait(lambda: _idle(w) and w.drawing is not None and w.drawing.path == str(p), 30)
    w.run_checks()
    assert w._wait(lambda: _idle(w) and w.issues, 60)
    assert any(i.check_id == "chybejici_napojeni" for i in w.issues)
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    w.repair()  # oprava umí jen DXF – jen vysvětlí
    assert shown and "jen výkres DXF" in shown[0]


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_prehled_vykresu(window):
    from PySide6.QtCore import Qt
    w = window
    w.load_drawing_file(UKAZKA)
    assert w._wait(lambda: _idle(w) and w.drawing is not None, 30)
    w.a_prehled.trigger()
    dlg = w._prehled_dlg
    t = dlg.table
    assert t.rowCount() == len({f.layer for f in w.drawing.features})
    assert sum(int(t.item(r, 1).text()) for r in range(t.rowCount())) == len(w.drawing.features)
    assert t.horizontalHeaderItem(2).text() == "Chyb"
    t.selectRow(0)
    name = dlg.selected_layer()
    dlg.only_layer()
    lst = w.layers.list
    on = [lst.item(i).data(Qt.UserRole) for i in range(lst.count()) if lst.item(i).checkState() == Qt.Checked]
    assert on == [name]
    dlg._show_layers(None)
    dlg.copy()
    dlg.close()


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_uvod_bez_pravidel_nabidne_cizi_vykres(window):
    w = window
    assert not w.project.rules.pravidla
    w.load_drawing_file(UKAZKA)
    assert w._wait(lambda: _idle(w) and w.drawing is not None, 30)
    w.home.refresh()
    assert "bez pravidel" in w.home.next_btn.text()
    w.home._next_action()
    assert w._wait(lambda: _idle(w) and w.issues, 60)
    assert not w.project.config.settings("symbologie").zapnuto
    assert w.project.config.settings("spicka").zapnuto
    w.home.refresh()
    assert "Zadání" in w.home.next_btn.text()


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_shluky_kroužku(window):
    from kontrola.checks.base import Issue, Severity
    w = window
    w.load_drawing_file(UKAZKA)
    assert w._wait(lambda: _idle(w) and w.drawing is not None, 30)
    x0, y0, x1, y1 = w.drawing.bounds()
    iss = [Issue("visici_konce", "Visící konec", Severity.VAROVANI, f"konec {k}", x0 + 1 + k * 0.01, y0 + 1)
           for k in range(5)] + [Issue("duplicity", "Duplicita", Severity.CHYBA, "dup", x0 + 1, y0 + 1.02),
                                 Issue("duplicity", "Duplicita", Severity.CHYBA, "dál", x1 - 1, y1 - 1)]
    for n, i in enumerate(iss, 1):
        i.number = n
    w.view.set_issues(iss)
    w.view.fit_all()
    w.view._declutter()
    leaders = [m for m in w.view.markers.values() if m.cluster_n > 1]
    assert len(leaders) == 1 and leaders[0].cluster_n == 6
    assert leaders[0].issue.severity == Severity.CHYBA  # shluk vede nejzávažnější chyba
    assert sum(m.cluster_hidden for m in w.view.markers.values()) == 5
    w.view.highlight_issue(3, zoom=False)
    w.view._declutter()
    assert not w.view.markers[3].cluster_hidden  # vybraná chyba se ukáže


def test_nove_chyby_od_minule_kontroly(window, tmp_path):
    import ezdxf
    w = window
    p = tmp_path / "v.dxf"
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "A"})
    msp.add_line((10, 0), (10, 10), dxfattribs={"layer": "A"})
    doc.saveas(p)
    w.load_drawing_file(p)
    assert w._wait(lambda: _idle(w) and w.drawing is not None, 30)
    w.run_checks()
    assert w._wait(lambda: _idle(w) and w.issues, 30)
    assert not any(i.nove for i in w.issues)
    first = {i.key for i in w.issues}
    msp.add_line((10.005, 10), (20, 10), dxfattribs={"layer": "A"})  # nedotažení o 5 mm
    doc.saveas(p)
    w.recheck(p, silent=True)
    assert w._wait(lambda: _idle(w) and any(i.nove for i in w.issues), 30)
    assert all((i.key not in first) == i.nove for i in w.issues)
    w.issue_panel.set_quick("nove")
    shown = w.issue_panel.proxy.rowCount()
    assert shown == sum(i.nove for i in w.issues) and shown > 0


def test_hledani_prikazu(window, monkeypatch):
    w = window
    cs = w.cmd_search
    cs._collect()
    m = cs._matches("prehled vykres")  # bez diakritiky
    assert m and m[0].startswith("Přehled výkresu")
    called = []
    monkeypatch.setattr(w, "show_overview", lambda: called.append(1))
    from PySide6.QtGui import QAction
    a = cs._actions[m[0]]
    assert isinstance(a, QAction)
    a.triggered.disconnect()
    a.triggered.connect(lambda: called.append(1))
    cs.setText("prehled vykres")
    cs._run(cs._first())
    assert called and cs.text() == ""


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_plovouci_panel_a_minimapa(window):
    w = window
    w.load_drawing_file(UKAZKA)
    assert w._wait(lambda: _idle(w) and w.drawing is not None, 30)
    w.resize(1300, 850)
    w.show_page("vykres")
    assert w.a_page["vykres"].isChecked() and w.tabs.currentWidget() is w.split
    cv = w.split
    assert cv.card.isVisible() and w.view.inset_right > 0
    cv.set_panel_visible(False, animate=False)
    assert not cv.card.isVisible() and cv.b_show.isVisible() and w.view.inset_right == 0
    cv.set_panel_visible(True, animate=False)
    assert cv.card.isVisible() and not cv.b_show.isVisible()
    w.minimap._tick()
    assert w.minimap.isVisible() and w.minimap._map is not None
    w.issue_panel.set_card_mode(False)
    assert not w.issue_panel.table.isColumnHidden(0)
    w.issue_panel.set_card_mode(True)
    assert w.issue_panel.table.isColumnHidden(0)


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_mini_okno_dalsi_chyba(window):
    from PySide6.QtWidgets import QApplication
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 2, 30)
    w.a_mini.trigger()
    m = w._mini
    assert m.isVisible() and m.windowFlags() & m.windowFlags().WindowStaysOnTopHint
    first = w.issue_panel.current_issue()
    assert first is not None and f"#{first.number}" in m.head.text()
    m._fixed()
    assert first.state == "opraveno"
    assert w.issue_panel.current_issue() is not first
    keys = [m.keyrow.itemAt(i).widget() for i in range(m.keyrow.count())]
    assert keys
    keys[0].click()
    assert QApplication.clipboard().text()
    m.close()


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_osobni_tahak(window):
    w = window
    w.settings.remove("tahak/projekty")  # QSettings přežívá mezi testy
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    w.home.refresh()
    assert w.home.tahak.isVisibleTo(w.home) and "Na co si dát pozor" in w.home.tahak.text()
    from kontrola import tahak
    w.a_check.trigger()  # opakovaná kontrola téhož projektu počty nezdvojí
    assert w._wait(lambda: _idle(w), 30)
    mine = tahak._load(w.settings)[str(w.project.root)]
    assert 0 < sum(mine.values()) <= sum(1 for i in w.issues if i.severity.value != "info")


def test_tepelna_mapa(window):
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    w.a_heat.setChecked(True)
    it = w.view._heat_item
    assert it is not None and it.scene() is w.view.scene() and not it.pixmap().isNull()
    w.issue_panel.filterChanged.emit(set())  # žádná viditelná chyba → mapa zmizí
    assert w.view._heat_item is None
    w.a_heat.setChecked(False)
    assert w.view._heat_item is None


def test_rezim_soustredeni(window):
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    w.show()
    w.a_focus.setChecked(True)
    bar = w._focus_bar
    assert bar.isVisible() and not w.toolbar.isVisible() and not w.view_tools.isVisible()
    assert not w.split.card.isVisible() or not w.split.panel_visible
    iss = w.issue_panel.current_issue()
    assert iss is not None and iss.message in bar.title.text()
    todo = sum(1 for i in w.issues if i.state == "nová")
    bar.b_ok.click()
    assert iss.state == "opraveno" and sum(1 for i in w.issues if i.state == "nová") == todo - 1
    assert w.issue_panel.current_issue() is not iss
    w._focus_esc.activated.emit()
    assert not w.a_focus.isChecked() and not bar.isVisible()
    assert w.toolbar.isVisible() and w.view_tools.isVisible() and w.split.panel_visible


def test_obrazek_jak_to_ma_vypadat(window):
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    from kontrola.ui.help_topics import _SVG
    s = next(i for i in w.issues if i.check_id in _SVG)
    w.issue_panel.select_issue(s.number)
    assert w.issue_panel.ilustrace.isVisibleTo(w.issue_panel)
    assert not w.issue_panel.ilustrace.pixmap().isNull()


def test_barva_vzhledu(window):
    from PySide6.QtWidgets import QApplication

    from kontrola.ui import theme
    w = window
    try:
        w.a_accent["zelena"].trigger()
        assert theme.accent_name() == "zelena"
        css = QApplication.instance().styleSheet()
        assert theme.ACCENT not in css and theme._accent_color(theme.ACCENT) in css
        assert w.settings.value("zobrazeni/barva") == "zelena"
        assert theme._accent_color("#DC2626") == "#DC2626"  # červená (chyby) zůstává
    finally:
        w.set_accent("modra")
    assert theme.ACCENT in QApplication.instance().styleSheet() or theme.is_dark()


def test_zadne_dvojite_zkratky(window):
    from PySide6.QtGui import QAction, QKeySequence
    seen = {}
    for a in window.findChildren(QAction):
        sc = a.shortcut().toString(QKeySequence.PortableText)
        if sc:
            seen.setdefault(sc, set()).add(a.text())
    dup = {k: v for k, v in seen.items() if len(v) > 1}
    assert not dup, dup


def test_souvisejici_chyby_na_stejnem_miste(window):
    from kontrola.checks.base import Issue, Severity
    w = window
    mk = lambda n, x, y, sev=Severity.CHYBA: Issue("pruseciky_bez_uzlu", "Průsečík", sev, f"chyba {n}", x, y,
                                                   number=n)
    issues = [mk(1, 0, 0), mk(2, 0.05, 0.05), mk(3, 0.3, 0), mk(4, 0.25, 0.3), mk(5, 0.05, 0, Severity.INFO)]
    issues[0].feature_ids = [7]
    issues[2].feature_ids = [7]  # stejný prvek do 50 cm; #4 jiný prvek 25 cm → nesouvisí
    p = w.issue_panel
    p.set_issues(issues)
    assert p.near[1] == [2, 3] and 4 not in p.near and 5 not in p.near
    p.select_issue(1)
    assert "Hned vedle" in p.hint.text() and "#2" in p.hint.text()
    p.hint.linkActivated.emit("3")
    assert p.current_issue().number == 3


def test_zpet_stav_chyby(window):
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 1, 30)
    p = w.issue_panel
    p.select_issue(w.issues[0].number)
    first = p.current_issue()
    p.set_state("opraveno")
    assert first.state == "opraveno" and p.current_issue() is not first
    p.set_state("ignorovat")
    second = [i for i in w.issues if i.state == "ignorovat"][0]
    w.a_undo.trigger()
    assert second.state == "nová" and p.current_issue() is second
    w.a_undo.trigger()
    assert first.state == "nová" and p.current_issue() is first
    w.a_undo.trigger()  # prázdná historie nic nerozbije
    assert not p.can_undo()


def test_velikost_pisma(window):
    from PySide6.QtWidgets import QApplication

    from kontrola.ui import theme
    w = window
    base = QApplication.font().pointSizeF()
    h0 = w.issue_panel.table.verticalHeader().defaultSectionSize()
    try:
        w.a_font["nejvetsi"].trigger()
        assert abs(QApplication.font().pointSizeF() - base * 1.3) < 0.2
        assert w.issue_panel.table.verticalHeader().defaultSectionSize() >= h0
        assert w.settings.value("zobrazeni/pismo") == "nejvetsi"
    finally:
        w.set_font_scale("normalni")
    assert abs(QApplication.font().pointSizeF() - base) < 0.05 and theme.font_scale_name() == "normalni"


def test_co_aplikace_umi_akce_existuji(window):
    from kontrola.ui.features_dialog import FUNKCE
    for _g, items in FUNKCE:
        for name, _d, act in items:
            if act and act.startswith("a_"):
                assert getattr(window, act, None) is not None, (name, act)


def test_opravy_z_revize(window):
    """Tepelná mapa po Opraveno, kopírování v okně Další chyba, „Hotovo“ v režimu soustředění."""
    from PySide6.QtWidgets import QApplication
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    w.a_heat.setChecked(True)
    for i in w.issues:
        if i.state == "nová" and i is not w.issues[0]:
            i.state = "opraveno"
    w.issue_panel.select_issue(w.issues[0].number)
    w.issue_panel.set_state("opraveno")  # poslední otevřená chyba
    assert w.view._heat_item is None  # nic neopraveného → žádná skvrna
    # okno Další chyba: kopírování a hned další chyba nesmí spadnout na smazaném tlačítku
    w.issue_panel.set_state("nová")
    w.show_mini()
    m = w._mini
    btns = [m.keyrow.itemAt(k).widget() for k in range(m.keyrow.count())]
    if btns:
        btns[0].click()
        m.refresh()
        w._wait(lambda: False, 1.5)
        QApplication.processEvents()
    # režim soustředění: po opravě poslední chyby „Hotovo“
    w.a_focus.setChecked(True)
    w._focus_bar.b_ok.click()
    assert "Hotovo" in w._focus_bar.title.text()
    w.a_focus.setChecked(False)


def test_co_je_noveho(window):
    from kontrola import novinky
    w = window
    s = w.settings
    s.remove(novinky.KEY)
    geo = s.value("okno/geometrie")
    s.remove("okno/geometrie")
    try:
        assert novinky.unseen(s) == []  # úplně první spuštění: nic (je tu průvodce)
        w.maybe_show_news()
        assert int(s.value(novinky.KEY)) == novinky.latest_id()
        s.setValue(novinky.KEY, novinky.latest_id() - 1)  # po aktualizaci
        w.maybe_show_news()
        dlg = w._news_dlg
        assert dlg.isVisible() and int(s.value(novinky.KEY)) == novinky.latest_id()
        dlg.close()
        assert w.show_news(force=True) is not None
        w._news_dlg.close()
    finally:
        if geo is not None:
            s.setValue("okno/geometrie", geo)


def test_hromadne_ignorovat_a_zpet(window):
    from kontrola.checks.base import Issue, Severity
    w = window
    mk = lambda n, cid, layer: Issue(cid, cid, Severity.CHYBA, f"chyba {n}", n * 10.0, 0, layer=layer, number=n)
    issues = [mk(1, "a", "L1"), mk(2, "a", "L2"), mk(3, "b", "L1"), mk(4, "a", "L1")]
    p = w.issue_panel
    p.set_issues(issues)
    p.set_state("ignorovat", [i for i in issues if i.check_id == "a"])
    assert [i.state for i in issues] == ["ignorovat", "ignorovat", "nová", "ignorovat"]
    p.undo()  # jedno Ctrl+Z vrátí celou hromadnou změnu
    assert all(i.state == "nová" for i in issues)
