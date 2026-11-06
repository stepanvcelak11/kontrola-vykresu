"""Vlastní pásy karet MicroStationu CONNECT z .dgnlib (např. UM_ribbon.dgnlib pracovní sady MultiScale).

V .dgnlib jsou tlačítka pásu uložená jako binární ECXML („BECXML“) v XAttributech prvků: cesta
„pás.Karta.Skupina.Tlačítko“, popisek, ikona a key-in MicroStationu (active level …; active color …;
place line constrained / place cell / texteditor place / change attributes …). Z toho se tu sestaví
karty se skupinami tlačítek a key-iny se převedou na příkazy CAD aplikace (lv=, co=, lc=, wt=, ac=…).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Tlacitko:
    cesta: str
    popisek: str
    keyin: str
    ikona: str = ""
    popis: str = ""

    @property
    def druh(self) -> str:
        k = self.keyin.lower()
        if k.startswith("change attributes"):
            return "atributy"
        if "place cell" in k or "place_and_edit" in k or "active cell" in k and "place" in k:
            return "bunka"
        if "texteditor place" in k or "place text" in k:
            return "text"
        if "place line" in k or "place smartline" in k:
            return "cara"
        if "place shape" in k or "place block" in k:
            return "plocha"
        return "nastaveni"


@dataclass
class Pas:
    nazev: str
    soubor: Path
    karty: list[tuple[str, list[tuple[str, list[Tlacitko]]]]] = field(default_factory=list)

    @property
    def pocet(self) -> int:
        return sum(len(t) for _k, sk in self.karty for _s, t in sk)


# ------------------------------------------------------------------ čtení BECXML
def _retezce(rec: bytes) -> list[str]:
    """Řetězce záznamu BECXML v pořadí: 0xFA = jednobajtové (cp1250), 0xFB = UTF-16; délka 1 B,
    nebo 0xF1/0xF2 + 1/2 B (little endian)."""
    out, i, n = [], 0, len(rec)
    while i < n - 1:
        t = rec[i]
        if t not in (0xFA, 0xFB):
            i += 1
            continue
        j = i + 1
        d = rec[j]
        j += 1
        if d == 0xF1:
            d = rec[j]
            j += 1
        elif d == 0xF2:
            d = int.from_bytes(rec[j:j + 2], "little")
            j += 2
        elif d >= 0xF0:
            i += 1
            continue
        if t == 0xFA:
            raw = rec[j:j + d]
            j += d
            out.append(raw.decode("cp1250", "replace"))
        else:
            raw = rec[j:j + 2 * d]
            j += 2 * d
            out.append(raw.decode("utf-16-le", "replace"))
        i = j
    return out


def _po(retezce: list[str], klic: str) -> str:
    try:
        i = retezce.index(klic)
    except ValueError:
        return ""
    return retezce[i + 1] if i + 1 < len(retezce) else ""


def _zaznamy(cesta: Path) -> list[list[str]]:
    import olefile

    from ..io.dgn_v8 import _inflate
    if not olefile.isOleFile(str(cesta)):
        return []
    ole = olefile.OleFileIO(str(cesta))
    try:
        out = []
        for s in ole.listdir():
            raw = ole.openstream(s).read()
            try:
                d = _inflate(raw) or b""
            except Exception:  # noqa: BLE001 – nekomprimovaný proud
                d = b""
            for data in (d, raw):
                if b"BECXML" not in data:
                    continue
                for kus in data.split(b"BECXML\x00")[1:]:
                    out.append(_retezce(kus[:6000]))
                break
        return out
    finally:
        ole.close()


def _casti(jm: str) -> list[str]:
    """Cesta „pás.Karta.Skupina.Tlačítko“ – tečka uvnitř názvu („10._Popis“, „Hranice_k._ú.“) nedělí."""
    casti = [c for c in re.split(r"\.(?=[^_.\s])", jm) if c]
    while len(casti) > 1 and casti[0].lower() == casti[1].lower():
        casti.pop(0)
    if len(casti) > 1 and casti[1].lower() == casti[0].lower():
        casti.pop(1)
    return casti


def _hezky(segment: str) -> str:
    s = segment.replace("_", " ").strip()
    return re.sub(r"\s+-\s+empty$", "", s)


NAZVY = {"um_ribbon": "Účelová mapa (ÚM)", "pasport": "Pasportizace staveb", "tm25": "Technická mapa (TM25)", "dgnlib_gui_mapovani": "Mapování",
         "dgnlib_gui_customribbon": "Vlastní pás"}


def _norm(t: str) -> str:
    return re.sub(r"[^\w]+", " ", t.lower()).strip()


def _nastroje_drawcomp(gui: Path) -> dict[str, tuple[str, str]]:
    """Nástroje palet (Dgnlib/DrawComp vedle Dgnlib/GUI): normalizovaný název hladiny → (hladina, styl čáry)."""
    out: dict[str, tuple[str, str]] = {}
    d = gui.parent.parent / "DrawComp"
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*")):
        if f.suffix.lower() != ".dgnlib":
            continue
        try:
            zaz = _zaznamy(f)
        except Exception:  # noqa: BLE001
            continue
        for r in zaz:
            if r and r[0] == "Ustn_ElementParams":
                lv = _po(r, "Value")
                if lv:
                    out.setdefault(_norm(lv), (lv, _po(r, "LineStyle")))
    return out


def _keyin_nastroje(keyin: str, nastroje: dict[str, tuple[str, str]]) -> str:
    """„DMSG ACTIVATETOOLBYPATH Pasport\\…\\Nástroj“ → key-in hladiny a stylu nástroje + kreslení čáry."""
    cesta = keyin.split(None, 2)[2] if len(keyin.split(None, 2)) > 2 else ""
    casti = [c for c in cesta.split("\\") if c]
    if not casti:
        return ""
    if _norm(casti[-1]) in ("nový nástroj", "new tool"):
        return ""  # nepojmenovaný rozpracovaný nástroj ze školní knihovny
    n = _norm(casti[-1])
    hit = nastroje.get(n) or next((v for k, v in nastroje.items() if k.startswith(n) or (n.startswith(k) and k)),
                                  None)
    if hit is None:
        if not any("vrstv" in c.lower() for c in casti[:-1]):
            return ""
        hit = (casti[-1], "")  # TM: nástroj „název vrstvy\\…\\X“ kreslí do hladiny X
    lv, ls = hit
    k = f'active level "{lv}"'
    if ls:
        k += f'; active style "{ls}"'
    return k + "; place smartline"


def nacti_pas(cesta: str | Path) -> Pas | None:
    """Pás karet z .dgnlib: jen tlačítka s key-inem (bez maker, která tu nejdou spustit samostatně)."""
    cesta = Path(cesta)
    tl: dict[str, Tlacitko] = {}
    popisky: dict[str, str] = {}
    nastroje = _nastroje_drawcomp(cesta)
    for r in _zaznamy(cesta):
        if not r:
            continue
        jm = _po(r, "Name")
        if not jm or "." not in jm:
            continue
        lbl = _po(r, "Label")
        if lbl:
            popisky.setdefault(jm, lbl)
        k = _po(r, "Keyin")
        if not k or r[0] != "Button":
            continue
        if k.upper().startswith("DMSG ACTIVATETOOLBYPATH"):  # Pasport, TM: nástroj z palety DrawComp
            jm_nastroje = [c for c in k.split(None, 2)[-1].split("\\") if c][-1:]
            k = _keyin_nastroje(k, nastroje)
            if not k:
                continue
            if jm_nastroje and (not lbl or lbl in ("Description", "CommandType", "Name", "Nový nástroj")):
                lbl = jm_nastroje[0]  # popisek chybí nebo je výchozí – název nástroje z cesty palety
        if not re.search(r"active (level|cell|color)|change attributes|place ", k, re.I):
            continue
        tl.setdefault(jm, Tlacitko(jm, lbl, k.strip(), _po(r, "NamedIcon"), _po(r, "Description")))
    if not tl:
        return None
    karty: dict[str, dict[str, list[Tlacitko]]] = {}
    koren = None
    for jm, t in tl.items():
        casti = _casti(jm)
        if koren is None:
            koren = casti[0].lower()
        casti = [c for i, c in enumerate(casti) if not (i and c.lower() == koren)]
        if len(casti) < 3:
            continue
        cesta_k = casti[0] + "." + casti[1]
        nk = popisky.get(cesta_k) or _hezky(casti[1])
        nk = re.sub(r"(?<=\D)\d+$", "", nk).strip() or nk
        ns = (popisky.get(cesta_k + "." + casti[2]) or _hezky(casti[2])) if len(casti) > 3 else "Nástroje"
        ns = re.sub(r"\d+$", "", ns).strip() or ns
        if not t.popisek:
            t.popisek = _hezky(casti[-1])
        karty.setdefault(nk, {}).setdefault(ns, []).append(t)
    pas = Pas(NAZVY.get(cesta.stem.lower(), _hezky(cesta.stem)), cesta)
    for nk, sk in karty.items():
        pas.karty.append((nk, list(sk.items())))
    return pas


# ------------------------------------------------------------------ key-in MicroStationu → příkazy aplikace
_AKTIVNI = {"level": "lv", "color": "co", "weight": "wt", "style": "lc", "cell": "ac"}
_ZMENA = {"level": "vrstva", "color": "barva", "weight": "tloušťka", "linestyle": "styl"}


def preloz(keyin: str) -> tuple[str, list[str]]:
    """(key-iny aktivních atributů „lv=…;co=…“, příkazy k provedení po nich)."""
    nastav: list[str] = []
    prikazy: list[str] = []
    zmeny: list[str] = []
    for c in (x.strip() for x in keyin.split(";")):
        if not c:
            continue
        m = re.match(r'active (level|color|weight|style|cell)\s*"?([^"]*)"?$', c, re.I)
        if m:
            v = m.group(2).strip()
            if v:
                nastav.append(f"{_AKTIVNI[m.group(1).lower()]}={v}")
            continue
        m = re.match(r'change attributes set (level|color|weight|linestyle)\s*"?([^"]*)"?$', c, re.I)
        if m:
            zmeny.append(f"{_ZMENA[m.group(1).lower()]} {m.group(2).strip()}")
            continue
        lc = c.lower()
        if lc.startswith("place line") or lc.startswith("place smartline"):
            prikazy.append("polylinie")
        elif lc.startswith("place cell") or "place_and_edit" in lc:
            if "vlož" not in prikazy:
                prikazy.append("vlož")
        elif lc.startswith("texteditor place") or lc.startswith("place text"):
            prikazy.append("text")
        elif lc.startswith("place shape"):
            prikazy.append("polylinie")
    return ";".join(nastav), zmeny + prikazy


def pasy_ve_slozce(slozka: str | Path) -> list[Path]:
    """Soubory .dgnlib s pásy karet (složka Dgnlib/GUI pracovní sady)."""
    p = Path(slozka)
    if not p.is_dir():
        return []
    return sorted(x for x in p.rglob("*.dgnlib") if x.parent.name.lower() == "gui")
