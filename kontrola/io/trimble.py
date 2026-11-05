"""Export měření z Trimble (JobXML .jxl) podle šablony .xsl – jako Trimble File and Report.

Šablony (.xsl a jimi vkládané .xdt) jsou XSLT 1.0 od Geotronicsu / školy; vloží se stejně jako do File
and Report a výstup (protokol GNSS, seznam bodů, zápisník MAPA2, SDR33…) je stejný. Soubor .job je binární
formát Trimble General Survey – na .jxl ho převede kontrolér (Exportovat → JobXML), Trimble Business Center
nebo File and Report.
"""

from __future__ import annotations

from pathlib import Path


class TrimbleError(Exception):
    pass


def _najdi(slozka: Path, jmeno: str) -> Path | None:
    """Vkládaný soubor (.xdt) vedle šablony: přesně, bez ohledu na velikost písmen (Windows), nebo
    se jménem s předponou (soubor stažený / nahraný jako „abc123-Protokol-Head.xdt“)."""
    p = slozka / jmeno
    if p.is_file():
        return p
    low = jmeno.lower()
    kandidati = [x for x in slozka.iterdir() if x.is_file()] if slozka.is_dir() else []
    for x in kandidati:
        if x.name.lower() == low:
            return x
    for x in kandidati:
        if x.name.lower().endswith("-" + low) or x.name.lower().endswith("_" + low):
            return x
    return None


def nacti_sablonu(xsl: str | Path):
    try:
        from lxml import etree
    except ImportError as e:  # pragma: no cover – lxml je v requirements
        raise TrimbleError("Chybí knihovna lxml.") from e
    xsl = Path(xsl)
    slozka = xsl.parent

    class Resolver(etree.Resolver):
        def resolve(self, url, _id, context):
            jm = Path(str(url).replace("file://", "")).name
            p = _najdi(slozka, jm)
            return self.resolve_filename(str(p), context) if p is not None else None

    parser = etree.XMLParser()
    parser.resolvers.add(Resolver())
    # rozšíření Microsoftu (msxsl:node-set) – File and Report běží na MSXML
    ns = etree.FunctionNamespace("urn:schemas-microsoft-com:xslt")
    ns["node-set"] = lambda _ctx, x: x
    try:
        return etree.XSLT(etree.parse(str(xsl), parser))
    except (etree.XSLTParseError, etree.XMLSyntaxError, OSError) as e:
        raise TrimbleError(f"Šablonu {xsl.name} nejde načíst: {e}") from None


def exportuj(zdroj: str | Path, sablona: str | Path) -> str:
    """Výstup šablony pro JobXML (.jxl) jako text."""
    from lxml import etree
    zdroj = Path(zdroj)
    if zdroj.suffix.lower() == ".job" or zdroj.read_bytes()[:30].startswith(b"Trimble General Survey"):
        raise TrimbleError(f"{zdroj.name} je zakázka Trimble (.job) v binárním formátu – exportujte ji v kontroléru "
                           "nebo ve File and Report jako JobXML (.jxl) a vložte sem soubor .jxl.")
    t = nacti_sablonu(sablona)
    try:
        vys = t(etree.parse(str(zdroj)))
    except etree.XMLSyntaxError as e:
        raise TrimbleError(f"{zdroj.name} není JobXML: {e}") from None
    except etree.XSLTApplyError as e:
        raise TrimbleError(f"Šablona selhala: {e}") from None
    return str(vys)  # textový výstup (method="text") i XML/HTML jako text
