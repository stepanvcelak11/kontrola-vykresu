"""Mobil jako druhá obrazovka: malý webový server v místní síti (Wi-Fi).

Telefon načte QR kód a v prohlížeči uvidí seznam chyb, aktuální chybu s návodem a tlačítka
Opraveno / Předchozí / Další / Ignorovat. Akce se posílají zpět do aplikace na PC.

Bezpečnost: server běží jen po dobu, kdy je otevřené okno „Mobil“, a každý požadavek musí nést náhodný
klíč z QR kódu (bez něj odpoví 403). Data se neposílají nikam mimo místní síť.

Server nesahá na Qt: hlavní okno mu předává hotový snímek stavu (``aktualizuj``) a akce z telefonu
předává funkcí ``na_akci`` (volá se z vlákna serveru – příjemce si je musí přehodit do hlavního vlákna).
"""

from __future__ import annotations

import json
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlparse

AKCE = {"opraveno", "dalsi", "predchozi", "ignorovat", "vratit", "vybrat"}


def mistni_ip() -> str:
    """IP adresa počítače v místní síti (bez odesílání dat – UDP socket se jen „namíří“)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


class MobilServer:
    def __init__(self, na_akci: Callable[[str, int | None], None], port: int = 0, host: str = "0.0.0.0"):
        self.na_akci = na_akci
        self.klic = secrets.token_urlsafe(12)
        self._stav: dict = {"vykres": "", "chyby": [], "aktualni": None, "verze": 0}
        self._zamek = threading.Lock()
        self.pristupy = 0
        self.posledni_klient: str | None = None
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # bez výpisů do konzole
                pass

            def _klic_ok(self) -> bool:
                q = parse_qs(urlparse(self.path).query)
                return secrets.compare_digest((q.get("t") or [""])[0], server.klic)

            def _posli(self, kod: int, telo: bytes, typ: str):
                self.send_response(kod)
                self.send_header("Content-Type", typ)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(telo)))
                self.end_headers()
                self.wfile.write(telo)

            def do_GET(self):  # noqa: N802
                if not self._klic_ok():
                    self._posli(403, "Neplatný odkaz – naskenujte QR kód v aplikaci znovu.".encode(), "text/plain; "
                                "charset=utf-8")
                    return
                server.pristupy += 1
                server.posledni_klient = self.client_address[0]
                cesta = urlparse(self.path).path
                if cesta == "/":
                    self._posli(200, STRANKA.encode("utf-8"), "text/html; charset=utf-8")
                elif cesta == "/api/stav":
                    with server._zamek:
                        telo = json.dumps(server._stav, ensure_ascii=False).encode("utf-8")
                    self._posli(200, telo, "application/json; charset=utf-8")
                else:
                    self._posli(404, b"", "text/plain")

            def do_POST(self):  # noqa: N802
                if not self._klic_ok():
                    self._posli(403, b"", "text/plain")
                    return
                try:
                    n = min(int(self.headers.get("Content-Length") or 0), 10000)
                    data = json.loads(self.rfile.read(n) or b"{}")
                    akce = str(data.get("akce", ""))
                    cislo = data.get("cislo")
                    cislo = int(cislo) if cislo is not None else None
                except (ValueError, TypeError):
                    self._posli(400, b"", "text/plain")
                    return
                if urlparse(self.path).path != "/api/akce" or akce not in AKCE:
                    self._posli(400, b"", "text/plain")
                    return
                server.posledni_klient = self.client_address[0]
                try:
                    server.na_akci(akce, cislo)
                except Exception:  # noqa: BLE001 – chyba příjemce nesmí shodit server
                    pass
                self._posli(200, b'{"ok":true}', "application/json")

        self._httpd = ThreadingHTTPServer((host, port), Handler)
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self._vlakno = threading.Thread(target=self._httpd.serve_forever, name="mobil-server", daemon=True)

    def spust(self):
        self._vlakno.start()
        return self

    def zastav(self):
        try:
            self._httpd.shutdown()
            self._httpd.server_close()
        except Exception:  # noqa: BLE001
            pass

    def adresa(self, ip: str | None = None) -> str:
        return f"http://{ip or mistni_ip()}:{self.port}/?t={self.klic}"

    def aktualizuj(self, stav: dict):
        with self._zamek:
            stav = dict(stav)
            stav["verze"] = self._stav.get("verze", 0) + 1
            self._stav = stav


def qr_matice(text: str) -> list[list[bool]]:
    """Matice QR kódu (knihovna qrcode, BSD)."""
    import qrcode
    q = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(text)
    q.make(fit=True)
    return q.get_matrix()


STRANKA = r"""<!doctype html><html lang="cs"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kontrola výkresu – mobil</title>
<style>
:root{--bg:#111318;--panel:#1c1f26;--text:#e5e7eb;--muted:#9ca3af;--chyba:#f87171;--var:#fbbf24;--info:#60a5fa;--ok:#22c55e;--acc:#3b82f6}
@media (prefers-color-scheme: light){:root{--bg:#f3f4f6;--panel:#fff;--text:#111827;--muted:#6b7280;--chyba:#dc2626;--var:#d97706;--info:#2563eb;--ok:#16a34a;--acc:#2563eb}}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--text)}
header{padding:12px 16px;position:sticky;top:0;background:var(--bg);z-index:2}
h1{font-size:16px;margin:0}#souhrn{color:var(--muted);font-size:13px;margin-top:2px}
#karta{margin:0 12px 12px;padding:14px;border-radius:14px;background:var(--panel)}
.sev{font-weight:800;font-size:13px}.sev.chyba{color:var(--chyba)}.sev.varování{color:var(--var)}.sev.info{color:var(--info)}
#zprava{font-size:17px;font-weight:600;margin:6px 0}#misto{color:var(--muted);font-size:13px}
#postup{margin:10px 0 0;padding-left:20px;font-size:14px;line-height:1.45}
.tl{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px}
button{font:inherit;font-size:16px;padding:14px;border-radius:12px;border:0;background:var(--panel);color:var(--text)}
button.ok{background:var(--ok);color:#fff;font-weight:700;grid-column:span 2}button:active{opacity:.7}
ul{list-style:none;margin:0 12px 24px;padding:0}li{padding:10px 12px;border-radius:10px;background:var(--panel);margin-bottom:6px;font-size:14px}
li.akt{outline:2px solid var(--acc)}li.hotovo{opacity:.45;text-decoration:line-through}
#chyba{color:var(--chyba);padding:0 16px;font-size:13px}
</style></head><body>
<header><h1 id="vykres">Kontrola výkresu</h1><div id="souhrn">Načítám…</div></header>
<div id="chyba"></div>
<section id="karta"><div class="sev" id="sev"></div><div id="zprava">Vyberte chybu</div><div id="misto"></div><ol id="postup"></ol></section>
<div class="tl"><button class="ok" onclick="akce('opraveno')">✓ Opraveno</button>
<button onclick="akce('predchozi')">◀ Předchozí</button><button onclick="akce('dalsi')">Další ▶</button>
<button onclick="akce('ignorovat')">Ignorovat</button><button onclick="akce('vratit')">Vrátit k opravě</button></div>
<ul id="seznam"></ul>
<script>
const T=new URLSearchParams(location.search).get('t');let verze=-1;
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
async function nacti(){try{const r=await fetch('/api/stav?t='+encodeURIComponent(T),{cache:'no-store'});
if(!r.ok){document.getElementById('chyba').textContent='Spojení odmítnuto – naskenujte QR kód znovu.';return}
const s=await r.json();document.getElementById('chyba').textContent='';if(s.verze===verze)return;verze=s.verze;vykresli(s)}
catch(e){document.getElementById('chyba').textContent='Počítač není dostupný – je okno Mobil v aplikaci otevřené a jste ve stejné Wi-Fi?'}}
function vykresli(s){document.getElementById('vykres').textContent=s.vykres||'Kontrola výkresu';
document.getElementById('souhrn').textContent=s.souhrn||'';const a=s.aktualni;
document.getElementById('sev').className='sev '+(a?a.zavaznost:'');
document.getElementById('sev').textContent=a?('#'+a.cislo+' '+a.zavaznost+' · '+a.kontrola):'';
document.getElementById('zprava').textContent=a?a.zprava:'Vyberte chybu v seznamu';
document.getElementById('misto').textContent=a?('vrstva '+(a.vrstva||'–')+' · Y '+a.y+'  X '+a.x+(a.stav!=='nová'?' · '+a.stav:'')):'';
document.getElementById('postup').innerHTML=a&&a.postup?a.postup.map(p=>'<li>'+esc(p)+'</li>').join(''):'';
document.getElementById('seznam').innerHTML=(s.chyby||[]).map(c=>'<li class="'+(a&&c.cislo===a.cislo?'akt ':'')+(c.stav!=='nová'?'hotovo':'')+
'" onclick="akce(\'vybrat\','+c.cislo+')"><span class="sev '+esc(c.zavaznost)+'">#'+c.cislo+'</span> '+esc(c.zprava)+'</li>').join('')}
async function akce(a,c){try{await fetch('/api/akce?t='+encodeURIComponent(T),{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({akce:a,cislo:c??null})});if(navigator.vibrate)navigator.vibrate(15);setTimeout(nacti,150)}catch(e){}}
nacti();setInterval(nacti,1500);
</script></body></html>"""
