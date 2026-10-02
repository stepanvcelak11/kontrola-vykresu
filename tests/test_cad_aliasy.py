import collections
import re
from pathlib import Path


def test_zkratky_prikazu_se_neprepisuji():
    """Zkratka příkazu (např. „tr“ = ořež) nesmí být ve slovníku ALIASY dvakrát – druhá by tiše přepsala první."""
    s = (Path(__file__).resolve().parents[1] / "kontrola" / "ui" / "cad_page.py").read_text(encoding="utf-8")
    i = s.index("    ALIASY = {")
    j = s.index("\n    }", i)
    klice = re.findall(r'"([^"]+)":', s[i:j])
    assert [k for k, c in collections.Counter(klice).items() if c > 1] == []
