"""
Download condicional dos arquivos da CVM.

Guarda ETag / Last-Modified em state/http_state.json e manda If-None-Match /
If-Modified-Since nas requisições seguintes. Se a CVM responder 304, reusa o
arquivo em disco — não re-baixa o histórico a cada execução. É isso que torna
a rotina barata de rodar em cron.
"""

from __future__ import annotations

import json
import socket
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import config

STATE = config.STATE_DIR / "http_state.json"
_UA = "cvm-insider-monitor/1.0 (+research)"

# Runners de CI (GitHub Actions) são só IPv4, mas vários endpoints da CVM
# publicam registro AAAA (IPv6) — quando o DNS resolve pro IPv6 a conexão morre
# com "Network is unreachable" (Errno 101), de forma intermitente. Forçamos IPv4.
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_only(host, *args, **kwargs):
    res = _orig_getaddrinfo(host, *args, **kwargs)
    v4 = [ai for ai in res if ai[0] == socket.AF_INET]
    return v4 or res


socket.getaddrinfo = _ipv4_only


def _load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def _save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2))


def download(url: str, dest: Path, timeout: int = 120, retries: int = 3) -> Path:
    """Baixa url->dest com cache condicional. Retorna o caminho local.
    Tenta novamente em falhas transientes de rede (comuns em CI)."""
    state = _load_state()
    meta = state.get(url, {})
    headers = {"User-Agent": _UA}
    if dest.exists() and meta.get("etag"):
        headers["If-None-Match"] = meta["etag"]
    if dest.exists() and meta.get("last_modified"):
        headers["If-Modified-Since"] = meta["last_modified"]

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urlopen(Request(url, headers=headers), timeout=timeout) as r:
                dest.write_bytes(r.read())
                state[url] = {
                    "etag": r.headers.get("ETag"),
                    "last_modified": r.headers.get("Last-Modified"),
                }
                _save_state(state)
                print(f"[fetch] baixado {dest.name} ({dest.stat().st_size//1024} KB)")
            return dest
        except HTTPError as e:
            if e.code == 304 and dest.exists():
                print(f"[fetch] 304 Not Modified — reusando {dest.name}")
                return dest
            raise
        except (URLError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < retries:
                print(f"[fetch] tentativa {attempt}/{retries} falhou ({e}); novo retry…")
                time.sleep(2 * attempt)
    raise last_err  # esgotou as tentativas
