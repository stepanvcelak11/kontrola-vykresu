"""Panel „Prvek“: vlastnosti prvku, na který se kliklo ve výkresu, srovnání s pravidlem a jeho chyby."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QTextBrowser, QVBoxLayout, QWidget

from ..checks.base import Issue, fmt_num
from ..model import Drawing, Feature, GeomType
from ..rules import RuleSet, color_matches, linetype_matches


def _ok(flag: bool | None) -> str:
    if flag is None:
        return ""
    return (" <span style='color:#16A34A'>✓</span>" if flag else
            " <span style='color:#DC2626'><b>✗</b></span>")


def feature_html(f: Feature, drawing: Drawing, rules: RuleSet, issues: list[Issue]) -> str:
    from ..checks.attributes import _norm_font, _what
    rows: list[tuple[str, str]] = []
    r = rules.resolve(f) if rules.pravidla else None
    rows.append(("Typ", escape(_what(f)) + f" <span style='color:#6B7280'>({f.dxftype})</span>"))
    lay_ok = r.matches_layer(f.layer) if (r and r.hladina) else None
    rows.append(("Vrstva", escape(f.layer) + _ok(lay_ok) + (f" – má být {escape(r.hladina)}" if lay_ok is False
                                                          else "")))
    col = rules.describe_feature_color(f)
    col_ok = color_matches(r.barva, f, rules.paleta, rules.barevna_tabulka) if (r and r.barva is not None) else None
    rows.append(("Barva", escape(col) + (" (dle vrstvy)" if "barva" in f.bylayer else "") + _ok(col_ok)
                 + (f" – má být {escape(str(r.barva))}" if col_ok is False else "")))
    if f.geom_type in (GeomType.LINIE, GeomType.POLYGON):
        st_ok = linetype_matches(r.styl_cary, f.linetype) if (r and r.styl_cary) else None
        rows.append(("Styl", escape(f.linetype) + _ok(st_ok) + (f" – má být {escape(r.styl_cary)}" if st_ok is False
                                                              else "")))
        if f.ltscale != 1.0 or (r and r.meritko_stylu):
            ok = abs(f.ltscale - r.meritko_stylu) < 1e-4 if (r and r.meritko_stylu) else None
            rows.append(("Měřítko stylu", fmt_num(f.ltscale, 3) + _ok(ok)))
    if f.geom_type != GeomType.TEXT:
        exp, _ = rules.expected_weights(r) if (r and r.tloustka is not None) else ([], [])
        ok = any(abs(w - f.lineweight) <= 0.051 for w in exp) if exp else None
        rows.append(("Tloušťka", f"{fmt_num(f.lineweight, 2)} mm" + _ok(ok)
                     + (f" – má být {escape(str(r.tloustka))}" if ok is False else "")))
    if f.geom_type == GeomType.TEXT:
        rows.append(("Text", f"„{escape(f.text or '')}“"))
        font_ok = (_norm_font(r.font) in _norm_font(f.font)) if (r and r.font and f.font) else None
        rows.append(("Font", escape(f.font or "–") + _ok(font_ok)))
        h = f.text_height
        exp_h = rules.text_size(r.vyska_textu) if (r and r.vyska_textu) else None
        h_txt = f"{fmt_num(h, 3)} m"
        if rules.meritko:
            h_txt += f" ({fmt_num(h * 1000 / rules.meritko, 2)} mm na papíře)"
        rows.append(("Výška", h_txt + _ok(abs(h - exp_h) <= max(0.005, 0.02 * exp_h) if exp_h else None)))
    if f.block_name:
        rows.append(("Buňka", escape(f.block_name)))
    g = f.geometry
    if f.geom_type == GeomType.LINIE:
        rows.append(("Délka", f"{fmt_num(g.length, 3)} m, vrcholů {len(g.coords)}"))
    elif f.geom_type == GeomType.POLYGON:
        rows.append(("Plocha", f"{fmt_num(g.area, 2)} m², obvod {fmt_num(g.length, 2)} m"))
    elif g is not None and g.geom_type == "Point":
        rows.append(("Souřadnice", f"Y {fmt_num(g.x, 3)}, X {fmt_num(g.y, 3)}"))
    li = drawing.layers.get(f.layer)
    if li is not None and (li.off or li.frozen):
        rows.append(("Pozor", "<span style='color:#B45309'>vrstva je ve výkresu vypnutá – v MicroStationu prvek "
                              "neuvidíte, dokud ji nezapnete</span>"))
    html = "<table cellspacing=0 cellpadding=3>" + "".join(
        f"<tr><td style='color:#6B7280; padding-right:10px'>{k}</td><td>{v}</td></tr>" for k, v in rows) + "</table>"
    if r is not None:
        html += (f"<p><b>Pravidlo:</b> {escape(r.nazev or r.kod)} "
                 f"<span style='color:#6B7280'>({escape(r.kod)}{', ' + escape(r.zdroj) if r.zdroj else ''})</span></p>")
    elif rules.pravidla:
        html += "<p><b>Pravidlo:</b> <span style='color:#B45309'>žádné – prvek neodpovídá Směrnici</span></p>"
    mine = [i for i in issues if f.fid in i.feature_ids]
    if mine:
        html += "<p><b>Chyby u prvku:</b><br>" + "<br>".join(
            f"#{i.number} {escape(i.check_name)}: {escape(i.message)}" for i in mine) + "</p>"
    else:
        html += "<p style='color:#16A34A'>U tohoto prvku kontrola nic nenašla.</p>"
    return html


class InspectorPanel(QWidget):
    issueRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.hint = QLabel("Klikněte ve výkresu na čáru, bod, text nebo buňku – zobrazí se tu její vlastnosti, "
                           "co o ní říká Směrnice a jestli je v pořádku.")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: palette(mid);")
        lay.addWidget(self.hint)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        lay.addWidget(self.view, 1)

    def show_feature(self, f: Feature | None, drawing: Drawing | None, rules: RuleSet, issues: list[Issue]):
        if f is None or drawing is None:
            self.view.setHtml("<p style='color:#6B7280'>V místě kliknutí není žádný prvek.</p>")
            return
        self.view.setHtml(feature_html(f, drawing, rules, issues))
