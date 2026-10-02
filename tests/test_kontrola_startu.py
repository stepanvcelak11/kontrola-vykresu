from kontrola import kontrola_startu as K


def test_vse_v_poradku():
    assert K.zkontroluj() == []
    assert K.main() == 0


def test_pozna_blokaci_windows(monkeypatch):
    def blok(modul):
        raise ImportError("DLL load failed while importing _multiarray_umath: An Application Control policy "
                          "has blocked this file.")
    monkeypatch.setattr(K.importlib, "import_module", blok)
    chyby = K.zkontroluj()
    assert chyby and all(c.startswith("BLOKACE:") for c in chyby)
    assert K.main() == 1


def test_konzole_bez_cestiny(monkeypatch):
    import io
    import sys
    out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(K, "zkontroluj", lambda: ["Knihovna numpy nejde načíst: chybí"])
    assert K.main() == 1
    out.flush()
    assert b"SPU" in out.buffer.getvalue()
