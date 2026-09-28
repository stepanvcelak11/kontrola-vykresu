"""Načítání nastavení kontrol z projektu."""

from kontrola.checks.base import Severity
from kontrola.config import Config


def test_kontrola_bez_zavaznosti_ma_vychozi():
    cfg = Config.from_dict({"verze_nastaveni": 3, "kontroly": {"visici_konce": {"okraj": 2.0}}})
    assert cfg.settings("visici_konce").zavaznost == Severity.VAROVANI
    assert cfg.settings("visici_konce").parametry["okraj"] == 2.0


def test_starsi_projekt_volne_konce_nejsou_chyba():
    cfg = Config.from_dict({"verze_nastaveni": 2, "kontroly": {"visici_konce": {"zavaznost": "chyba"}}})
    assert cfg.settings("visici_konce").zavaznost == Severity.VAROVANI
    # v novém projektu si uživatel „chybu“ nastavit může
    cfg = Config.from_dict({"verze_nastaveni": 3, "kontroly": {"visici_konce": {"zavaznost": "chyba"}}})
    assert cfg.settings("visici_konce").zavaznost == Severity.CHYBA
