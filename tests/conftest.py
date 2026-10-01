"""Pomocné funkce pro testy: malé testovací DXF se vytvářejí přímo v testu."""

from __future__ import annotations

import sys
from pathlib import Path

import ezdxf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kontrola.config import Config  # noqa: E402
from kontrola.io import read_dxf  # noqa: E402
from kontrola.rules import RuleSet  # noqa: E402
from kontrola.runner import run_checks  # noqa: E402


@pytest.fixture
def make_dxf(tmp_path):
    """Vrátí funkci, která z callbacku ``build(msp, doc)`` vytvoří a načte DXF."""
    counter = {"n": 0}

    def _make(build, name=None):
        doc = ezdxf.new("R2013", setup=True)
        doc.header["$INSUNITS"] = 6
        msp = doc.modelspace()
        build(msp, doc)
        counter["n"] += 1
        path = tmp_path / (name or f"test{counter['n']}.dxf")
        doc.saveas(path)
        return read_dxf(path)

    return _make


def check(drawing, check_id, rules=None, config=None, **params):
    """Spustí jedinou kontrolu a vrátí seznam chyb."""
    cfg = config or Config()
    cfg.settings(check_id).parametry.update(params)
    res = run_checks(drawing, rules or RuleSet(), cfg, only=[check_id])
    assert not res.cancelled
    for n in res.notes:
        assert "selhala" not in n, n
    return res.issues


@pytest.fixture(autouse=True)
def _kalibrace_do_tmp(tmp_path, monkeypatch):
    """Kalibrace podle protokolů učitele se v testech nesmí zapisovat do dokumentů uživatele."""
    monkeypatch.setenv("KONTROLA_KALIBRACE", str(tmp_path / "kalibrace.json"))


# ------------------------------------------------------------------ trasování tichých pádů (CI na Windows)
# Na Windows CI občas proces skončí kódem 1 bez jakéhokoli výpisu. Do souboru (KONTROLA_TEST_TRACE)
# se okamžitě zapisuje začátek a konec každého testu, volání sys.exit / os._exit se zásobníkem,
# běžné ukončení Pythonu a nativní pád (faulthandler) – krok CI ho při selhání vypíše.
import os as _os  # noqa: E402

_TRACE = _os.environ.get("KONTROLA_TEST_TRACE")
if _TRACE:
    import atexit
    import faulthandler
    import threading
    import traceback

    _trace_fh = open(_TRACE, "a", encoding="utf-8", buffering=1)  # noqa: SIM115

    def _zapis(text: str):
        _trace_fh.write(text + "\n")
        _trace_fh.flush()
        try:
            _os.fsync(_trace_fh.fileno())
        except OSError:
            pass

    faulthandler.enable(file=_trace_fh, all_threads=True)
    atexit.register(lambda: _zapis("ATEXIT: Python končí normálně"))
    _puvodni_exit, _puvodni_os_exit = sys.exit, _os._exit

    def _sys_exit(code=None):
        _zapis(f"SYS.EXIT({code!r}) z vlákna {threading.current_thread().name}:\n"
               + "".join(traceback.format_stack()))
        _puvodni_exit(code)

    def _os_exit(code):
        _zapis(f"OS._EXIT({code!r}):\n" + "".join(traceback.format_stack()))
        _puvodni_os_exit(code)

    sys.exit = _sys_exit
    _os._exit = _os_exit

    _qt_handler = {}

    def _qt_zpravy():
        """Zprávy Qt (i qFatal těsně před abort) do trasování – na Windows jinak zmizí."""
        if _qt_handler or "PySide6.QtCore" not in sys.modules:
            return
        from PySide6.QtCore import qInstallMessageHandler

        def handler(typ, ctx, msg):
            _zapis(f"QT[{int(typ.value) if hasattr(typ, 'value') else typ}] {msg} ({ctx.file}:{ctx.line})")
        _qt_handler["h"] = handler
        qInstallMessageHandler(handler)

    def pytest_runtest_setup(item):
        _qt_zpravy()
        _zapis(f"SETUP {item.nodeid} vlákna={[t.name for t in threading.enumerate()]}")

    _SLEDOVAT = {"test_vypocty_seznam_souradnic"}  # test, ve kterém proces na Windows tiše umírá

    def _sledovac(frame, event, arg):
        if event == "call":
            f = frame.f_code.co_filename
            if "kontrola" in f and "site-packages" not in f:
                _zapis(f"  → {f.rsplit('kontrola', 1)[-1]}:{frame.f_code.co_name}:{frame.f_lineno}")
        return None

    def pytest_runtest_call(item):
        _zapis(f"CALL {item.nodeid}")
        if item.name in _SLEDOVAT:
            sys.settrace(_sledovac)
            threading.settrace(_sledovac)

    def pytest_runtest_makereport(item, call):
        if call.when == "call" and item.name in _SLEDOVAT:
            sys.settrace(None)
            threading.settrace(None)

    def pytest_runtest_teardown(item):
        _zapis(f"TEARDOWN {item.nodeid}")

    _selhane: list[str] = []

    def pytest_runtest_logreport(report):
        if report.failed:
            text = str(report.longrepr)[-3000:]
            _selhane.append(f"SELHAL {report.nodeid} ({report.when}):\n{text}")
            _zapis(_selhane[-1])
        if report.when == "teardown":
            _zapis(f"HOTOVO {report.nodeid} {report.outcome}")

    def pytest_sessionfinish(session, exitstatus):
        # souhrn na konec trasování – krok CI vypisuje jen jeho konec
        _zapis(f"KONEC exit={exitstatus}, selhalo {len(_selhane)}")
        for t in _selhane[:5]:
            _zapis(t)
