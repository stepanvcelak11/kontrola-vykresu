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
