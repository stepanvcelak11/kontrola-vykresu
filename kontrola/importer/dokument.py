"""Čtení textu zadání z Wordu (DOC, DOCX), ODT, RTF, PDF a TXT – bez Wordu na počítači.

Kromě textu vrací i tabulky (DOCX, ODT) a z textu vytáhne požadavky, které se hodí při kontrole:
měřítko, písmo, velikost písma, tolerance, názvy vrstev, formát souboru, termíny…
"""

from __future__ import annotations

import re
import struct
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

DOC_EXT = {".doc", ".docx", ".odt", ".rtf", ".txt", ".pdf"}

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"


@dataclass
class Dokument:
    path: Path
    odstavce: list[str] = field(default_factory=list)
    tabulky: list[list[list[str]]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.odstavce)


def read_document(path: str | Path) -> Dokument:
    path = Path(path)
    suf = path.suffix.lower()
    if suf == ".docx":
        return _docx(path)
    if suf == ".odt":
        return _odt(path)
    if suf == ".doc":
        return Dokument(path, _split(_doc_text(path)))
    if suf == ".rtf":
        return Dokument(path, _split(_rtf_text(path.read_bytes().decode("latin-1"))))
    if suf == ".pdf":
        import pdfplumber
        paras, tables = [], []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                paras += _split(page.extract_text() or "")
                for t in page.extract_tables() or []:
                    tables.append([[(c or "").strip() for c in row] for row in t])
        return Dokument(path, paras, tables)
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            return Dokument(path, _split(raw.decode(enc)))
        except UnicodeDecodeError:
            continue
    return Dokument(path)


def _split(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0b", "\n").replace("\x07", "\t")
    return [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in text.split("\n") if ln.strip()]


# ---------------------------------------------------------------- DOCX / ODT
def _docx(path: Path) -> Dokument:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(f"{_W}body")
    doc = Dokument(path)

    def para_text(p) -> str:
        parts = []
        for el in p.iter():
            if el.tag == f"{_W}t" and el.text:
                parts.append(el.text)
            elif el.tag == f"{_W}tab":
                parts.append("\t")
            elif el.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        return "".join(parts)

    for el in (body if body is not None else []):
        if el.tag == f"{_W}p":
            doc.odstavce += _split(para_text(el))
        elif el.tag == f"{_W}tbl":
            rows = []
            for tr in el.iter(f"{_W}tr"):
                rows.append([" ".join(_split(" ".join(para_text(p) for p in tc.iter(f"{_W}p"))))
                             for tc in tr.findall(f"{_W}tc")])
            doc.tabulky.append(rows)
            doc.odstavce += [" | ".join(r) for r in rows if any(r)]
    return doc


def _odt(path: Path) -> Dokument:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("content.xml"))
    doc = Dokument(path)

    def txt(el) -> str:
        return "".join(el.itertext())

    for el in root.iter():
        if el.tag in (f"{_TEXT}p", f"{_TEXT}h") and not _inside_table(el, root):
            doc.odstavce += _split(txt(el))
        elif el.tag == f"{_TABLE}table":
            rows = [[" ".join(_split(txt(c))) for c in tr.findall(f"{_TABLE}table-cell")]
                    for tr in el.iter(f"{_TABLE}table-row")]
            doc.tabulky.append(rows)
            doc.odstavce += [" | ".join(r) for r in rows if any(r)]
    return doc


def _inside_table(el, root) -> bool:
    parents = {c: p for p in root.iter() for c in p}
    p = parents.get(el)
    while p is not None:
        if p.tag == f"{_TABLE}table-cell":
            return True
        p = parents.get(p)
    return False


# ---------------------------------------------------------------- RTF
def _rtf_text(rtf: str) -> str:
    out = []
    rtf = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("cp1250", "replace"), rtf)
    rtf = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), rtf)
    rtf = re.sub(r"\\(par|line)\b ?", "\n", rtf)
    rtf = re.sub(r"\\tab\b ?", "\t", rtf)
    rtf = re.sub(r"\{\\\*[^{}]*\}", "", rtf)
    rtf = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", rtf)
    out.append(rtf.replace("{", "").replace("}", ""))
    return "".join(out)


# ---------------------------------------------------------------- DOC (Word 97–2003)
def _doc_text(path: Path) -> str:
    """Text ze starého Wordu (.doc) podle tabulky kusů (piece table) – bez Wordu a bez LibreOffice."""
    import olefile
    ole = olefile.OleFileIO(str(path))
    try:
        wd = ole.openstream("WordDocument").read()
        flags = struct.unpack_from("<H", wd, 0x0A)[0]
        table_name = "1Table" if flags & 0x0200 else "0Table"
        if not ole.exists(table_name):
            table_name = "0Table" if table_name == "1Table" else "1Table"
        tbl = ole.openstream(table_name).read()
        # FibRgFcLcb97: fcClx / lcbClx (index 33 v poli fcLcb)
        csw = struct.unpack_from("<H", wd, 32)[0]
        pos = 34 + csw * 2
        cslw = struct.unpack_from("<H", wd, pos)[0]
        pos += 2 + cslw * 4
        pos += 2  # cbRgFcLcb
        fc_clx, lcb_clx = struct.unpack_from("<II", wd, pos + 33 * 8)
        clx = tbl[fc_clx:fc_clx + lcb_clx]
        i = 0
        while i < len(clx) and clx[i] == 0x01:  # Prc (formátování) přeskočit
            cb = struct.unpack_from("<H", clx, i + 1)[0]
            i += 3 + cb
        if i >= len(clx) or clx[i] != 0x02:
            return _doc_fallback(wd)
        lcb = struct.unpack_from("<I", clx, i + 1)[0]
        plc = clx[i + 5:i + 5 + lcb]
        n = (lcb - 4) // 12
        cps = struct.unpack_from(f"<{n + 1}I", plc, 0)
        parts = []
        for k in range(n):
            pcd = plc[(n + 1) * 4 + k * 8:(n + 1) * 4 + (k + 1) * 8]
            fc = struct.unpack_from("<I", pcd, 2)[0]
            cnt = cps[k + 1] - cps[k]
            if fc & 0x40000000:  # 8bitový text (cp1252)
                start = (fc & 0x3FFFFFFF) // 2
                parts.append(wd[start:start + cnt].decode("cp1252", "replace"))
            else:
                parts.append(wd[fc:fc + cnt * 2].decode("utf-16-le", "replace"))
        text = "".join(parts)
    finally:
        ole.close()
    # řídicí znaky Wordu: pole (0x13–0x15), obrázky (0x01, 0x08), konec buňky (0x07)
    text = re.sub(r"\x13[^\x14\x15]*\x14?", "", text).replace("\x15", "")
    return re.sub(r"[\x00-\x06\x08\x0e-\x1f]", "", text)


def _doc_fallback(wd: bytes) -> str:
    return re.sub(r"[^\w\s.,;:()\-–/%+=°]", " ", wd.decode("utf-16-le", "ignore"))


# ---------------------------------------------------------------- požadavky ze zadání
_REQ = [
    ("Měřítko", r"(?:měřítk\w*\s*)?\b1\s*:\s*(\d[\d\s]{2,6})\b"),
    ("Písmo", r"\b(?:font|písm\w*)\b[^.\n]{0,40}?\b((?:Arial(?: Narrow)?|Times(?: New Roman)?|ISOCP\w*|"
              r"Romans?|Engineering|CS [A-Za-z]+|Monotxt|Microstation \w+)\b)"),
    ("Výška písma", r"\b(?:výšk\w* (?:písma|textu)|velikost\w* písma)\b[^.\n]{0,30}?(\d+(?:[.,]\d+)?\s*mm)"),
    ("Tolerance", r"\b(?:toleranc\w*|přesnost\w*|odchylk\w*)\b[^.\n]{0,40}?(\d+(?:[.,]\d+)?\s*(?:mm|cm|m)\b)"),
    ("Formát odevzdání", r"\b(DGN|DXF|DWG|PDF)\b[^.\n]{0,30}?\b(?:formát\w*|odevzd\w*|soubor\w*)|"
                         r"\b(?:formát\w*|odevzd\w*)\b[^.\n]{0,40}?\b(DGN|DXF|DWG|PDF)\b"),
    ("Název souboru", r"\b(?:název|pojmenov\w*|označení)\b[^.\n]{0,20}?\bsoubor\w*[^.\n]{0,20}?[„\"']?([\w\-]+\."
                      r"(?:dgn|dxf|pdf))"),
    ("Termín", r"\b(?:termín\w*|do dne|odevzd\w* do)\b[^.\n]{0,20}?(\d{1,2}\.\s?\d{1,2}\.(?:\s?\d{2,4})?)"),
    ("Souřadnicový systém", r"\b(S-?JTSK|Bpv|ETRS\w*|WGS\s?84)\b"),
    ("Vrstva", r"\b(?:vrstv\w*|hladin\w*|level\w*)\s+(?:č\.\s*)?[„\"']?([A-Z0-9][\w\-+ ]{0,40}?[\w])[“\"']?(?=[\s,.;)]|$)"),
]
_KEYWORDS = ("musí", "nesmí", "povinn", "je nutné", "nutno", "vyžad", "dodržet", "pozor", "nezapomeň",
             "odevzd", "hodnot", "srážka", "bod")


@dataclass
class Pozadavek:
    druh: str
    hodnota: str
    veta: str


def requirements(doc: Dokument, limit: int = 60) -> list[Pozadavek]:
    """Požadavky ze zadání: konkrétní hodnoty (měřítko, písmo, tolerance…) a věty s „musí/nesmí…“."""
    out: list[Pozadavek] = []
    seen: set[tuple[str, str]] = set()
    for para in doc.odstavce:
        for sent in re.split(r"(?<=[.!?])\s+", para):
            s = sent.strip()
            if len(s) < 4:
                continue
            for druh, rx in _REQ:
                for m in re.finditer(rx, s, flags=re.IGNORECASE if druh != "Vrstva" else 0):
                    val = next((g for g in m.groups() if g), m.group(0)).strip()
                    if druh == "Měřítko":
                        val = "1:" + val.replace(" ", "")
                    key = (druh, val.lower())
                    if key not in seen:
                        seen.add(key)
                        out.append(Pozadavek(druh, val, s))
            low = s.lower()
            if any(k in low for k in _KEYWORDS[:9]) and ("Pokyn", s) not in seen:
                seen.add(("Pokyn", s))
                out.append(Pozadavek("Pokyn", "", s))
            if len(out) >= limit:
                return out
    return out


def _metres(v: str) -> float | None:
    m = re.match(r"(\d+(?:[.,]\d+)?)\s*(mm|cm|m)\b", v.strip())
    if not m:
        return None
    return _num(m.group(1)) * {"mm": 0.001, "cm": 0.01, "m": 1.0}[m.group(2)]


def document_settings(doc: Dokument) -> dict:
    """Hodnoty ze zadání, které jdou použít v nastavení kontroly: měřítko kresby, tolerance, písmo, formát."""
    out: dict = {}
    text = "\n".join(doc.odstavce)
    sc = _scale(_SCALE_DST, text)
    reqs = requirements(doc, limit=400)
    if sc is None:
        scales = [int(q.hodnota[2:]) for q in reqs if q.druh == "Měřítko" and q.hodnota[2:].isdigit()]
        scales = [x for x in scales if 50 <= x <= 100000]
        if scales:
            sc = max(set(scales), key=scales.count)
    if sc:
        out["meritko"] = sc
    for q in reqs:
        if q.druh == "Tolerance" and "tolerance" not in out:
            m = _metres(q.hodnota)
            low = q.veta.lower()
            if any(w in low for w in ("uxy", "tříd", "tríd", "kód kvality", "střední")):
                continue  # přesnost mapování, ne tolerance kresby
            if m is not None and 0.0001 <= m <= 0.5:
                out["tolerance"] = (m, q.veta)
        elif q.druh == "Písmo" and "pismo" not in out:
            out["pismo"] = q.hodnota
        elif q.druh == "Formát odevzdání" and "format" not in out:
            out["format"] = q.hodnota.upper()
    return out


def looks_like_rules_table(rows: list[list[str]]) -> bool:
    """Tabulka ve Wordu, ze které jdou udělat pravidla (má sloupec vrstva/level a barva/styl/písmo)."""
    if len(rows) < 2:
        return False
    head = " ".join(" ".join(r).lower() for r in rows[:3])
    return bool(re.search(r"vrstv|hladin|level", head)) and bool(re.search(r"barv|styl|tlouš|font|písm|buňk", head))


# ---------------------------------------------------------------- popisy vrstev → pravidla
_HEAD = re.compile(r"^(?:Vrstva|Hladina|Level)\s+(?:č\.\s*)?(\d{1,3})\s*[-–—:]\s*(.+)$", re.IGNORECASE)
_SCALE_SRC = re.compile(r"platí\s+pro\s+měřítk\w*\s*1\s*:\s*([\d\s]{3,7})", re.IGNORECASE)
_SCALE_DST = re.compile(r"(?:kresb\w*|výkres\w*)[^.\n]{0,30}?\bměřítk\w*\s*1\s*:\s*([\d\s]{3,7})", re.IGNORECASE)


def _num(s: str) -> float:
    return float(s.replace(",", ".").replace(" ", ""))


def _scale(rx, text: str) -> int | None:
    m = rx.search(text)
    return int(m.group(1).replace(" ", "")) if m else None


def layer_rules(doc: Dokument, rules_meritko: int | None = None):
    """Pravidla z popisu vrstev ve Wordu („Vrstva 58 – podrobné body… Barva 0, Tloušťka čáry 2…“).

    Výšky písma v metrech se přepočtou z měřítka, pro které hodnoty platí („platí pro měřítko 1 : 1 000“),
    na měřítko kresby („Kresbu proveďte pro měřítko 1 : 500“). Pokud pravidla počítají písmo v mm na papíře
    (``rules_meritko``), uloží se v mm.
    """
    from ..model import GeomType
    from ..rules import Rule
    text = doc.text
    src = _scale(_SCALE_SRC, text)
    dst = _scale(_SCALE_DST, text) or src
    heads = [(i, m) for i, p in enumerate(doc.odstavce) if (m := _HEAD.match(p))]
    out = []
    for n, (i, m) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else min(len(doc.odstavce), i + 5)
        body = " ".join(doc.odstavce[i + 1:min(end, i + 5)])
        low = body.lower()
        title = m.group(2).strip(" .")
        title = title[:1].upper() + title[1:].lower() if title.isupper() or sum(c.isupper() for c in title) > 6 \
            else title
        r = Rule(kod=f"Vrstva {m.group(1)}", nazev=title, hladina=m.group(1),
                 zdroj=f"{doc.path.name} (popis vrstvy {m.group(1)})")
        typ = re.search(r"typ\w*\s+(?:kresebn\w+\s+)?prvk\w*\s+(.{0,40})", low)
        typ = typ.group(1) if typ else low[:60]
        if typ.startswith("text") or " text " in f" {typ[:12]} ":
            r.geometrie, r.typy_prvku = GeomType.TEXT, [17]
        elif "nulové délky" in typ or re.match(r"(bod|úsečk\w* \(nul)", typ):
            r.geometrie, r.typy_prvku = GeomType.BOD, [3]
            r.poznamka = "bod = úsečka nulové délky („umístit aktivní bod“)"
        elif "buňk" in typ:
            r.geometrie = GeomType.BOD
        elif re.match(r"(úsečk|lomen|čár|lini)", typ):
            r.geometrie = GeomType.LINIE
        if (b := re.search(r"\bbarv\w*\s+(\d{1,3})\b", low)):
            r.barva = int(b.group(1))
        if (t := re.search(r"\btloušťk\w*(?:\s+čáry)?\s+(\d{1,2})\b", low)):
            r.tloustka = float(t.group(1))
        if (s := re.search(r"\bstyl\w*(?:\s+čáry)?\s+(\d{1,2})\b", low)):
            r.styl_cary = s.group(1)
        if (f := re.search(r"\bfont\s+(?:\d+\s*[-–]\s*)?([A-Za-z][\w ]{1,30}?)(?=\s+(?:vztažn|výšk|šířk|tloušťk|barv|zarovn)|$)",
                           body, re.IGNORECASE)):
            r.font = f.group(1).strip()
        if (a := re.search(r"\b(?:vztažný bod|zarovnání)\s+((?:vlevo|vpravo|na střed|uprostřed|střed)"
                           r"(?:\s+(?:nahoře|dole|uprostřed))?)", low)):
            r.zarovnani = a.group(1)
        for key, attr in (("výšk", "vyska_textu"), ("šířk", "sirka_textu")):
            if (h := re.search(rf"\b{key}\w*\s+textu\s+(\d+(?:[.,]\d+)?)\s*(mm|m)\b", low)):
                val, unit = _num(h.group(1)), h.group(2)
                paper_mm = val if unit == "mm" else (val * 1000 / src if src else None)
                if rules_meritko and paper_mm is not None:
                    setattr(r, attr, round(paper_mm, 3))
                elif paper_mm is not None and dst:
                    setattr(r, attr, round(paper_mm * dst / 1000, 4))
                else:
                    setattr(r, attr, val)
        if src and dst and src != dst and (r.vyska_textu or r.sirka_textu):
            r.zdroj += f"; písmo přepočteno z 1:{src} na 1:{dst}"
        if any(v is not None for v in (r.barva, r.tloustka, r.font, r.vyska_textu, r.geometrie)):
            out.append(r)
    return out
