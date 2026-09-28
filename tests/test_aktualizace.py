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
