"""Rozhraní webové verze: výsledky jako JSON, stejné výpočty jako na desktopu."""

import json
from pathlib import Path

import pytest

from kontrola import web_api as W

P = Path(__file__).resolve().parents[1] / "podklady" / "zadani2-husovice"
BODY = [{"c": "1", "y": 1000.0, "x": 2000.0, "z": 250.0}, {"c": "2", "y": 1100.0, "x": 2000.0, "z": None},
        {"c": "3", "y": 1100.0, "x": 2100.0}, {"c": "4", "y": 1000.0, "x": 2100.0}]


def test_ulohy_a_vypocet():
    u = json.loads(W.ulohy())
    assert len(u) > 15 and u[0]["pole"][0]["key"] == "a"
    i = next(n for n, x in enumerate(u) if x["nazev"] == "Výměra a obvod")
    r = json.loads(W.spocti(i, json.dumps(BODY), json.dumps({"body": "1 2 3 4"})))
    assert "10000.00" in r["protokol"].replace(" ", "") or "10 000" in r["protokol"]
    r = json.loads(W.spocti(0, json.dumps(BODY), json.dumps({"a": "1", "b": "99"})))
    assert "99" in r["chyba"]
    i = next(n for n, x in enumerate(u) if x["nazev"].startswith("Bod ze staničení"))
    r = json.loads(W.spocti(i, json.dumps(BODY), json.dumps({"a": "1", "b": "2", "st": "50", "kol": "10",
                                                               "nove": "5"})))
    assert r["nove"][0]["c"] == "5" and abs(r["nove"][0]["y"] - 1050.0) < 1e-6


def test_seznam_souradnic(tmp_path):
    f = tmp_path / "s.txt"
    f.write_text("1 1000.00 2000.00 250.00\n2 1100,5 2000\nxx\n", encoding="utf-8")
    d = json.loads(W.nacti_seznam(str(f)))
    assert [b["c"] for b in d["body"]] == ["1", "2"]
    t = W.seznam_text(json.dumps(BODY))
    assert t.splitlines()[0].split() == ["1", "1000.00", "2000.00", "250.00"]
    assert W.seznam_text(json.dumps(BODY), ";").splitlines()[1].startswith("1;1000.00")


def test_polarni_metoda_ze_zapisniku():
    if not (P / "zap_husovice.zap").exists():
        pytest.skip("chybí podklady")
    from kontrola.geodezie.formaty import nacti_soubor
    body, _v, _f = nacti_soubor(P / "dane_body.txt")
    r = json.loads(W.polarni(str(P / "zap_husovice.zap"), json.dumps(W._body_json(body))))
    assert "chyba" not in r, r
    assert len(r["nove"]) > 5 and "POLÁRNÍ" in r["protokol"].upper()
    assert json.loads(W.polarni(str(P / "zap_husovice.zap"), "[]"))["chyba"]


def test_vrstevnice_dxf(tmp_path):
    import ezdxf
    body = [{"c": f"{i}{j}", "y": 1000 + i * 10.0, "x": 2000 + j * 10.0, "z": 250 + i * 2.0} for i in range(5) for j in range(5)]
    r = json.loads(W.vrstevnice_dxf(json.dumps(body), json.dumps({"interval": "1"})))
    f = tmp_path / "v.dxf"
    f.write_text(r["dxf"], encoding="utf-8")
    d = ezdxf.readfile(f)
    assert len(d.modelspace().query('LWPOLYLINE[layer=="VRSTEVNICE_ZAKLADNI"]')) >= 6 and "TIN" in r["souhrn"]
    assert "chyba" in json.loads(W.vrstevnice_dxf("[]", "{}"))


def test_kontrola_exporty_a_nastroje():
    if not (P / "zap_husovice.zap").exists():
        pytest.skip("chybí podklady")
    vykres = next(P.glob("Husovice_*_mapa.dxf"))
    seznam = next(P.glob("Husovice_*_seznam.txt"))
    k = json.loads(W.kontroly())
    assert len(k) > 20 and all("nazev" in x for x in k)
    vyp = [x["id"] for x in k if x["zapnuto"]][:1]
    j = json.loads(W.zkontroluj(str(vykres), None, str(seznam), None, json.dumps({"vypnute": vyp, "tolerance": 0.02})))
    assert j["chyby"] and j["vrstvy"] and all(c["kid"] != vyp[0] for c in j["chyby"])
    for druh in ("html", "pdf", "oprava", "xlsx", "csv", "dxf", "log"):
        r = json.loads(W.export(druh))
        assert Path(r["soubor"]).stat().st_size > 100, druh
    o = json.loads(W.oprava(json.dumps({"symbologie": False})))
    assert Path(o["soubor"]).exists() and "oprav" in o["text"].lower()
    assert "verdikt" in json.loads(W.predikce())
    assert json.loads(W.porovnej(str(vykres)))["zmeny"] == []
    c = next(c for c in j["chyby"] if c["x"] is not None)
    assert json.loads(W.prvek_na(c["x"], c["y"], 0.5)).get("vlastnosti")


def test_zapisnik_vyrovnani_kontrola_vypoctu():
    if not (P / "zap_husovice.zap").exists():
        pytest.skip("chybí podklady")
    from kontrola.geodezie.formaty import nacti_soubor
    body, _v, _f = nacti_soubor(P / "dane_body.txt")
    bj = json.dumps(W._body_json(body))
    z = json.loads(W.nacti_zapisnik(str(P / "zap_husovice.zap"), bj))
    zj = json.dumps(z["stanoviska"])
    assert len(z["stanoviska"]) == 2
    assert len(json.loads(W.polarni_zapisnik(zj, bj))["nove"]) > 100
    assert "σ0" in json.loads(W.vyrovnani(zj, bj))["souhrn"]
    k = json.loads(W.kontrola_vypoctu(str(next(P.glob("Husovice_*_seznam.txt"))), zj, bj))
    assert k["rozdilu"] == 0 and k["bodu"] > 100
    for druh in ("zap", "gsi"):
        assert Path(json.loads(W.zapisnik_soubor(zj, druh))["soubor"]).stat().st_size > 1000
    # .zap tam a zpět dá stejná stanoviska
    z2 = json.loads(W.nacti_zapisnik(json.loads(W.zapisnik_soubor(zj, "zap"))["soubor"], bj))
    assert sum(len(s["orient"]) + len(s["detail"]) for s in z2["stanoviska"]) == \
        sum(len(s["orient"]) + len(s["detail"]) for s in z["stanoviska"])
    r = json.loads(W.porovnej_seznamy(str(P / "dane_body.txt"), bj))
    assert "nevyhovuje 0" in r["souhrn"]
    assert json.loads(W.duplicity(bj))["pocet"] == 0
    assert Path(json.loads(W.protokol_pdf("PROTOKOL\nřádek", "p"))["soubor"]).stat().st_size > 500


def test_qtrig_ze_zalohy():
    import base64
    import gzip

    from tests.test_qtrig import _zaloha_telefonu
    b64 = base64.b64encode(gzip.compress(json.dumps(_zaloha_telefonu()).encode())).decode()
    z = json.loads(W.qtrig_zakazky(b64))
    assert {x["name"]: x["n"] for x in z} == {"Husovice": 2, "Prázdná": 0, "Výchozí zakázka": 1}
    r = json.loads(W.qtrig_body("p1"))
    assert r["nazev"] == "Husovice" and abs(r["body"][0]["y"] - 743011.77) < 0.01
    assert "chyba" in json.loads(W.qtrig_zakazky("nesmysl"))


def test_overeni_spojnice_hromadne():
    vykres = next(P.glob("Husovice_*_mapa.dxf"), None)
    if vykres is None:
        pytest.skip("chybí podklady")
    seznam = next(P.glob("Husovice_*_seznam.txt"))
    W.zkontroluj(str(vykres))
    r = json.loads(W.overeni_bodu(str(seznam)))
    assert "Nalezeno" in r["souhrn"] and r["polozky"]
    r = json.loads(W.spojnice(str(seznam), "plot: 1-2-3"))
    assert len(r["polozky"]) == 2 and "úseků" in r["souhrn"]
    r = json.loads(W.hromadne(str(vykres), str(vykres), json.dumps({})))
    assert len(r) == 2 and r[0]["skore"] == r[1]["skore"]
    r = json.loads(W.hromadne(str(P / "zap_husovice.zap"), json.dumps({})))
    assert "chyba" in r[0]
