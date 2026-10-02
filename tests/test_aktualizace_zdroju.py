import zipfile

import pytest

from kontrola import aktualizace as A


def _zip(path, soubory):
    with zipfile.ZipFile(path, "w") as z:
        for jm, obsah in soubory.items():
            z.writestr("kontrola-vykresu-main/" + jm, obsah)
    return path


def test_rozbaleni_prepise_aplikaci_a_necha_venv(tmp_path):
    root = tmp_path / "app"
    (root / "kontrola").mkdir(parents=True)
    (root / ".venv").mkdir()
    (root / ".venv" / "x.txt").write_text("venv")
    (root / "spustit.py").write_text("stary")
    (root / "kontrola" / "stary_modul.py").write_text("pryč")
    (root / "kontrola" / "app.py").write_text("stary")
    z = _zip(tmp_path / "main.zip", {"spustit.py": "novy", "kontrola/app.py": "novy", "kontrola/novy.py": "x",
                                     ".venv/zlo.txt": "nesmí", "requirements.txt": "ezdxf"})
    n = A.rozbal_aktualizaci(z, root, sha="abc123")
    assert n == 4
    assert (root / "spustit.py").read_text() == "novy" and (root / "kontrola" / "app.py").read_text() == "novy"
    assert not (root / "kontrola" / "stary_modul.py").exists()
    assert (root / ".venv" / "x.txt").read_text() == "venv" and not (root / ".venv" / "zlo.txt").exists()
    assert A.nainstalovana_sha(root) == "abc123"


def test_cizi_zip_odmitne(tmp_path):
    z = _zip(tmp_path / "x.zip", {"neco.txt": "x"})
    (tmp_path / "app").mkdir()
    with pytest.raises(OSError):
        A.rozbal_aktualizaci(z, tmp_path / "app")


def test_pozna_zdrojovou_instalaci(tmp_path):
    (tmp_path / "spustit.py").write_text("")
    assert A.je_zdrojova_instalace(tmp_path) == (A.BUILD is None)
    (tmp_path / ".git").mkdir()
    assert not A.je_zdrojova_instalace(tmp_path)  # vývojová kopie – aktualizace přes git
