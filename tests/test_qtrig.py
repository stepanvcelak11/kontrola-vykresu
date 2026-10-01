"""Propojení s QTrig: převod bodů z WGS84, zápisníky z exportu a přírůstková synchronizace z cloudu."""

import io
import json
import urllib.error

import pytest

from kontrola import qtrig as Q
from kontrola.geodezie import sjtsk

# referenční hodnoty z PROJ pro definici EPSG:5514 v QTrig (+towgs84=570.8,85.7,462.8,4.998,1.587,5.261,3.56)
REF = [((50.08, 14.42), (743011.7706, 1043823.1631)), ((49.2, 16.6), (598682.8836, 1160149.6554)),
       ((48.8, 18.9), (435246.2983, 1219999.0963))]


def test_prevod_jako_qtrig():
    for (la, lo), (y, x) in REF:
        b = Q.bod_z_qtrig({"id": "cp_1", "name": "4001", "lat": la, "lng": lo, "vyska": 251.3, "kod": "plot"})
        assert abs(b.y - y) < 0.001 and abs(b.x - x) < 0.001
        assert b.cislo == "4001" and b.z == 251.3 and b.kod == "plot"
    # bod zadaný v QTrig souřadnicemi S-JTSK: QTrig uloží WGS84 zpřesněné Newtonem (zpresniLL),
    # aby dopředný převod vrátil přesně zadané Y, X – stejný dopředný převod je tady
    cil = (743011.771, 1043823.163)
    la, lo, _ = sjtsk.sjtsk_na_wgs84(*cil, parametry=sjtsk.HELMERT_PROJ4)
    for _i in range(3):
        f = sjtsk.wgs84_na_sjtsk(la, lo, parametry=sjtsk.HELMERT_PROJ4)
        h = 1e-6
        fa = sjtsk.wgs84_na_sjtsk(la + h, lo, parametry=sjtsk.HELMERT_PROJ4)
        fo = sjtsk.wgs84_na_sjtsk(la, lo + h, parametry=sjtsk.HELMERT_PROJ4)
        a11, a12, a21, a22 = (fa[0] - f[0]) / h, (fo[0] - f[0]) / h, (fa[1] - f[1]) / h, (fo[1] - f[1]) / h
        r1, r2 = cil[0] - f[0], cil[1] - f[1]
        det = a11 * a22 - a12 * a21
        la, lo = la + (r1 * a22 - a12 * r2) / det, lo + (a11 * r2 - a21 * r1) / det
    b = Q.bod_z_qtrig({"name": "1", "lat": la, "lng": lo})
    assert (b.y, b.x) == pytest.approx((743011.771, 1043823.163), abs=5e-4)
    assert Q.bod_z_qtrig({"name": "Vídeň", "lat": 48.2, "lng": 16.37}) is not None
    assert Q.bod_z_qtrig({"name": "Paříž", "lat": 48.85, "lng": 2.35}) is None


def test_soubory(tmp_path):
    f = tmp_path / "moje_body_default.json"
    f.write_text(json.dumps([{"id": "a", "name": "1", "lat": 50.08, "lng": 14.42, "acc": 0.02},
                             {"id": "b", "name": "2", "lat": 49.2, "lng": 16.6, "kod": "roh"}]), encoding="utf-8")
    body = Q.nacti_soubor(f)
    assert [b.cislo for b in body] == ["1", "2"] and "0.02" in body[0].poznamka
    niv = tmp_path / "nivelace.csv"
    niv.write_text("﻿NIVELAČNÍ ZÁPISNÍK — Pořad A\r\nVýchozí výška: 250.000 m\r\n\r\n"
                   "bod;zpět z (m);vpřed p (m);h (m);výška (m)\r\nA;1.234;;;250.000\r\n1;1.100;0.987;0.247;250.247\r\n"
                   "B;;1.500;-0.400;249.847\r\n\r\nΣz=2.334 m; Σp=2.487 m; Σh=-0.153 m\r\n", encoding="utf-8", newline="")
    n = Q.nacti_soubor(niv)
    assert n.nazev == "Pořad A" and n.vychozi_vyska == 250.0
    assert n.radky == [("A", 1.234, None), ("1", 1.1, 0.987), ("B", None, 1.5)]
    sm = tmp_path / "smery.csv"
    hl = ("cíl;skupina;Hz I (gon);Hz II (gon);red. (gon);zenit I (gon);zenit II (gon);Ø red. (gon);rozptyl (mgon);"
          "Ø zenit (gon);délka zapsaná (m);vodorovná (m);převýšení (m)")
    sm.write_text("ZÁPISNÍK VODOROVNÝCH SMĚRŮ — St 4001\r\nStanovisko: 4001; délky zapsané jako: šikmé\r\n\r\n"
                  f"{hl}\r\n5001;1;0.0000;200.0010;0.0000;100.0000;300.0000;0.0000;0.0;100.0000;50.000;50.000;0.000\r\n"
                  "5001;2;100.0000;300.0000;0.0000;;;\r\n"
                  "12;1;87.1234;287.1236;87.1235;98.0000;302.0000;87.1235;0.2;98.0000;30.015;30.000;0.943\r\n",
                  encoding="utf-8", newline="")
    s = Q.nacti_soubor(sm)
    assert s.stanovisko == "4001" and [c[0] for c in s.cile] == ["5001", "12"]
    st = Q.smery_na_stanovisko(s, 1.6)
    assert st.bod == "4001" and st.detail[1].hz == 87.1235
    assert st.detail[1].sd * __import__("math").sin(98 * __import__("math").pi / 200) == pytest.approx(30.0)
    spatny = tmp_path / "x.csv"
    spatny.write_text("něco;jiného\n", encoding="utf-8")
    with pytest.raises(Q.ChybaQTrig):
        Q.nacti_soubor(spatny)


class _Server:
    """Napodobenina workeru QTrig (login, jobs, sync/points se stránkováním)."""

    def __init__(self):
        self.radky = []
        self.dotazy = []

    def __call__(self, req, timeout=None):
        from urllib.parse import parse_qs, urlparse
        u = urlparse(req.full_url)
        self.dotazy.append((req.get_method(), u.path, u.query))
        if u.path == "/login":
            b = json.loads(req.data)
            if b.get("password") != "heslo":
                raise urllib.error.HTTPError(req.full_url, 401, "x", {},
                                             io.BytesIO(b'{"error":"Nespr\\u00e1vn\\u00fd k\\u00f3d nebo heslo."}'))
            return io.BytesIO(json.dumps({"token": "TOK", "user": {"name": "Štěpán"},
                                          "config": {"firm": {"name": "Moje firma"}}}).encode())
        assert req.headers.get("Authorization") == "Bearer TOK"
        if u.path == "/jobs":
            return io.BytesIO(json.dumps({"jobs": [{"key": "chodov", "name": "Chodov"},
                                                   {"key": "stara", "name": "Stará", "deleted": 1}]}).encode())
        if u.path == "/sync/points":
            q = parse_qs(u.query)
            since = int(q["since"][0])
            nove = [r for r in self.radky if r["srv"] > since][:2]  # stránka po dvou
            return io.BytesIO(json.dumps({"points": nove, "more": len(nove) == 2}).encode())
        raise AssertionError(u.path)


def _radek(srv, pid, name=None, lat=50.08, lng=14.42, deleted=0):
    d = None if deleted else json.dumps({"id": pid, "name": name, "lat": lat, "lng": lng})
    return {"id": pid, "data": d, "ts": srv, "srv": srv, "deleted": deleted}


def test_cloud_prirustkova_synchronizace():
    srv = _Server()
    k = Q.Klient(otevri=srv)
    with pytest.raises(Q.ChybaQTrig, match="heslo"):
        k.prihlas("ABCD1234", "spatne")
    k.prihlas("ABCD1234", "heslo")
    assert k.uzivatel == "Štěpán" and k.firma == "Moje firma"
    assert [z["name"] for z in k.zakazky()] == ["Chodov"]
    srv.radky = [_radek(1, "a", "1"), _radek(2, "b", "2", 49.2, 16.6), _radek(3, "c", "3")]
    body, smazane, stav = Q.sync(k, Q.StavSync(), "chodov")
    assert sorted(b.cislo for b in body) == ["1", "2", "3"] and stav.kurzor == 3 and not smazane
    # na mobilu: bod 2 opraven, bod 3 smazán, přibyl 4 – stáhnou se jen změny
    srv.radky += [_radek(4, "b", "2", 49.21, 16.6), _radek(5, "c", deleted=1), _radek(6, "d", "4")]
    pocet = len(srv.dotazy)
    body, smazane, stav = Q.sync(k, stav, "chodov")
    assert sorted(b.cislo for b in body) == ["1", "2", "4"] and smazane == ["3"] and stav.kurzor == 6
    assert "since=3" in srv.dotazy[pocet][2]  # přírůstkově od posledního kurzoru
    assert Q.klic_zakazky("  Chodov   Sever ") == "chodov sever"


def test_slouceni_do_seznamu_a_nivelace():
    from kontrola.geodezie.body import Bod, SeznamBodu
    s = SeznamBodu()
    s.pridej([Bod("1", 1, 1, poznamka="ručně"), Bod("2", 2, 2, poznamka="QTrig"), Bod("3", 3, 3, poznamka="QTrig")])
    nove, zmenene, smazane = Q.sloucit(s, [Bod("2", 2.5, 2, poznamka="QTrig"), Bod("3", 3, 3, poznamka="QTrig"),
                                           Bod("4", 4, 4, poznamka="QTrig")], ["1", "9"])
    assert (nove, zmenene, smazane) == (1, 1, 0)  # ručně zadaný bod 1 se nesmaže
    assert s.najdi("2").y == 2.5 and s.najdi("4") is not None
    Q.sloucit(s, [], ["3"])
    assert s.najdi("3") is None
    s.zpet()
    s.zpet()
    assert s.najdi("4") is None and s.najdi("2").y == 2  # jedno Zpět vrátí celé stažení
    n = Q.NivelaceQTrig("A", 250.0, [("A", 1.234, None), ("1", 1.1, 0.987), ("B", None, 1.5)])
    vysky, prot = Q.nivelace_vypocet(n)
    assert vysky == [("A", 250.0), ("1", pytest.approx(250.247)), ("B", pytest.approx(249.847))]
    assert "NIVELACE" in prot[0]
