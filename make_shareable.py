"""
Gera uma versão 100% offline do dashboard: baixa as fontes do Google (woff2,
subsets latin/latin-ext), embute como base64 e troca o <link> externo por um
<style> inline. O arquivo resultante abre em qualquer navegador sem rede.

Uso: python make_shareable.py [caminho_html_entrada] [caminho_saida]
"""
from __future__ import annotations

import base64
import re
import sys
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
KEEP_SUBSETS = {"latin", "latin-ext"}


def _get(url: str, binary: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if binary else data.decode("utf-8")


def inline_fonts(css_url: str) -> str:
    css = _get(css_url)
    # divide em blocos @font-face, cada um precedido por /* subset */
    blocks = re.split(r"(/\*\s*[\w-]+\s*\*/)", css)
    out, label = [], None
    for chunk in blocks:
        m = re.match(r"/\*\s*([\w-]+)\s*\*/", chunk.strip())
        if m:
            label = m.group(1)
            continue
        if "@font-face" not in chunk:
            continue
        if label not in KEEP_SUBSETS:
            continue
        url_m = re.search(r"url\((https://[^)]+\.woff2)\)", chunk)
        if not url_m:
            continue
        b64 = base64.b64encode(_get(url_m.group(1), binary=True)).decode("ascii")
        chunk = chunk.replace(url_m.group(1),
                              f"data:font/woff2;base64,{b64}")
        out.append(chunk.strip())
    return "\n".join(out)


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output/dashboard.html")
    html = src.read_text(encoding="utf-8")

    link_m = re.search(r'<link[^>]+href="(https://fonts\.googleapis\.com/css2[^"]+)"[^>]*>', html)
    if not link_m:
        print("[aviso] não achei o <link> de fontes; saída ficará igual à entrada")
        css_block = ""
    else:
        css = inline_fonts(link_m.group(1))
        css_block = f"<style>\n{css}\n</style>"
        html = html.replace(link_m.group(0), css_block)

    # remove os preconnect (não há mais o que pré-conectar)
    html = re.sub(r'\s*<link rel="preconnect"[^>]*>', "", html)

    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_name("dashboard_offline.html")
    dst.write_text(html, encoding="utf-8")
    print(f"[ok] {dst}  ({round(len(html.encode('utf-8'))/1024)} KB)")


if __name__ == "__main__":
    main()
