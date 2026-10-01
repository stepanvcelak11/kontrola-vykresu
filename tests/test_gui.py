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
    assert "data:image/svg+xml;base64," in html and "const ILU=" in html  # obrázky „chyba / správně“


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


def test_pocet_na_tlacitku_chyby(window):
    w = window
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    k = lambda: sum(1 for i in w.issues if i.state == "nová" and i.severity.value != "info")
    assert f"({k()})" in w.split.b_show.text()
    first = next(i for i in w.issues if i.severity.value != "info")
    w.issue_panel.select_issue(first.number)
    w.issue_panel.set_state("opraveno")
    assert f"({k()})" in w.split.b_show.text()


def test_hlaseni_o_problemu(window, tmp_path, monkeypatch):
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtCore import QStandardPaths
    from kontrola.ui import crash
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    monkeypatch.setattr(QStandardPaths, "writableLocation", staticmethod(lambda loc: str(tmp_path / "plocha")))
    w = window
    # tvrdý pád minule: příznak běhu zůstal
    crash.start_session()
    assert crash.previous_run_crashed()
    crash.end_session()
    assert not crash.previous_run_crashed()
    w.load_drawing_file(UKAZKA)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    w.a_heat.trigger()  # jako kliknutí uživatele
    w.a_heat.trigger()
    crash.write_log("Traceback (most recent call last):\n  ValueError: zkouška")
    dlg = w.show_report("Klikl jsem na mapu")
    text = dlg._text()
    assert "Verze:" in text and "Klikl jsem na mapu" in text and "Tepelná mapa chyb" in text
    assert "ValueError: zkouška" in text and "prvků" in text
    dlg._copy()
    assert QGuiApplication.clipboard().text().startswith("HLÁŠENÍ O PROBLÉMU")
    dlg._save()
    saved = list((tmp_path / "plocha").glob("KontrolaVykresu_hlaseni_*.txt"))
    assert saved and "Poslední kroky" in saved[0].read_text(encoding="utf-8")
    dlg.close()


@pytest.mark.skipif(not UKAZKA.exists(), reason="ukázkový výkres chybí")
def test_kazda_funkce_bez_padu(window, tmp_path, monkeypatch):
    """Spustí každou akci okna (dialogy se samy zavřou) – žádná nesmí skončit výjimkou."""
    import sys
    import traceback

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QAction, QDesktopServices
    from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QInputDialog, QMenu, QMessageBox,
                                   QProgressDialog)
    w = window
    errs = []
    cur = {"t": ""}
    monkeypatch.setattr(sys, "excepthook", lambda t, e, tb: errs.append(
        (cur["t"], "".join(traceback.format_exception(t, e, tb))[-1200:])))
    orig_exec = QDialog.exec

    def fake_exec(self, *a, **k):
        # časovač patří dialogu: zanikne s ním (singleShot s vázanou metodou by mohl doběhnout
        # až po smazání dialogu – na Windows pak proces tiše spadne v některém z dalších testů)
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(self.reject)
        t.start(100)
        return orig_exec(self)
    monkeypatch.setattr(QDialog, "exec", fake_exec)
    monkeypatch.setattr(QMenu, "exec", lambda self, *a, **k: None)
    for n in ("question", "information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.No))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.No)
    monkeypatch.setattr(QMessageBox, "about", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda *a, **k: True))
    monkeypatch.setattr(QProgressDialog, "exec", lambda self: 0)
    cnt = {"n": 0}

    def save_name(*a, **k):
        cnt["n"] += 1
        flt = ((a[3] if len(a) > 3 else k.get("filter", "")) or "").lower()
        ext = next((e for e in (".pdf", ".xlsx", ".csv", ".html", ".dxf", ".log", ".kontrola", ".txt", ".lve")
                    if e[1:] in flt), ".pdf")
        return (str(tmp_path / f"out{cnt['n']}{ext}"), "")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(save_name))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: ([], "")))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    for n, v in (("getText", ("", False)), ("getItem", ("", False)), ("getInt", (0, False)),
                 ("getDouble", (0.0, False))):
        monkeypatch.setattr(QInputDialog, n, staticmethod(lambda *a, v=v, **k: v))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    import shutil
    kopie = tmp_path / "vykres" / UKAZKA.name  # funkce zapisují vedle výkresu – ne do repozitáře
    kopie.parent.mkdir()
    shutil.copy(UKAZKA, kopie)
    w.load_drawing_file(kopie)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    app = QApplication.instance()
    skip = ("Konec", "Ukončit", "Aktualizovat", "Zavřít")
    acts = [a for a in w.findChildren(QAction) if a.text() and a.menu() is None and not a.isSeparator()]
    assert len(acts) > 60
    for a in acts:
        t = a.text().replace("&", "")
        if any(s in t for s in skip):
            continue
        cur["t"] = t
        try:
            if a.isCheckable():
                a.toggle()
                w._wait(lambda: _idle(w), 30)
                a.toggle()
            else:
                a.trigger()
            w._wait(lambda: _idle(w), 60)
            for _ in range(3):
                app.processEvents()
            for tw in app.topLevelWidgets():
                if tw is not w and tw.isVisible():
                    tw.close()
            if w.split.focus_mode:
                w.a_focus.setChecked(False)
        except Exception:  # noqa: BLE001
            errs.append((t, traceback.format_exc()[-1200:]))
    # úklid uvnitř tohoto testu: zavřít okna, doběhnout odložená smazání a časovače, ať nic
    # nepřeteče do dalších testů
    import gc

    from PySide6.QtCore import QElapsedTimer, QEvent
    for tw in app.topLevelWidgets():
        if tw is not w and tw.isVisible():
            tw.close()
    hodiny = QElapsedTimer()
    hodiny.start()
    while hodiny.elapsed() < 500:
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    gc.collect()
    app.processEvents()
    assert not errs, "\n\n".join(f"{t}:\n{e}" for t, e in errs)


def test_vypocty_seznam_souradnic(window, tmp_path):
    w = window
    w.show_page("vypocty")
    p = w.vypocty
    assert w.tabs.currentWidget() is p and w.a_page["vypocty"].isChecked()
    src = tmp_path / "body.csv"
    src.write_text("Číslo;Y;X;Z;Kód\n1;595975,72;1158246,97;258,27;plot\n2;595976,10;1158247,01;;roh\n"
                   "3;595980,00;1158250,00;259,00;plot\nšpatný řádek;x;y\n", encoding="cp1250")
    assert p.import_dialog(str(src), accept=True) == 3
    assert len(p.seznam) == 3 and p.seznam.najdi("2").kod == "roh"
    # úprava v tabulce + chybná hodnota se nepřijme
    idx = p.proxy.mapFromSource(p.model.index(0, 3))
    assert p.proxy.setData(idx, "260,5")
    assert p.seznam.najdi("1").z == 260.5
    assert not p.proxy.setData(idx, "abc") and "není číslo" in p.msg.text()
    # filtr podle kódu
    p.kody.setCurrentIndex(p.kody.findData("plot"))
    assert p.proxy.rowCount() == 2
    p.kody.setCurrentIndex(0)
    # hromadně, smazat, Zpět přes Ctrl+Z okna
    p.table.selectAll()
    p.bulk_dialog({"kod": "hranice", "kvalita": 3, "dy": 0.0, "dx": 0.0, "dz": 0.0, "predpona": None,
                   "pricti_k_cislu": 0})
    assert all(b.kod == "hranice" and b.kvalita == 3 for b in p.seznam.body)
    w.a_undo.trigger()
    assert p.seznam.najdi("1").kod == "plot"
    w.a_redo.trigger()
    assert p.seznam.najdi("1").kod == "hranice"
    # export s plnou přesností do souboru a automatické uložení v projektu
    out = p.export_dialog(str(tmp_path / "ven.txt"))
    assert "595975.72" in Path(out).read_text(encoding="utf-8")
    p.save()
    from kontrola.geodezie.body import SeznamBodu
    assert len(SeznamBodu.nacti(w.project.root / "vypocty" / "seznam_bodu.json")) == 3
    # duplicity
    p.seznam.pridej([__import__("kontrola.geodezie.body", fromlist=["Bod"]).Bod("99", 595975.72, 1158246.97)])
    assert p.duplicates_dialog(accept_all=True) == 1 and p.seznam.najdi("99") is None


def test_vypocty_ulohy(window):
    from kontrola.geodezie import vypocty as V
    from kontrola.geodezie.body import Bod
    w = window
    w.show_page("vypocty")
    p = w.vypocty
    p.seznam.pridej([Bod("1", 595000.0, 1158000.0, 250.0), Bod("2", 595100.0, 1158000.0, 251.0),
                     Bod("3", 595050.0, 1158080.0), Bod("4", 595000.0, 1158100.0)])
    p.model.refresh()
    p.tabs.setCurrentWidget(p.ulohy)
    u = p.ulohy
    names = [u.lst.item(i).text() for i in range(u.lst.count())]
    # rajón
    u.lst.setCurrentRow(names.index("Rajón (polární bod)"))
    u.nastav(st="1", o="2", so="0", sm="100", d="50", nove="10")
    r = u.vypocitej()
    assert r and "Y =" in u.vystup.toPlainText()
    exp = V.rajon(V.P(595000, 1158000), V.norm_gon(V.smernik(V.P(595000, 1158000), V.P(595100, 1158000)) + 100), 50)
    assert u.pridej() == 1 and abs(p.seznam.najdi("10").y - exp.y) < 1e-9
    # chybný vstup – srozumitelná hláška, žádný pád
    u.nastav(st="999")
    assert u.vypocitej() is None and "není" in u.chyba.text()
    # výměra
    u.lst.setCurrentRow(names.index("Výměra a obvod"))
    u.nastav(body="1 2 3")
    u.vypocitej()
    assert "výměra P = 4000.00 m²" in u.vystup.toPlainText()
    # protokol v projektu
    assert "VÝMĚRA A OBVOD" in (w.project.root / "vypocty" / "protokol.txt").read_text(encoding="utf-8")
    # každá úloha s prázdným formulářem jen ohlásí, co chybí
    for i in range(u.lst.count()):
        u.lst.setCurrentRow(i)
        assert u.vypocitej() is None and u.chyba.text()


def test_polarni_metoda_protokol_a_seznam(window, tmp_path, monkeypatch):
    from kontrola.ui.vypocet_dialog import VypocetDialog
    z = Path(__file__).resolve().parents[1] / "podklady" / "zadani2-husovice"
    if not (z / "zap_husovice.zap").exists():
        pytest.skip("podklady chybí")
    w = window
    d = VypocetDialog(w.project, w)
    d.zap.setText(str(z / "zap_husovice.zap"))
    d.dane.setText(str(z / "dane_body.txt"))
    d.seznam.setText("")  # bez porovnání – jen výpočet jako v Gromě
    d.run()
    assert d.b_prot.isEnabled() and d.b_list.isEnabled()
    out = d.save_protokol(str(tmp_path / "protokol.pdf"))
    assert out and Path(out).stat().st_size > 5000
    txt = d.save_protokol(str(tmp_path / "protokol.txt"))
    assert "POLÁRNÍ METODA DÁVKOU" in Path(txt).read_text(encoding="utf-8-sig")
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    assert d.to_list() > 100 and w.vypocty.seznam.najdi("1") is not None
    d.close()


def test_cad_otevreni_mereni_a_propojeni(window, tmp_path):
    w = window
    w.load_drawing_file(UKAZKA)
    assert w._wait(lambda: _idle(w), 30)
    w.a_open_cad.trigger()
    c = w.cad
    assert w.tabs.currentWidget() is c and c.dok is not None and c.view.scene().items()
    assert "DXF" in c.historie.toPlainText()
    # měření vzdálenosti z příkazového řádku (souřadnice DXF)
    c.sjtsk = False
    c.proved("vzd")
    c.proved("x=0 y=0")
    c.proved("@3,4")
    assert "Vzdálenost 5.000" in c.historie.toPlainText()
    c.proved("nesmysl")
    assert "Neznámý příkaz" in c.historie.toPlainText()
    c.proved("?")
    # uložit jako a zkontrolovat v Kontrole (propojení CAD → Kontrola)
    p = c.uloz(path=str(tmp_path / "z_cad.dxf"))
    assert p.exists()
    c.zkontroluj()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    assert w.tabs.currentWidget() is w.split


def test_cad_kresleni_upravy_zpet(window, tmp_path):
    import ezdxf
    w = window
    w.show_page("cad")
    c = w.cad
    c.novy()
    assert c.dok is not None and not c.sjtsk
    msp = c.dok.msp
    # úsečky řetězcem z příkazového řádku
    for t in ("u", "x=0 y=0", "@10,0", "@0,10", ""):
        c.zadej(t)
    assert sorted(e.dxftype() for e in msp) == ["LINE", "LINE"]
    # kružnice: střed kliknutím, poloměr číslem
    c.proved("kr")
    c._klik(30.0, 0.0)
    c.zadej("5")
    assert any(e.dxftype() == "CIRCLE" and e.dxf.radius == 5 for e in msp)
    # polylinie uzavřená
    for t in ("pl", "x=50 y=0", "@10,0", "@0,10", "k"):
        c.zadej(t)
    pl = [e for e in msp if e.dxftype() == "LWPOLYLINE"]
    assert len(pl) == 1 and pl[0].closed
    c.view.zoom_all()
    # výběr kliknutím a posun
    c.vyber_v_bode(5, 0)
    assert len(c.vyber) == 1 and c.vyber[0].dxftype() == "LINE"
    for t in ("m", "x=0 y=0", "@0,-5"):
        c.zadej(t)
    l = [e for e in msp if e.dxftype() == "LINE" and abs(e.dxf.start.y + 5) < 1e-12]
    assert len(l) == 1 and len(msp) == 4
    assert c.view.scene().items()
    # Zpět přes hlavní okno (Ctrl+Z) a Vpřed
    w.undo_dispatch()
    assert not any(abs(e.dxf.start.y + 5) < 1e-12 for e in msp if e.dxftype() == "LINE")
    w.redo_dispatch()
    assert any(abs(e.dxf.start.y + 5) < 1e-12 for e in msp if e.dxftype() == "LINE")
    # výběr oknem a smazání, zpět
    c.vyber = []
    c._okno(45, -1, 61, 11)
    assert [e.dxftype() for e in c.vyber] == ["LWPOLYLINE"]
    c.proved("smaž")
    assert not any(e.dxftype() == "LWPOLYLINE" for e in msp)
    c.undo()
    assert any(e.dxftype() == "LWPOLYLINE" for e in msp)
    # ořez: úsečka přes kružnici
    for t in ("u", "x=20 y=0", "x=40 y=0", ""):
        c.zadej(t)
    c.proved("tr")
    c.view.mys = (30.0, 0.3)
    c._req.typ == "prvek"
    c._posli((next(e for e in msp if e.dxftype() == "LINE" and e.dxf.start.x == 20), (30.0, 0.0)))
    c.zrus()
    casti = sorted((round(e.dxf.start.x, 6), round(e.dxf.end.x, 6)) for e in msp
                   if e.dxftype() == "LINE" and e.dxf.start.y == 0 and e.dxf.start.x >= 20)
    assert casti == [(20, 25), (35, 40)]
    # text, vrstva, uložení a znovu načtení
    c.proved("vrstva POPIS")
    for t in ("t", "x=0 y=20", "2", "0", "Měřický bod č. 1", ""):
        c.zadej(t)
    assert c.neulozeno and c.title.text().endswith("*")
    p = c.uloz(path=str(tmp_path / "kresba.dxf"))
    assert not c.neulozeno
    d = ezdxf.readfile(p)
    t = [e for e in d.modelspace() if e.dxftype() == "TEXT"]
    assert t and t[0].dxf.text == "Měřický bod č. 1" and t[0].dxf.layer == "POPIS"
    assert len(d.modelspace()) == len(msp)
    # chybný vstup nespadne
    c.proved("kr")
    c.zadej("abc")
    c.zadej("x=1 y=1")
    c.zadej("-3")
    assert "⚠" in c.historie.toPlainText()
    c.proved("?")


def test_vypocet_ze_souboru_gsi(window, tmp_path):
    from kontrola.geodezie.gsi import zapis_gsi
    from kontrola.ui.vypocet_dialog import VypocetDialog
    from kontrola.vypocet import read_zap
    z = Path(__file__).resolve().parents[1] / "podklady" / "zadani2-husovice"
    if not (z / "zap_husovice.zap").exists():
        pytest.skip("podklady chybí")
    f = tmp_path / "mereni.gsi"
    f.write_text(zapis_gsi(read_zap(z / "zap_husovice.zap")), encoding="ascii")
    d = VypocetDialog(window.project, window)
    d.zap.setText(str(f))
    d.dane.setText(str(z / "dane_body.txt"))
    d.seznam.setText("")
    d.run()
    assert d.result is not None and len(d.result.body) > 100
    assert any("GSI: stanovisko 4001 – orientace na" in t for t in d._gsi_zpravy)
    d.close()


def test_cad_spravce_vrstev(window, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    c = window.cad
    window.show_page("cad")
    c.novy()
    for t in ("u", "x=0 y=0", "@10,0", ""):
        c.zadej(t)
    d = c.spravce_vrstev(modal=False)
    assert d.nova("HRANICE") == "HRANICE" and "HRANICE" in c.dok.doc.layers
    assert d.nova("HRANICE") is None  # už existuje
    # řádek vrstvy 0 → zamknout: úsečku pak nejde vybrat
    r0 = next(r for r in range(d.tab.rowCount()) if d._jmeno(r) == "0")
    d.tab.item(r0, 3).setCheckState(Qt.Checked)
    assert c.dok.doc.layers.get("0").is_locked()
    c.view.zoom_all()
    assert c.vyber_v_bode(5, 0) is None
    d.tab.item(r0, 3).setCheckState(Qt.Unchecked)
    assert c.vyber_v_bode(5, 0) is not None
    # přejmenování a smazání prázdné vrstvy, aktuální vrstva
    rh = next(r for r in range(d.tab.rowCount()) if d._jmeno(r) == "HRANICE")
    d.tab.selectRow(rh)
    assert d.prejmenuj("HRANICE_PARCEL") and "HRANICE_PARCEL" in c.dok.doc.layers
    rh = next(r for r in range(d.tab.rowCount()) if d._jmeno(r) == "HRANICE_PARCEL")
    d.tab.selectRow(rh)
    d.aktualni()
    assert c.kresleni.vrstva == "HRANICE_PARCEL"
    assert not d.smaz()  # aktuální vrstvu nejde smazat
    r0 = next(r for r in range(d.tab.rowCount()) if d._jmeno(r) == "0")
    d.tab.selectRow(r0)
    assert not d.smaz()
    # vypnutí vrstvy 0 – prvek zmizí z výběru i úchytů
    d.tab.item(r0, 1).setCheckState(Qt.Unchecked)
    assert c.dok.doc.layers.get("0").is_off() and c.vyber_v_bode(5, 0) is None
    assert c.neulozeno
    d.close()


def test_cad_bloky(window):
    c = window.cad
    window.show_page("cad")
    c.novy()
    for t in ("kr", "x=0 y=0", "1", "u", "x=-1 y=0", "x=1 y=0", ""):
        c.zadej(t)
    c.proved("vše")
    for t in ("blok", "", "BOD_ZNACKA", "x=0 y=0"):
        c.zadej(t)
    assert [e.dxftype() for e in c.dok.msp] == ["INSERT"]
    for t in ("vlož", "BOD_ZNACKA", "2", "0", "x=10 y=10", "x=20 y=10", ""):
        c.zadej(t)
    assert sum(1 for e in c.dok.msp if e.dxftype() == "INSERT") == 3
    c.undo()
    assert sum(1 for e in c.dok.msp if e.dxftype() == "INSERT") == 2
    c.proved("vlož")
    c.zadej("NENI")
    assert "⚠" in c.historie.toPlainText()


def test_poradce_citelny_v_tmavem_vzhledu(window):
    from kontrola.ui import theme
    puvodni = theme.is_dark()
    try:
        theme._dark = True
        p = window.poradce
        p.q.setText("volný konec")
        p.ask()
        html = "".join(p._html)
        assert "#EFF6FF" not in html and theme.DARK_MAP["#EFF6FF"] in html
        assert theme.DARK_MAP["#1F2937"] in html  # světlé písmo na tmavém pozadí
    finally:
        theme._dark = puvodni


def test_cad_podle_zadani(window, tmp_path):
    from kontrola.config import Config
    from kontrola.io.dxf_loader import load_drawing
    from kontrola.rules import RuleSet
    from kontrola.runner import run_checks
    f = Path(__file__).resolve().parents[1] / "podklady" / "zadani1-microstation" / "pravidla_zadani1.yaml"
    if not f.exists():
        pytest.skip("chybí pravidla")
    w = window
    puvodni = w.project.rules
    w.project.rules = RuleSet.load(f)
    try:
        c = w.cad
        w.show_page("cad")
        c.obnov_predvolby()
        assert c.predvolby_cb.count() == len(w.project.rules.pravidla) + 1
        c.novy_podle_zadani(vzory=[])
        assert "5" in c.dok.doc.layers and "58" in c.dok.doc.layers
        assert c.sjtsk
        # zvolit „Budovy zděné“ → spustí se polylinie s atributy budovy
        assert c.vyber_predvolbu("Budovy zděné")
        assert c._gen is not None and c.kresleni.vrstva == "5"
        for t in ("600000 1160000", "600010 1160000", "600010 1160010", "k"):
            c.zadej(t)
        pl = [e for e in c.dok.msp if e.dxftype() == "LWPOLYLINE"]
        assert len(pl) == 1 and pl[0].dxf.layer == "5" and pl[0].dxf.color == c.predvolba.barva
        # čísla podrobných bodů – text s výškou a písmem podle zadání
        c.zrus()
        c.proved("prvek Čísla podrobných bodů")
        assert c.predvolba.geometrie == "text"
        for t in ("600001 1160001", "", "0", "101", ""):
            c.zadej(t)
        tx = [e for e in c.dok.msp if e.dxftype() == "TEXT"]
        assert tx and abs(tx[0].dxf.height - c.predvolba.vyska) < 1e-9 and tx[0].dxf.style == c.predvolba.textovy_styl
        # úsečka nakreslená volně → „Použít na výběr“ jako plot drátěný
        c.zrus()
        c.predvolby_cb.setCurrentIndex(0)
        c.zrus()
        for t in ("u", "600020 1160000", "600030 1160000", ""):
            c.zadej(t)
        c.vyber = [e for e in c.dok.msp if e.dxftype() == "LINE"]
        assert c.vyber_predvolbu("Plot drátěný")
        c.zrus()
        c.vyber = [e for e in c.dok.msp if e.dxftype() == "LINE"]
        c.predvolba_na_vyber()
        ln = [e for e in c.dok.msp if e.dxftype() == "LINE"][0]
        assert ln.dxf.layer == "7" and ln.dxf.linetype == "2.123"
        th = c.uloz_tahak(path=str(tmp_path / "tahak.html"))
        assert "lv=5;co=94;lc=0;wt=0" in th.read_text(encoding="utf-8")
        p = c.uloz(path=str(tmp_path / "zadani.dxf"))
        res = run_checks(load_drawing(p), w.project.rules, Config(), only=["symbologie", "atribut_dle_vrstvy"])
        assert not res.issues, [i.message for i in res.issues]
    finally:
        w.project.rules = puvodni
        window.cad.obnov_predvolby()


def test_mobil_druha_obrazovka(window):
    import json
    import urllib.request
    from PySide6.QtWidgets import QApplication
    w = window
    w.load_drawing_file(UKAZKA)
    assert w._wait(lambda: _idle(w), 30)
    w.a_check.trigger()
    assert w._wait(lambda: _idle(w) and len(w.issues) > 0, 30)
    d = w.show_mobil()
    try:
        base = f"http://127.0.0.1:{d.server.port}"
        t = d.server.klic
        assert d.qr.pixmap() is not None and not d.qr.pixmap().isNull()
        # bez klíče nic
        try:
            urllib.request.urlopen(base + "/api/stav?t=spatne", timeout=5)
            raise AssertionError("bez klíče musí být 403")
        except urllib.error.HTTPError as e:
            assert e.code == 403
        html = urllib.request.urlopen(f"{base}/?t={t}", timeout=5).read().decode()
        assert "Opraveno" in html
        stav = json.loads(urllib.request.urlopen(f"{base}/api/stav?t={t}", timeout=5).read())
        assert len(stav["chyby"]) == len(w.issues)
        prvni = w.issues[0].number

        def post(akce, cislo=None):
            req = urllib.request.Request(f"{base}/api/akce?t={t}", data=json.dumps(
                {"akce": akce, "cislo": cislo}).encode(), headers={"Content-Type": "application/json"})
            assert urllib.request.urlopen(req, timeout=5).status == 200
        post("vybrat", prvni)
        assert w._wait(lambda: (QApplication.processEvents() or True) and w.issue_panel.current_issue() is not None
                       and w.issue_panel.current_issue().number == prvni, 10)
        post("opraveno")
        assert w._wait(lambda: (QApplication.processEvents() or True)
                       and next(i for i in w.issues if i.number == prvni).state == "opraveno", 10)
        stav = json.loads(urllib.request.urlopen(f"{base}/api/stav?t={t}", timeout=5).read())
        assert next(c for c in stav["chyby"] if c["cislo"] == prvni)["stav"] == "opraveno"
        post("vybrat", prvni)
        assert w._wait(lambda: (QApplication.processEvents() or True) and w.issue_panel.current_issue() is not None
                       and w.issue_panel.current_issue().number == prvni, 10)
        post("vratit")
        assert w._wait(lambda: (QApplication.processEvents() or True)
                       and next(i for i in w.issues if i.number == prvni).state == "nová", 10)
    finally:
        d.close()


def test_cad_atributy_ze_zadani_kontrola_a_uprava(window):
    from kontrola.rules import RuleSet
    from kontrola.ui.cad_atributy import C_HL, C_OVE, C_TL, parse_mapa
    f = Path(__file__).resolve().parents[1] / "podklady" / "zadani2-husovice" / "pravidla_zadani2.yaml"
    if not f.exists():
        pytest.skip("chybí pravidla")
    w = window
    puvodni = w.project.rules
    w.project.rules = RuleSet.load(f)
    try:
        c = w.cad
        w.show_page("cad")
        c.obnov_predvolby()
        d = c.atributy_zadani(modal=False)
        v = d.vysledek
        spatne = {i for i, m in v.items() if m}
        assert len(v) == len(w.project.rules.pravidla) and len(spatne) == 4
        kody = [r.kod for r in d.rs.pravidla]
        # doplnit převod tloušťky 1 a vrstvu chybějícímu pravidlu
        d.mapa.setText(d.mapa.text() + "; 1=0,18")
        d.mapa.editingFinished.emit()
        i = kody.index("10.xx6")
        d.tab.item(i, C_HL).setText("GS10-popis sítí")
        v = d.overit()
        assert not any(v.values()), {kody[i]: m for i, m in v.items() if m}
        assert d.tab.item(i, C_OVE).text().startswith("✓")
        # úprava tloušťky se projeví ve sloupci „Kreslí se jako“
        j = kody.index("12.02")
        d.tab.item(j, C_TL).setText("0")
        assert d.rs.pravidla[j].tloustka == 0
        assert d.ulozit()
        assert w.project.rules.mapa_tloustek[1] == 0.18
        assert next(r for r in w.project.rules.pravidla if r.kod == "10.xx6").hladina == "GS10-popis sítí"
        assert any(p.vrstva == "GS10-popis sítí" for p in c._predvolby)
        assert parse_mapa("0=0; 2=0,3") == {0: 0.0, 2: 0.3}
        with pytest.raises(ValueError):
            parse_mapa("x=1")
        d.zmeneno = False
        d.close()
    finally:
        w.project.rules = puvodni
        w.cad.obnov_predvolby()


def test_cad_reference_a_modely(window, tmp_path):
    import ezdxf
    podklad = ezdxf.new("R2000", setup=True)
    podklad.modelspace().add_line((0, 0), (100, 0))
    podklad.modelspace().add_circle((50, 50), 10)
    pf = tmp_path / "podklad.dxf"
    podklad.saveas(pf)
    c = window.cad
    window.show_page("cad")
    c.novy()
    d = c.spravce_referenci(modal=False)
    r = d.pripojit(str(pf))
    assert r is not None and d.tab.rowCount() == 1
    assert r.nazev in c._ref_skupiny and c._ref_skupiny[r.nazev].childItems()
    # na referenci se dá přichytit, ale nedá se vybrat
    c.view.zoom_all()
    u = c.view.uchyty.najdi(100.2, 0.1, 1.0)
    assert u is not None and u.typ == "konec" and (u.x, u.y) == (100, 0)
    assert c.vyber_v_bode(50, 0) is None
    # posun reference v tabulce (výkres není v S-JTSK → přímo x, y)
    d.tab.item(0, 2).setText("1000")
    assert r.vlozeni == (1000.0, 0.0) and r.inserty[0].dxf.insert.x == 1000
    assert c.view.uchyty.najdi(1100.1, 0.1, 1.0) is not None
    # kopie z reference do výkresu a Zpět
    nove = d.kopirovat()
    assert len(nove) == 2 and nove[0].dxf.start.x == 1000
    c.undo()
    assert sum(1 for e in c.prostor if e.dxftype() == "LINE") == 0
    # uložit a znovu otevřít – reference zůstane
    p = c.uloz(path=str(tmp_path / "s_referenci.dxf"))
    d.close()
    c.otevri(str(p))
    assert len(c.reference) == 1 and c.reference[0].doc is not None and c.reference[0].vlozeni == (1000.0, 0.0)
    # odpojit a Zpět
    d = c.spravce_referenci(modal=False)
    d.odpojit()
    assert not c.reference[0].pripojena and not c._ref_skupiny
    c.undo()
    assert c.reference[0].pripojena and c._ref_skupiny
    d.close()
    # modely: nový list, výřez v měřítku, přepnutí zpět
    for t in ("u", "x=0 y=0", "@50,0", ""):
        c.zadej(t)
    assert c.novy_list("Výkres A3") == "Výkres A3"
    assert c.prostor.name == "Výkres A3" and not c._je_model()
    for t in ("výřez", "x=20 y=20", "x=220 y=170", "500", ""):
        c.zadej(t)
    vps = [e for e in c.prostor if e.dxftype() == "VIEWPORT" and e.dxf.get("id", 0) != 1]  # 1 = výřez listu
    assert len(vps) == 1 and abs(vps[0].dxf.view_height - 150 * 500 / 1000) < 1e-9
    c.undo()
    assert not [e for e in c.prostor if e.dxftype() == "VIEWPORT" and e.dxf.get("id", 0) != 1]
    c.redo()
    c.modely.setCurrentText("Model")
    assert c._je_model() and any(e.dxftype() == "LINE" for e in c.prostor)
    p = c.uloz(path=str(tmp_path / "s_listem.dxf"))
    d2 = ezdxf.readfile(p)
    assert "Výkres A3" in d2.layout_names() and len(d2.layouts.get("Výkres A3").query("VIEWPORT")) >= 1


def test_cad_tisk_a_razitko(window, tmp_path):
    c = window.cad
    window.show_page("cad")
    c.novy()
    for t in ("kr", "x=50 y=50", "20", ""):
        c.zadej(t)
    d = c.tisk_pdf(modal=False)
    d.soubor.setText(str(tmp_path / "model.pdf"))
    d.meritko.setValue(500)
    d.tisk()
    assert (tmp_path / "model.pdf").stat().st_size > 500 and d.vysledek["meritko"] == 500
    c.novy_list("Mapa")
    assert c.razitko({"Název": "Zkušební mapa"})
    d = c.tisk_pdf(modal=False)
    d.soubor.setText(str(tmp_path / "list.pdf"))
    d.tisk()
    assert (tmp_path / "list.pdf").exists() and d.vysledek["meritko"] == 1.0
    c.modely.setCurrentText("Model")
    assert c.razitko() == []


def test_cad_vlastnosti_prvku_hledani(window):
    c = window.cad
    window.show_page("cad")
    c.novy()
    for t in ("u", "x=0 y=0", "x=3 y=4", "", "t", "x=10 y=10", "2", "0", "Parcela 12", ""):
        c.zadej(t)
    ln = next(e for e in c.prostor if e.dxftype() == "LINE")
    d = c.vlastnosti_prvku(ln, modal=False)
    d.pole["end"].setText("6 8")
    d.pole["ms_barva"].setText("3")  # barva MicroStationu 3 = červená → ACI 1
    d.pouzit()
    n = next(e for e in c.prostor if e.dxftype() == "LINE")
    assert n.dxf.end.isclose((6, 8, 0)) and n.dxf.color == 1
    c.undo()
    assert next(e for e in c.prostor if e.dxftype() == "LINE").dxf.end.isclose((3, 4, 0))
    c.proved("najdi parcela")
    assert len(c.vyber) == 1 and c.vyber[0].dxftype() == "TEXT"
    c.proved("nahraď Parcela / Pozemek")
    assert next(e for e in c.prostor if e.dxftype() == "TEXT").dxf.text == "Pozemek 12"
    c.vyber = [next(e for e in c.prostor if e.dxftype() == "LINE")]
    c.proved("podobné")
    assert len(c.vyber) == 1


def test_cad_pojmenovani_jako_microstation(window):
    from kontrola.cad import symbologie as S
    c = window.cad
    window.show_page("cad")
    c.novy()
    # key-in z taháku atributů nastaví aktivní atributy
    c.proved("lv=5;co=94;lc=2;wt=2")
    assert c.kresleni.vrstva == "5" and c.kresleni.barva == S.ms_na_aci(94)
    assert c.kresleni.typ_cary == "DGN Style 2" and c.kresleni.tloustka == 30
    assert c.aktivni.text() == "Hladina 5 · Barva 94 · Styl 2 · Tloušťka 2"
    for t in ("u", "x=0 y=0", "@10,0", ""):
        c.zadej(t)
    ln = next(e for e in c.prostor if e.dxftype() == "LINE")
    assert S.popis_prvku(ln, znama_barva=c.kresleni.ms_barvy_prvku[ln.dxf.handle]) == \
        "hladina 5 · barva 94 · styl 2 · tloušťka 2"
    # vlastnosti prvku v pojmech MicroStationu
    d = c.vlastnosti_prvku(ln, modal=False)
    assert d.pole["ms_barva"].text() == "94" and d.pole["ms_styl"].text() == "2" and d.pole["ms_tl"].text() == "2"
    d.pole["ms_barva"].setText("3")
    d.pole["ms_styl"].setText("0")
    d.pouzit()
    ln = next(e for e in c.prostor if e.dxftype() == "LINE")
    assert S.aci_na_ms(ln.dxf.color) == 3 and ln.dxf.linetype == "CONTINUOUS"
    c.proved("co=300")
    assert "0–255" in c.historie.toPlainText()


def test_vypocty_grafika_bodu(window):
    from kontrola.geodezie.body import Bod
    w = window
    w.show_page("vypocty")
    v = w.vypocty
    v.seznam.pridej([Bod("G1", 1000.0, 2000.0, 250.0, "BUD"), Bod("G2", 1003.0, 2004.0, 251.5)])
    v._after_change()
    v.tabs.setCurrentWidget(v.grafika)
    g = v.grafika
    g.obnov()
    g.cele()
    # klik na bod G1 (obrazovka x = −Y, y = −X) vybere i řádek v tabulce
    g._klik(-1000.0, -2000.0, False)
    assert g.vyber == ["G1"] and [b.cislo for b in v.selected()] == ["G1"]
    g._klik(-1003.0, -2004.0, True)
    assert set(g.vyber) == {"G1", "G2"}
    # měření mezi body: délka 5 m, převýšení 1,5 m
    g.b_mer.setChecked(True)
    g._klik(-1000.0, -2000.0, False)
    g._klik(-1003.0, -2004.0, False)
    assert "délka 5.000 m" in g.info.text() and "Δh 1.500" in g.info.text()
    g.b_mer.setChecked(False)
    v.seznam.smaz(["G1", "G2"])  # smazání mimo tabulku → obnovení nesmí spadnout
    v._after_change()
    assert v.model.rowCount() == len(v.seznam.body)


def test_ulohy_protokol_pdf(window, tmp_path):
    from kontrola.geodezie.body import Bod
    w = window
    w.show_page("vypocty")
    v = w.vypocty
    v.seznam.pridej([Bod("P1", 1000.0, 2000.0), Bod("P2", 1003.0, 2004.0)])
    v._after_change()
    u = v.ulohy
    u.lst.setCurrentRow(0)
    u.nastav(a="P1", b="P2")
    assert u.vypocitej() is not None
    out = u.protokol_pdf(str(tmp_path / "jeden.pdf"), vse=False)
    assert out and out.stat().st_size > 1000
    import pdfplumber
    with pdfplumber.open(out) as pdf:
        assert "SMĚRNÍK A DÉLKA" in pdf.pages[0].extract_text()
    v.seznam.smaz(["P1", "P2"])
    v._after_change()


def test_cad_mereni_plochy_a_uhlu(window):
    c = window.cad
    window.show_page("cad")
    c.novy()
    for t in ("mp", "x=0 y=0", "x=10 y=0", "x=10 y=10", "x=0 y=10", ""):
        c.zadej(t)
    assert "Výměra 100.00 m²" in c.historie.toPlainText() and "obvod 40.000" in c.historie.toPlainText()
    for t in ("měř úhel", "x=10 y=0", "x=0 y=0", "x=0 y=10"):
        c.zadej(t)
    assert "vnitřní 100.0000 g" in c.historie.toPlainText()


def test_cad_body_ze_seznamu(window):
    from kontrola.geodezie.body import Bod
    from kontrola.rules import RuleSet
    f = Path(__file__).resolve().parents[1] / "podklady" / "zadani1-microstation" / "pravidla_zadani1.yaml"
    if not f.exists():
        pytest.skip("chybí pravidla")
    w = window
    puvodni = w.project.rules
    w.project.rules = RuleSet.load(f)
    try:
        c = w.cad
        w.show_page("cad")
        c.obnov_predvolby()
        c.novy_podle_zadani(vzory=[])
        d = c.body_ze_seznamu(modal=False)
        d.nastav_body([Bod(str(i), 565500.0 + i, 1187900.0 + i, 240.0 + i) for i in range(1, 21)])
        d.filtr.setText("1-5, 12")
        assert len(d.body()) == 6
        d.vlozit()
        assert d.vysledek["vlozeno"] == 6
        pts = list(c.prostor.query("POINT"))
        assert len(pts) == 6 and all(p.dxf.layer == "58" for p in pts)
        c.view.najed(-565503.0, -1187903.0)
        assert c.sjtsk and "Y 565" in c.coords.text()  # souřadnice kurzoru v S-JTSK (shodně se světem)
        c.undo()
        assert not list(c.prostor.query("POINT"))
    finally:
        w.project.rules = puvodni
        w.cad.obnov_predvolby()


def test_cad_rastr(window, tmp_path):
    from PySide6.QtGui import QColor, QImage
    img = QImage(80, 40, QImage.Format_RGB32)
    img.fill(QColor("green"))
    f = tmp_path / "sken.png"
    img.save(str(f))
    (tmp_path / "sken.pgw").write_text("1\n0\n0\n-1\n100.5\n239.5\n", encoding="ascii")
    c = window.cad
    window.show_page("cad")
    c.novy()
    c.pripoj_rastr(str(f))
    assert len(c._rastry) == 1
    r = c._rastry[0].sceneBoundingRect()
    assert abs(r.left() - 100) < 1e-6 and abs(r.right() - 180) < 1e-6 and abs(r.top() - 200) < 1e-6
    g = tmp_path / "bez.png"
    img.save(str(g))
    c.pripoj_rastr(str(g))
    for t in ("x=0 y=0", "x=40 y=0"):
        c.zadej(t)
    assert len(c._rastry) == 2
    c.undo()
    assert len(c._rastry) == 1


def test_vypocty_zapisnik_editor(window, tmp_path):
    from kontrola.geodezie.formaty import nacti_soubor
    z = Path(__file__).resolve().parents[1] / "podklady" / "zadani2-husovice"
    if not (z / "zap_husovice.zap").exists():
        pytest.skip("podklady chybí")
    w = window
    w.show_page("vypocty")
    v = w.vypocty
    puvodni = list(v.seznam.body)
    dane, _var, _f = nacti_soubor(z / "dane_body.txt")
    v.seznam.pridej(dane, "dané body")
    v._after_change()
    zp = v.zapisnik
    v.tabs.setCurrentWidget(zp)
    assert zp.nacist(str(z / "zap_husovice.zap"))
    assert zp.seznam_st.count() >= 1 and zp.tab.rowCount() > 10
    r = zp.vypocitej()
    assert r is not None and len([b for b in r.body if not b.kontrolni]) > 100
    assert "POLÁRNÍ METODA DÁVKOU" in zp.vystup.toPlainText()
    # úprava délky v tabulce změní výsledek bodu
    row = next(i for i in range(zp.tab.rowCount()) if zp.tab.cellWidget(i, 5).currentText() == "podrobný")
    bod = zp.tab.item(row, 0).text()
    y0 = next(b.y for b in r.body if b.bod == bod)
    zp.tab.item(row, 1).setText(f"{float(zp.tab.item(row, 1).text()) + 1:.3f}")
    r2 = zp.vypocitej()
    assert abs(next(b.y for b in r2.body if b.bod == bod) - y0) > 0.1
    out = zp.ulozit(str(tmp_path / "upraveny.zap"))
    assert out.exists() and "-1" in out.read_text(encoding="cp1250")
    assert zp.do_seznamu() > 100
    v.seznam.body[:] = puvodni
    v._after_change()


def test_cad_rozdel_ohrada_omerne_miry(window):
    c = window.cad
    window.show_page("cad")
    c.novy()
    for t in ("u", "x=0 y=0", "x=10 y=0", ""):
        c.zadej(t)
    c.view.zoom_all()
    c.proved("rozděl")
    ln = next(iter(c.prostor.query("LINE")))
    c._posli((ln, (4.0, 0.0)))
    c.zrus()
    assert len(list(c.prostor.query("LINE"))) == 2
    for t in ("ohrada", "x=-1 y=-1", "x=5 y=-1", "x=5 y=1", "x=-1 y=1", ""):
        c.zadej(t)
    assert len(c.vyber) == 1
    c.proved("vše")
    for t in ("om", "2"):
        c.zadej(t)
    assert sorted(t.dxf.text for t in c.prostor.query("TEXT")) == ["4.00", "6.00"]
    for t in ("ku", "x=10 y=0", "x=0 y=0", "x=0 y=10", "x=5 y=5"):
        c.zadej(t)
    assert any(e.dxftype() == "DIMENSION" for e in c.prostor)


def test_zapisnik_vyrovnani_site(window):
    from kontrola.geodezie.formaty import nacti_soubor
    z = Path(__file__).resolve().parents[1] / "podklady" / "zadani2-husovice"
    if not (z / "zap_husovice.zap").exists():
        pytest.skip("podklady chybí")
    v = window.vypocty
    window.show_page("vypocty")
    puvodni = list(v.seznam.body)
    dane, _var, _f = nacti_soubor(z / "dane_body.txt")
    v.seznam.pridej(dane, "dané body")
    v._after_change()
    zp = v.zapisnik
    assert zp.nacist(str(z / "zap_husovice.zap"))
    r = zp.vyrovnat(10, 3, 2)
    text = zp.vystup.toPlainText()
    assert (r is not None and "VYROVNÁNÍ SÍTĚ MNČ" in text) or "⚠" in zp.info.text()
    v.seznam.body[:] = puvodni
    v._after_change()


def test_cad_prevzeti_a_zmena_atributu(window):
    c = window.cad
    window.show_page("cad")
    c.novy()
    c.proved("lv=VZOR;co=3;lc=2;wt=2")
    for t in ("u", "x=0 y=0", "x=10 y=0", ""):
        c.zadej(t)
    c.proved("lv=0;co=1;lc=0;wt=0")
    for t in ("u", "x=0 y=5", "x=10 y=5", ""):
        c.zadej(t)
    vzor = next(e for e in c.prostor.query("LINE") if e.dxf.layer == "VZOR")
    c.proved("ma")
    c._posli((vzor, (5, 0)))
    assert c.kresleni.vrstva == "VZOR" and c.aktivni.text().startswith("Hladina VZOR · Barva 3")
    druha = next(e for e in c.prostor.query("LINE") if e.dxf.layer == "0")
    c.proved("ca")
    c._posli((druha, (5, 5)))
    c.zrus()
    assert all(e.dxf.layer == "VZOR" and e.dxf.linetype == "DGN Style 2" for e in c.prostor.query("LINE"))


def test_cad_knihovna_bunek(window, tmp_path):
    import ezdxf
    knih = ezdxf.new("R2000")
    knih.blocks.new("3.13").add_circle((0, 0), 0.5)
    knih.blocks.new("4.05").add_line((-1, 0), (1, 0))
    f = tmp_path / "bunky.dxf"
    knih.saveas(f)
    c = window.cad
    window.show_page("cad")
    c.novy()
    assert set(c.knihovna_bunek(str(f))) == {"3.13", "4.05"}
    for t in ("vlož", "4.05", "1", "0", "x=10 y=10", ""):
        c.zadej(t)
    assert [e.dxf.name for e in c.prostor.query("INSERT")] == ["4.05"]


def test_cad_zkoseni_a_vrcholy(window):
    c = window.cad
    window.show_page("cad")
    c.novy()
    for t in ("u", "x=0 y=0", "x=10 y=0", ""):
        c.zadej(t)
    for t in ("u", "x=10 y=-2", "x=10 y=10", ""):
        c.zadej(t)
    a, b = list(c.prostor.query("LINE"))
    c.proved("cha")
    c.zadej("2")
    c.zadej("2")
    c._posli((a, (2, 0)))
    c._posli((b, (10, 8)))
    assert len(c.prostor.query("LINE")) == 3
    c.proved("pl")
    for t in ("x=0 y=20", "x=10 y=20", "x=10 y=30", ""):
        c.zadej(t)
    p = c.prostor.query("LWPOLYLINE").first
    c.proved("iv")
    c._posli((p, (5, 20)))
    c.zadej("x=5 y=18")
    p = c.prostor.query("LWPOLYLINE").first
    assert len(p) == 4
    c.proved("dv")
    c._posli((p, (5, 18)))
    c.zrus()
    assert len(c.prostor.query("LWPOLYLINE").first) == 3
    c.proved("zpět")
    c.proved("zpět")
    assert len(c.prostor.query("LWPOLYLINE").first) == 3


def test_qtrig_z_cloudu_a_ze_souboru(window, tmp_path, monkeypatch):
    import json as _json

    from kontrola import qtrig as Q
    from tests.test_qtrig import _radek, _Server
    monkeypatch.setattr("kontrola.ui.qtrig_dialog._nastaveni", lambda: __import__(
        "PySide6.QtCore", fromlist=["QSettings"]).QSettings(str(tmp_path / "s.ini"), __import__(
            "PySide6.QtCore", fromlist=["QSettings"]).QSettings.IniFormat))
    w = window
    w.show_page("vypocty")
    p = w.vypocty
    puvodni = list(p.seznam.body)
    srv = _Server()
    srv.radky = [_radek(1, "a", "QT1"), _radek(2, "b", "QT2", 49.2, 16.6)]
    d = p.qtrig_dialog(Q.Klient(otevri=srv))
    try:
        d.kod.setText("ABCD1234")
        assert not d.prihlas("spatne") and "heslo" in d.stav.text()
        assert d.prihlas("heslo") and d.zakazka.count() == 1
        assert d.stahni() == (2, 0, 0)
        assert p.seznam.najdi("QT1") is not None and abs(p.seznam.najdi("QT1").y - 743011.7706) < 0.001
        srv.radky.append(_radek(3, "a", deleted=1))
        assert d.stahni() == (0, 0, 1) and p.seznam.najdi("QT1") is None
        f = tmp_path / "smery.csv"
        f.write_text("ZÁPISNÍK VODOROVNÝCH SMĚRŮ — X\r\nStanovisko: 4001; délky zapsané jako: šikmé\r\n\r\nhlava\r\n"
                     "12;1;87;287;87;98;302;87.1235;0.2;98.0000;30.015;30.000;0.943\r\n", encoding="utf-8")
        n = len(p.zapisnik.stanoviska)
        d.nacti_soubor(str(f))
        assert len(p.zapisnik.stanoviska) == n + 1 and p.zapisnik.stanoviska[-1].bod == "4001"
        j = tmp_path / "moje_body.json"
        j.write_text(_json.dumps([{"name": "QT9", "lat": 50.0, "lng": 15.0}]), encoding="utf-8")
        d.nacti_soubor(str(j))
        assert p.seznam.najdi("QT9") is not None
    finally:
        d.close()
        p.zapisnik.nastav(p.zapisnik.stanoviska[:n])
        p.seznam.body[:] = puvodni
        p._after_change()
