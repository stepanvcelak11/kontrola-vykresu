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
