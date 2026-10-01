"""Kontrola aktualizací: čtení čísla sestavení z popisu vydání."""

from kontrola import aktualizace


def test_cislo_sestaveni_z_popisu():
    assert aktualizace.parse_build("Sestavení č. 57 – automaticky z commitu abc") == 57
    assert aktualizace.parse_build("Automaticky sestaveno") is None
    assert aktualizace.is_newer(58, 57) and not aktualizace.is_newer(57, 57)
    assert not aktualizace.is_newer(None, 57)


def test_bez_sestaveni_se_nic_nehlasi(monkeypatch):
    monkeypatch.setattr(aktualizace, "BUILD", None)
    assert not aktualizace.is_newer(100)
    assert "zdrojových" in aktualizace.version_text()


def test_stazeni_a_davka_nahrazeni(tmp_path, monkeypatch):
    import io

    from kontrola import aktualizace
    data = b"MZ" + b"\0" * 6_000_000

    class R(io.BytesIO):
        headers = {"Content-Length": str(len(data))}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(aktualizace.urllib.request, "urlopen", lambda *a, **k: R(data))
    seen = []
    p = aktualizace.download(tmp_path / "n.exe", lambda d, t: seen.append((d, t)))
    assert p.stat().st_size == len(data) and seen[-1] == (len(data), len(data))
    monkeypatch.setattr(aktualizace.urllib.request, "urlopen", lambda *a, **k: R(b"<html>chyba</html>"))
    import pytest
    with pytest.raises(OSError):
        aktualizace.download(tmp_path / "x.exe")
    assert not (tmp_path / "x.exe").exists()
    bat = aktualizace.updater_script(1234, r"C:\\t\\n.exe", r"C:\\P\\KontrolaVykresu.exe")
    assert 'PID eq 1234' in bat and 'move /y' in bat and 'start ""' in bat
