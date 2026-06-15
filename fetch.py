"""
Download condicional dos arquivos da CVM.

Guarda ETag / Last-Modified em state/http_state.json e manda If-None-Match /
If-Modified-Since nas requisições seguintes. Se a CVM responder 304, reusa o
arquivo em disco — não re-baixa o histórico a cada execução. É isso que torna
a rotina barata de rodar em cron.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import config

STATE = config.STATE_DIR / "http_state.json"
_UA = "cvm-insider-monitor/1.0 (+research)"


def _load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def _save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2))


def download(url: str, dest: Path, timeout: int = 120) -> Path:
    """Baixa url->dest com cache condicional. Retorna o caminho local."""
    state = _load_state()
    meta = state.get(url, {})
    headers = {"User-Agent": _UA}
    if dest.exists() and meta.get("etag"):
        headers["If-None-Match"] = meta["etag"]
    if dest.exists() and meta.get("last_modified"):
        headers["If-Modified-Since"] = meta["last_modified"]

    try:
        with urlopen(Request(url, headers=headers), timeout=timeout) as r:
            dest.write_bytes(r.read())
            state[url] = {
                "etag": r.headers.get("ETag"),
                "last_modified": r.headers.get("Last-Modified"),
            }
            _save_state(state)
            print(f"[fetch] baixado {dest.name} ({dest.stat().st_size//1024} KB)")
    except HTTPError as e:
        if e.code == 304 and dest.exists():
            print(f"[fetch] 304 Not Modified — reusando {dest.name}")
        else:
            raise
    return dest
