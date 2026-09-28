"""Protokol o kontrole do PDF (souhrn, přehledka, tabulka chyb, obrázky problémových míst)."""

from __future__ import annotations

import datetime as dt
import io
from collections import Counter
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..navody import navod
from ..checks.base import Issue, Severity, fmt_num
from ..resources import resource_path

SEV_COLORS = {Severity.CHYBA: colors.HexColor("#DC1E1E"), Severity.VAROVANI: colors.HexColor("#F58C00"),
              Severity.INFO: colors.HexColor("#1E6EE6")}
_FONT = None


def _font() -> tuple[str, str]:
    """Zaregistruje písmo s českou diakritikou (přibalené DejaVu, případně Arial ve Windows)."""
    global _FONT
    if _FONT:
        return _FONT
    candidates = [
        (resource_path("fonts", "DejaVuSans.ttf"), resource_path("fonts", "DejaVuSans-Bold.ttf")),
        (Path(r"C:\Windows\Fonts\arial.ttf"), Path(r"C:\Windows\Fonts\arialbd.ttf")),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
         Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    ]
    for reg, bold in candidates:
        if reg.is_file():
            pdfmetrics.registerFont(TTFont("CZ", str(reg)))
            pdfmetrics.registerFont(TTFont("CZ-Bold", str(bold if bold.is_file() else reg)))
            from reportlab.pdfbase.pdfmetrics import registerFontFamily
            registerFontFamily("CZ", normal="CZ", bold="CZ-Bold", italic="CZ", boldItalic="CZ-Bold")
            _FONT = ("CZ", "CZ-Bold")
            return _FONT
    _FONT = ("Helvetica", "Helvetica-Bold")  # bez diakritiky
    return _FONT


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _coord(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


def export_pdf(issues: list[Issue], path: str | Path, drawing_name: str = "", project_name: str = "",
               rules_count: int = 0, images: dict[int, bytes] | None = None, overview: bytes | None = None,
               notes: list[str] | None = None, tolerance: float | None = None, image_limit: int = 60):
    font, bold = _font()
    ss = getSampleStyleSheet()
    st = {
        "h1": ParagraphStyle("h1", parent=ss["Title"], fontName=bold, fontSize=18, spaceAfter=6, alignment=TA_LEFT),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName=bold, fontSize=13, spaceBefore=10),
        "p": ParagraphStyle("p", parent=ss["Normal"], fontName=font, fontSize=9.5, leading=12),
        "small": ParagraphStyle("s", parent=ss["Normal"], fontName=font, fontSize=8, leading=10),
        "cell": ParagraphStyle("c", parent=ss["Normal"], fontName=font, fontSize=7.8, leading=9.5),
    }
    images = images or {}
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm, title="Protokol kontroly výkresu",
                            author="Kontrola výkresu")
    story = []
    story.append(Paragraph("Protokol kontroly výkresu", st["h1"]))
    meta = [["Výkres:", drawing_name or "–"], ["Projekt:", project_name or "–"],
            ["Datum kontroly:", dt.datetime.now().strftime("%d.%m.%Y %H:%M")],
            ["Počet pravidel:", str(rules_count)]]
    if tolerance is not None:
        meta.append(["Tolerance:", f"{fmt_num(tolerance, 4)} m"])
    t = Table(meta, colWidths=[35 * mm, 140 * mm])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), font, 9.5), ("FONT", (0, 0), (0, -1), bold, 9.5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story.append(t)

    # --- souhrn
    active = [i for i in issues if i.state == "nová"]
    cnt = Counter(i.severity for i in active)
    story.append(Paragraph("Souhrn", st["h2"]))
    verdict = ("Výkres neobsahuje žádné chyby." if not cnt[Severity.CHYBA] else
               f"Výkres obsahuje {cnt[Severity.CHYBA]} chyb, které je potřeba před odevzdáním opravit.")
    story.append(Paragraph(
        f"{_esc(verdict)} Nalezeno celkem {len(issues)} problémů "
        f"(chyby {cnt[Severity.CHYBA]}, varování {cnt[Severity.VAROVANI]}, info {cnt[Severity.INFO]}; "
        f"opraveno {sum(1 for i in issues if i.state == 'opraveno')}, "
        f"ignorováno {sum(1 for i in issues if i.state == 'ignorovat')}).", st["p"]))
    story.append(Spacer(1, 4))
    per: dict[str, Counter] = {}
    for i in active:
        per.setdefault(i.check_name, Counter())[i.severity] += 1
    rows = [["Typ kontroly", "Chyby", "Varování", "Info", "Celkem"]]
    for name in sorted(per, key=lambda n: (-per[n][Severity.CHYBA], n)):
        c = per[name]
        rows.append([name, c[Severity.CHYBA] or "", c[Severity.VAROVANI] or "", c[Severity.INFO] or "",
                     sum(c.values())])
    rows.append(["Celkem", cnt[Severity.CHYBA], cnt[Severity.VAROVANI], cnt[Severity.INFO], len(active)])
    t = Table(rows, colWidths=[80 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), font, 9), ("FONT", (0, 0), (-1, 0), bold, 9),
        ("FONT", (0, -1), (-1, -1), bold, 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#44546A")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("TEXTCOLOR", (1, 1), (1, -1), SEV_COLORS[Severity.CHYBA]),
        ("TEXTCOLOR", (2, 1), (2, -1), SEV_COLORS[Severity.VAROVANI]),
        ("TEXTCOLOR", (3, 1), (3, -1), SEV_COLORS[Severity.INFO]),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F2F2F2")]),
    ]))
    story.append(t)
    if notes:
        story.append(Spacer(1, 4))
        for n in notes:
            story.append(Paragraph("• " + _esc(n), st["small"]))
    if overview:
        story.append(Paragraph("Přehled výkresu s vyznačenými chybami", st["h2"]))
        story.append(_image(overview, 180 * mm, 120 * mm))

    # --- seznam chyb
    story.append(PageBreak())
    story.append(Paragraph("Seznam problémů", st["h2"]))
    rows = [["Č.", "Typ", "Záv.", "Popis", "Vrstva", "X", "Y", "Stav"]]
    for i in issues:
        rows.append([str(i.number), Paragraph(_esc(i.check_name), st["cell"]), i.severity.value,
                     Paragraph(_esc(i.message), st["cell"]), Paragraph(_esc(i.layer), st["cell"]),
                     _coord(i.x), _coord(i.y), i.state])
    t = Table(rows, colWidths=[9 * mm, 28 * mm, 14 * mm, 55 * mm, 22 * mm, 20 * mm, 21 * mm, 13 * mm],
              repeatRows=1)
    style = [("FONT", (0, 0), (-1, -1), font, 7.5), ("FONT", (0, 0), (-1, 0), bold, 7.5),
             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#44546A")),
             ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("ALIGN", (5, 1), (6, -1), "RIGHT")]
    for k, i in enumerate(issues, start=1):
        style.append(("TEXTCOLOR", (2, k), (2, k), SEV_COLORS[i.severity]))
        if i.state != "nová":
            style.append(("TEXTCOLOR", (0, k), (1, k), colors.grey))
            style.append(("TEXTCOLOR", (3, k), (-1, k), colors.grey))
    t.setStyle(TableStyle(style))
    story.append(t)

    # --- obrázky problémových míst
    if images:
        story.append(PageBreak())
        story.append(Paragraph("Problémová místa", st["h2"]))
        if len([i for i in issues if i.state == "nová"]) > image_limit:
            story.append(Paragraph(f"Zobrazeno prvních {image_limit} problémů.", st["small"]))
        by_num = {i.number: i for i in issues}
        cells = []
        for num, png in images.items():
            i = by_num.get(num)
            if i is None:
                continue
            cap = Paragraph(f"<b>#{i.number} {_esc(i.check_name)}</b> ({i.severity.value})<br/>{_esc(i.message)}"
                            f"<br/>Vrstva {_esc(i.layer)}, X {_coord(i.x)}, Y {_coord(i.y)}"
                            + (f"<br/><i>Jak opravit:</i> {_esc(navod(i))}" if navod(i) else ""), st["small"])
            cells.append([_image(png, 68 * mm, 68 * mm), cap])
        grid = []
        for k in range(0, len(cells), 2):
            pair = cells[k:k + 2]
            grid.append([[c[0], Spacer(1, 2), c[1]] for c in pair] + ([""] if len(pair) == 1 else []))
        t = Table(grid, colWidths=[90 * mm, 90 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        story.append(t)

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont(font, 7.5)
        canvas.setFillColor(colors.grey)
        canvas.drawString(15 * mm, 8 * mm, f"Kontrola výkresu – {drawing_name}")
        canvas.drawRightString(A4[0] - 15 * mm, 8 * mm, f"Strana {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path


def _image(png: bytes, max_w: float, max_h: float) -> Image:
    from reportlab.lib.utils import ImageReader
    w, h = ImageReader(io.BytesIO(png)).getSize()
    s = min(max_w / w, max_h / h)
    return Image(io.BytesIO(png), width=w * s, height=h * s)
