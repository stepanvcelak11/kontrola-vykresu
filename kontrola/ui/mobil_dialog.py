"""Okno „Mobil jako druhá obrazovka“: QR kód, adresa a propojení serveru s hlavním oknem."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from ..mobil import MobilServer, mistni_ip, qr_matice


class _Most(QObject):
    """Předá akci z vlákna serveru do hlavního vlákna (signál mezi vlákny = fronta událostí)."""

    akce = Signal(str, object)


def snimek(win) -> dict:
    """Stav pro telefon: seznam chyb a aktuální chyba s postupem opravy."""
    issues = list(getattr(win, "issues", []) or [])
    cur = win.issue_panel.current_issue() if hasattr(win, "issue_panel") else None

    def radek(i):
        return {"cislo": i.number, "zprava": i.message, "zavaznost": i.severity.value, "stav": i.state,
                "kontrola": i.check_name, "vrstva": i.layer, "y": f"{i.x:.2f}", "x": f"{i.y:.2f}"}
    akt = None
    if cur is not None:
        akt = radek(cur)
        try:
            from ..opravny_postup import krok
            k = krok(cur, win.drawing, win.project.config.tolerance if win.project else 0.01)
            akt["postup"] = list(k.postup[:6]) if k else []
        except Exception:  # noqa: BLE001 – postup je jen pomůcka
            akt["postup"] = []
    zbyva = sum(1 for i in issues if i.state == "nová" and i.severity.value != "info")
    nazev = win.drawing_path.name if getattr(win, "drawing_path", None) else "Žádný výkres"
    return {"vykres": nazev, "souhrn": f"Zbývá opravit: {zbyva} z {len(issues)}",
            "chyby": [radek(i) for i in issues[:500]], "aktualni": akt}


class MobilDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Mobil jako druhá obrazovka")
        self.most = _Most(self)
        self.most.akce.connect(self._akce, Qt.QueuedConnection)
        self.server = MobilServer(lambda a, c: self.most.akce.emit(a, c)).spust()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b>Naskenujte QR kód fotoaparátem telefonu.</b><br>Telefon musí být ve stejné Wi-Fi "
                             "jako počítač. Na telefonu uvidíte seznam chyb a tlačítka Opraveno / Další.<br>"
                             "<span style='color:gray'>Windows se může jednou zeptat na povolení ve firewallu – "
                             "povolte pro soukromé sítě. Spojení běží, jen dokud je toto okno otevřené.</span>"))
        self.qr = QLabel()
        self.qr.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.qr)
        row = QHBoxLayout()
        self.url = QLineEdit(self.server.adresa(mistni_ip()))
        self.url.setReadOnly(True)
        row.addWidget(self.url, 1)
        b = QPushButton("Kopírovat")
        b.clicked.connect(lambda: (self.url.selectAll(), self.url.copy()))
        row.addWidget(b)
        lay.addLayout(row)
        self.stav = QLabel("Čekám na telefon…")
        lay.addWidget(self.stav)
        zav = QPushButton("Ukončit spojení a zavřít")
        zav.clicked.connect(self.close)
        lay.addWidget(zav)
        self._kresli_qr(self.url.text())
        self.obnov()
        for sig in (win.issue_panel.issueSelected, win.issue_panel.stateChanged):
            sig.connect(self.obnov)
        self._t = QTimer(self)
        self._t.timeout.connect(self._stav_spojeni)
        self._t.start(1000)

    def _kresli_qr(self, text: str, modul: int = 7):
        m = qr_matice(text)
        n = len(m)
        img = QImage(n, n, QImage.Format_RGB32)
        cerna, bila = QColor("#000000").rgb(), QColor("#FFFFFF").rgb()
        for y, row in enumerate(m):
            for x, v in enumerate(row):
                img.setPixel(x, y, cerna if v else bila)
        self.qr.setPixmap(QPixmap.fromImage(img.scaled(n * modul, n * modul)))

    def obnov(self, *_a):
        try:
            self.server.aktualizuj(snimek(self.win))
        except Exception:  # noqa: BLE001
            pass

    def _stav_spojeni(self):
        if self.server.posledni_klient:
            self.stav.setText(f"Telefon připojen ({self.server.posledni_klient}).")

    def _akce(self, akce: str, cislo):
        p = self.win.issue_panel
        if akce == "vybrat" and cislo is not None:
            p.select_issue(int(cislo))
        elif akce == "dalsi":
            p.step(1)
        elif akce == "predchozi":
            p.step(-1)
        elif p.current_issue() is not None and akce in ("opraveno", "ignorovat", "vratit"):
            p.set_state({"opraveno": "opraveno", "ignorovat": "ignorovat", "vratit": "nová"}[akce])
        self.obnov()

    def closeEvent(self, e):  # noqa: N802
        self._t.stop()
        self.server.zastav()
        for sig in (self.win.issue_panel.issueSelected, self.win.issue_panel.stateChanged):
            try:
                sig.disconnect(self.obnov)
            except (RuntimeError, TypeError):
                pass
        super().closeEvent(e)
