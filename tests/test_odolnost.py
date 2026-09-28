"""Odolnost: bezpečné ukládání a zápis chyb do logu."""

from pathlib import Path


def test_atomicky_zapis_neprepise_pri_chybe(tmp_path, monkeypatch):
    from kontrola import safeio
    f = tmp_path / "projekt.yaml"
    safeio.write_text_atomic(f, "puvodni")

    def boom(*a, **k):
        raise OSError("plný disk")
    monkeypatch.setattr(safeio.os, "replace", boom)
    try:
        safeio.write_text_atomic(f, "nove")
    except OSError:
        pass
    assert f.read_text() == "puvodni"
    assert not [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]


def test_log_chyb(tmp_path, monkeypatch):
    from kontrola.ui import crash
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    try:
        raise ValueError("testovací chyba")
    except ValueError as e:
        crash.write_log(crash.report_text(type(e), e, e.__traceback__))
    text = crash.log_file().read_text(encoding="utf-8")
    assert "testovací chyba" in text and "verze" in text
    assert Path(crash.log_file()).parent.name == "logy"
