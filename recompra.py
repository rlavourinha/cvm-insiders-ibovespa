"""
Histórico de recompra (buyback) a partir dos PDFs do IPE.

O índice IPE entrega apenas o *link* do documento; a quantidade autorizada/
recomprada está no PDF (Fato Relevante / Comunicado / Anexo G da Res. CVM 80).
Este módulo baixa os PDFs (cache em data/pdf/), extrai o texto (cache em
data/pdf_txt/), classifica o tipo de evento e extrai os campos estruturados:

  ticker, cd_cvm, data_entrega, categoria, assunto, tipo, qtd_autorizada,
  pct_float, acoes_circulacao, acoes_tesouraria, prazo_meses, data_aprovacao,
  preco_max, link

Saída: output/recompra.parquet (fallback CSV). Sem nomes de coluna hardcodados
na origem (reusa parse_ipe). Os PDFs são free-text: a extração é por regex
tolerante a acentos; cada linha mantém o link para auditoria humana.
"""
from __future__ import annotations

import concurrent.futures as cf
import io
import re
import socket
import time
import unicodedata
from pathlib import Path

import pandas as pd
from urllib.request import Request, urlopen
from urllib.error import URLError

import config
import parse_ipe
import resolver
from fetch import download as _http_download  # IPv4+retry p/ os zips (single-thread)

_UA = "Mozilla/5.0 (compatible; cvm-insider-monitor/1.0)"

# IPv4 também aqui (alguns ambientes importam recompra sem passar por fetch antes)
_orig_gai = socket.getaddrinfo
socket.getaddrinfo = lambda *a, **k: ([ai for ai in _orig_gai(*a, **k) if ai[0] == socket.AF_INET]
                                      or _orig_gai(*a, **k))

PDF_DIR = config.DATA_DIR / "pdf"
TXT_DIR = config.DATA_DIR / "pdf_txt"
for _d in (PDF_DIR, TXT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# número grande no formato BR (milhar com ponto) ou inteiro com 4+ dígitos
_NUM = r"\d{1,3}(?:\.\d{3})+|\d{4,}"
# quantidade: aceita também "5 milhões", "1,5 milhão", "500 mil", "10 milhões"
# (a CVM mistura dígito+palavra-escala com o formato com pontos de milhar).
_SCALE = r"(?:bilhoes|bilhao|milhoes|milhao|mil)"
_QTY = r"\d{1,3}(?:\.\d{3})+|\d+(?:,\d+)?\s*" + _SCALE + r"|\d{4,}"
_SCALE_MULT = {"mil": 1e3, "milhao": 1e6, "milhoes": 1e6, "bilhao": 1e9, "bilhoes": 1e9}


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode()


def _to_int(s) -> int | None:
    d = re.sub(r"\D", "", str(s))
    return int(d) if d else None


def _to_qty(s) -> int | None:
    """Converte '5 milhões'/'1,5 milhão'/'500 mil' ou '5.000.000' em inteiro."""
    s = str(s).strip().lower()
    m = re.match(r"([\d.,]+)\s*(" + _SCALE + r")", s)
    if m:
        base = float(m.group(1).replace(".", "").replace(",", "."))
        return int(round(base * _SCALE_MULT[m.group(2)]))
    return _to_int(s)


def _protocolo(link: str) -> str:
    m = re.search(r"numProtocolo=(\d+).*?numSequencia=(\d+).*?numVersao=(\d+)", link)
    return "_".join(m.groups()) if m else re.sub(r"\W+", "_", link)[-40:]


# ---------------------------------------------------------------------------
# download + extração de texto (com cache em disco)
# ---------------------------------------------------------------------------
def _fetch_pdf(link: str) -> Path | None:
    # download direto (sem o http_state.json compartilhado do fetch.py — este é
    # chamado de várias threads e a corrida corromperia o JSON de estado).
    pid = _protocolo(link)
    dest = PDF_DIR / f"{pid}.pdf"
    if dest.exists() and dest.stat().st_size > 0 and dest.read_bytes()[:5] == b"%PDF-":
        return dest
    for attempt in range(1, 5):
        try:
            with urlopen(Request(link, headers={"User-Agent": _UA}), timeout=90) as r:
                data = r.read()
            if data[:5] == b"%PDF-":
                dest.write_bytes(data)
                return dest
            return None  # não é PDF (página de erro/HTML)
        except (URLError, TimeoutError, OSError):
            time.sleep(min(20, 3 * attempt))
    print(f"[recompra] falha download {pid}")
    return None


def _text_of(link: str) -> str:
    pid = _protocolo(link)
    cache = TXT_DIR / f"{pid}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    pdf = _fetch_pdf(link)
    if pdf is None:
        return ""
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf)) as doc:
            txt = "\n".join((p.extract_text() or "") for p in doc.pages)
    except Exception as e:
        print(f"[recompra] falha extrair {pid}: {type(e).__name__}")
        txt = ""
    cache.write_text(txt, encoding="utf-8")
    return txt


# ---------------------------------------------------------------------------
# classificação + extração de campos
# ---------------------------------------------------------------------------
def _classify(assunto: str, text: str) -> str:
    a = _norm(assunto).lower()
    t = _norm(text).lower()[:1500]
    blob = a + " " + t
    if re.search(r"debenture", blob):
        return "debenture"          # recompra de dívida, não de ações — fora do escopo
    if re.search(r"oferta publica de aquisicao|\bopa\b|tender offer", blob):
        return "opa"                # OPA por terceiro/controle — não é recompra da própria cia
    if re.search(r"encerr", blob):
        return "encerramento"
    if re.search(r"cancelamento de acoes", blob):
        return "cancelamento"
    if re.search(r"negociacao de acoes de propria emissao|efetivad|recompradas\s+\d|saldo do programa", blob):
        return "execucao"
    if re.search(r"aliena[çc]?\w*\s+de\s+acoes.*tesouraria|alienacao de acoes em tesouraria", blob):
        return "alienacao"
    if re.search(r"programa de recompra|recompra de acoes|aquisicao de acoes", blob):
        return "aprovacao"
    return "outro"


def _extract_fields(text: str) -> dict:
    t = _norm(text)
    tl = re.sub(r"\s+", " ", t).lower()
    out = {k: None for k in ("qtd_autorizada", "valor_autorizado", "pct_float", "acoes_circulacao",
                             "acoes_tesouraria", "prazo_meses", "data_aprovacao", "preco_max")}

    # quantidade máxima autorizada: "até X (...) ações" perto de recompr/adquir/aquisic/máximo
    for m in re.finditer(r"(?:ate|de)\s+(" + _QTY + r")\s*(?:\([^)]*\)\s*)?(?:de\s+)?ac[oa]es", tl):
        ctx = tl[max(0, m.start() - 130):m.start()]
        if re.search(r"recompr|adquir|aquisic|maxim|poderao ser|serao adquirid", ctx):
            out["qtd_autorizada"] = _to_qty(m.group(1))
            break

    # alguns programas limitam por VALOR (R$), não por nº de ações (ex.: "até R$ 100.000.000")
    for m in re.finditer(r"ate\s+r\$?\s*(" + _NUM + r"(?:,\d{2})?)", tl):
        ctx = tl[max(0, m.start() - 130):m.start()]
        if re.search(r"recompr|adquir|aquisic|maxim|programa", ctx):
            out["valor_autorizado"] = _money(m.group(1))
            break

    # % do free float
    m = re.search(r"representativ\w*\s+de\s+(?:ate\s+)?([\d.,]+)\s*%", tl)
    if m:
        out["pct_float"] = float(m.group(1).replace(".", "").replace(",", "."))

    # ações em circulação
    m = re.search(r"(" + _NUM + r")\s*(?:\([^)]*\)\s*)?acoes\s+em\s+circulacao", tl)
    if m:
        out["acoes_circulacao"] = _to_int(m.group(1))

    # ações em tesouraria (quando informado)
    m = re.search(r"(" + _NUM + r")\s*(?:\([^)]*\)\s*)?acoes\s+(?:mantidas\s+)?em\s+tesouraria", tl)
    if m:
        out["acoes_tesouraria"] = _to_int(m.group(1))
    elif re.search(r"nao possui acoes em tesouraria", tl):
        out["acoes_tesouraria"] = 0

    # prazo em meses
    m = re.search(r"(\d{1,2})\s*\(?[a-z ]*\)?\s*meses", tl)
    if m:
        out["prazo_meses"] = int(m.group(1))

    # data de aprovação (reunião do conselho)
    m = re.search(r"realizad\w*\s+em\s+(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})", tl)
    if m:
        out["data_aprovacao"] = _parse_data_br(m.group(1), m.group(2), m.group(3))

    # preço máximo (quando há limite explícito)
    m = re.search(r"pre[çc]?o\s+(?:maximo|unitario maximo)[^\d]{0,40}r?\$?\s*([\d.,]+)", tl)
    if m:
        out["preco_max"] = _money(m.group(1))

    # % do programa: se não foi declarado explicitamente ("representativas de
    # X%"), calcula a partir de qtd/free float. Empresas como a CURY autorizam
    # um nº absoluto e só citam o TETO legal de 10% da RCVM 77 — o % real do
    # programa é qtd/circulação (ex.: 11.720.002/137.108.025 = 8,55%), não o teto.
    if out["pct_float"] is None and out["qtd_autorizada"] and out["acoes_circulacao"]:
        out["pct_float"] = round(out["qtd_autorizada"] / out["acoes_circulacao"] * 100, 2)
    return out


def _extract_executed(text: str) -> dict:
    """Quantidade EFETIVAMENTE recomprada — disclosada nos comunicados de
    encerramento/conclusão de programa ('tendo sido adquiridas X ações...').
    Só dispara em linguagem realizada (passado), nunca em autorização ('até X')."""
    tl = re.sub(r"\s+", " ", _norm(text)).lower()
    out = {k: None for k in ("qtd_executada", "qtd_executada_pn", "preco_medio_exec",
                             "valor_executado", "pct_capital_exec")}
    realized = re.search(r"foram adquirid|sido adquirid|concluiu o programa|encerr\w+ d\w+ programa"
                         r"|no ambito d\w+ programa[^.]{0,90}adquirid|adquiriu", tl)
    if not realized:
        return out

    m = re.search(r"adquirid\w+\s+(?:na b3[^,]*,?\s*)?(?:a precos? de mercado,?\s*)?("
                  + _QTY + r")\s*(?:\([^)]*\)\s*)?(?:de\s+)?ac[oa]es", tl)
    if m:
        out["qtd_executada"] = _to_qty(m.group(1))
        tail = tl[m.end() - 1:m.end() + 90]
        mp = re.search(r"e\s+(" + _QTY + r")\s*(?:\([^)]*\)\s*)?ac[oa]es\s*pn", tail)
        if mp:
            out["qtd_executada_pn"] = _to_qty(mp.group(1))
        mc = re.search(r"equivalentes?\s+a\s+([\d,]+)\s*%\s+do\s+capital", tl)
        if mc:
            out["pct_capital_exec"] = float(mc.group(1).replace(".", "").replace(",", "."))
    elif re.search(r"nao (?:foram|houve|adquiriu|realizou|ocorreu)[^.]{0,45}(adquir|negocia|aquisi|recompr)", tl):
        out["qtd_executada"] = 0

    m = re.search(r"preco medio (?:ponderado )?(?:de )?(?:aquisicao )?(?:de )?r?\$?\s*([\d.,]+)", tl)
    if m:
        out["preco_medio_exec"] = _money(m.group(1))
    m = re.search(r"totalizando[^.]{0,35}r\$\s*([\d.,]+)", tl)
    if m:
        out["valor_executado"] = _money(m.group(1))
    return out


_MESES = {m: i + 1 for i, m in enumerate(
    ["janeiro", "fevereiro", "marco", "abril", "maio", "junho",
     "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"])}


def _parse_data_br(d, mes, y) -> str | None:
    mi = _MESES.get(_norm(mes).lower())
    return f"{int(y):04d}-{mi:02d}-{int(d):02d}" if mi else None


def _money(s: str) -> float | None:
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------
def _ipe_recompra(years) -> pd.DataFrame:
    mp = resolver.resolve()
    keep = resolver.cd_cvm_set(mp)
    cd2tk = resolver.cd_to_tickers(mp)
    frames = []
    for ano in years:
        zc = config.DATA_DIR / f"ipe_{ano}.zip"
        if not zc.exists():
            try:
                _http_download(config.IPE_URL.format(ano=ano), zc, timeout=90, retries=4)
            except Exception as e:
                print(f"[recompra] IPE {ano} indisponível: {type(e).__name__}")
                continue
        df = parse_ipe.parse(zc, keep)
        if not df.empty:
            df["ano"] = ano
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    ipe = pd.concat(frames, ignore_index=True)
    ipe["ticker"] = ipe["cd_cvm"].map(lambda c: cd2tk.get(int(c), ["—"])[0] if pd.notna(c) else "—")
    return ipe


def build_ledger(years=None, max_workers=8) -> pd.DataFrame:
    years = years or config.ANOS
    ipe = _ipe_recompra(years)
    if ipe.empty:
        return pd.DataFrame()
    links = ipe["link"].fillna("").tolist()
    texts = {}
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        fut = {ex.submit(_text_of, l): l for l in links if l}
        for f in cf.as_completed(fut):
            texts[fut[f]] = f.result()

    rows = []
    for _, r in ipe.iterrows():
        link = r.get("link") or ""
        txt = texts.get(link, "")
        tipo = _classify(r.get("assunto", ""), txt)
        if tipo in ("debenture",):
            continue
        fields = _extract_fields(txt) if txt else {}
        executed = _extract_executed(txt) if txt else {}
        rows.append(dict(
            ticker=r.get("ticker"), cd_cvm=r.get("cd_cvm"), ano=r.get("ano"),
            data_entrega=r.get("data_entrega"), data_ref=r.get("data_ref"),
            categoria=r.get("categoria"), assunto=r.get("assunto"),
            tipo=tipo, link=link, chars=len(txt), **fields, **executed,
        ))
    led = pd.DataFrame(rows)
    _write(led)
    return led


def _write(df: pd.DataFrame) -> str:
    pq = config.OUTPUT_DIR / "recompra.parquet"
    try:
        df.to_parquet(pq, index=False)
        return str(pq)
    except Exception:
        cv = config.OUTPUT_DIR / "recompra.csv"
        df.to_csv(cv, index=False, encoding="utf-8")
        return str(cv)


# snapshot versionado no repo (não re-baixa centenas de PDFs a cada build do CI)
HISTORY_FILE = config.BASE_DIR / "recompra_history.parquet"


def load() -> pd.DataFrame:
    """Carrega o histórico de recompra versionado (gerado por build_ledger e
    commitado). Vazio se ausente — o dashboard degrada sem quebrar."""
    for p in (HISTORY_FILE, HISTORY_FILE.with_suffix(".csv")):
        if p.exists():
            try:
                return pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
            except Exception:
                pass
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# visualização (aba "Recompras" do dashboard)
# ---------------------------------------------------------------------------
def fragment(led: pd.DataFrame, meta: dict) -> dict:
    import report  # formatadores compartilhados (1,000.00)
    if led is None or led.empty:
        return {"body": '<div class="empty">Sem histórico de recompra disponível.</div>', "n": 0}
    led = led.copy()
    led["_d"] = led.get("data_aprovacao")
    led["_d"] = led["_d"].fillna(led.get("data_entrega"))
    led["_d"] = led["_d"].fillna("").astype(str)

    ap = led[led["tipo"] == "aprovacao"].copy()
    # de-dup: o mesmo programa costuma ser arquivado em 2-3 categorias (Reunião +
    # Fato Relevante + Comunicado). Junta por (papel, tamanho, mês). Chave
    # construída linha-a-linha — a concatenação vetorizada com StringDtype/NaN
    # propagaria NA e colapsaria tudo.
    ap["_k"] = ap.apply(lambda r: f'{r["ticker"]}|{r.get("qtd_autorizada")}|'
                                  f'{r.get("valor_autorizado")}|{str(r["_d"])[:7]}', axis=1)
    ap = ap.sort_values("_d").drop_duplicates("_k", keep="first")

    enc = led[led["tipo"].isin(["encerramento", "cancelamento"])].copy()
    n_prog = len(ap)
    total_acoes = ap["qtd_autorizada"].fillna(0).sum()
    n_emp = ap["ticker"].nunique()

    # execução: quantidade efetivamente recomprada (dos comunicados de conclusão)
    ex = pd.DataFrame()
    if "qtd_executada" in led:
        ex = led[led["qtd_executada"].notna() & (led["qtd_executada"] > 0)].copy()
        ex["_ke"] = ex.apply(lambda r: f'{r["ticker"]}|{r.get("qtd_executada")}|{str(r["_d"])[:7]}', axis=1)
        ex = ex.sort_values("_d").drop_duplicates("_ke", keep="last")
    total_exec = ex["qtd_executada"].fillna(0).sum() if not ex.empty else 0

    exec_items = []
    for _, r in ex.sort_values("qtd_executada", ascending=False).iterrows():
        pm, val = r.get("preco_medio_exec"), r.get("valor_executado")
        if pd.isna(val) and pd.notna(pm):
            val = r["qtd_executada"] * pm
        head = (f'{report._qtd(r["qtd_executada"])} ON + {report._qtd(r["qtd_executada_pn"])} PN'
                if pd.notna(r.get("qtd_executada_pn")) else f'{report._qtd(r["qtd_executada"])} ações')
        parts = [head]
        if pd.notna(pm):
            parts.append(f'R$ {pm:,.2f} méd')
        if pd.notna(val):
            parts.append(report._brl(val))
        link = r.get("link") or ""
        doc = f' <a href="{link}" target="_blank" rel="noopener">doc ↗</a>' if link else ""
        exec_items.append(
            f'<div class="tes-item"><div class="tes-head"><span class="tkr">{r.get("ticker","—")}</span>'
            f'<span class="tag gold">executado</span></div>'
            f'<div class="tes-body">{" · ".join(parts)}</div>'
            f'<div class="tes-meta">{report._short(str(r["_d"]),10)}{doc}</div></div>')
    exec_items = exec_items or ['<div class="empty">Sem recompras concluídas com quantidade disponível.</div>']

    def _aut(r):
        if pd.notna(r.get("qtd_autorizada")):
            return f'{report._qtd(r["qtd_autorizada"])} <span class="t-unit">ações</span>'
        if pd.notna(r.get("valor_autorizado")):
            return report._brl(r["valor_autorizado"])
        return "—"

    rows = []
    for _, r in ap.sort_values("_d", ascending=False).iterrows():
        pct = f'{r["pct_float"]:.2f}%' if pd.notna(r.get("pct_float")) else "—"
        prazo = f'{int(r["prazo_meses"])}m' if pd.notna(r.get("prazo_meses")) else "—"
        link = r.get("link") or ""
        doc = f'<a href="{link}" target="_blank" rel="noopener">↗</a>' if link else "—"
        rows.append(
            f'<div class="rec-row"><span class="t-tkr">{r.get("ticker","—")}</span>'
            f'<span class="t-num">{report._short(r["_d"],10)}</span>'
            f'<span class="t-num strong">{_aut(r)}</span>'
            f'<span class="t-num">{pct}</span>'
            f'<span class="t-days">{prazo}</span>'
            f'<span class="t-days">{doc}</span></div>')
    rows = rows or ['<div class="empty">Sem programas aprovados.</div>']

    enc_items = []
    for _, r in enc.sort_values("_d", ascending=False).iterrows():
        tag = "encerramento" if r["tipo"] == "encerramento" else "cancelamento"
        enc_items.append(
            f'<div class="tes-item"><div class="tes-head"><span class="tkr">{r.get("ticker","—")}</span>'
            f'<span class="tag">{tag}</span></div>'
            f'<div class="tes-body">{report._short(r.get("assunto") or "—",70)}</div>'
            f'<div class="tes-meta">{report._short(r["_d"],10)}</div></div>')
    enc_items = enc_items or ['<div class="empty">Sem encerramentos/cancelamentos.</div>']

    anos = f'{int(led["ano"].min())}–{int(led["ano"].max())}' if "ano" in led else "—"
    body = f"""
  <div class="month-bar">
    <span>Histórico de programas de recompra — <b>{anos}</b></span>
    <span>Fonte: <b>comunicados IPE</b> (PDF) da CVM</span>
    <span><b>Autorizado</b> = limite do programa · <b>Executado</b> = efetivamente recomprado (programas concluídos)</span>
  </div>
  <section class="kpis c4">
    <div class="kpi"><div class="lbl">Programas aprovados</div><div class="val">{n_prog}</div><div class="foot">no período</div></div>
    <div class="kpi"><div class="lbl">Ações autorizadas</div><div class="val">{report._qtd(total_acoes)}</div><div class="foot">soma dos limites</div></div>
    <div class="kpi"><div class="lbl">Ações recompradas</div><div class="val gold">{report._qtd(total_exec)}</div><div class="foot">executado · prog. concluídos</div></div>
    <div class="kpi"><div class="lbl">Empresas com programa</div><div class="val">{n_emp}</div><div class="foot">do Ibovespa</div></div>
  </section>
  <div class="grid">
    <section class="card">
      <div class="card-h"><h2>Programas de recompra aprovados</h2><span class="meta">por data · {n_prog}</span></div>
      <div class="rec-head"><span>Papel</span><span>Aprovação</span><span style="text-align:right">Autorizado</span>
        <span style="text-align:right">% float</span><span style="text-align:center">Prazo</span><span style="text-align:center">Doc</span></div>
      <div class="tape">{''.join(rows)}</div>
    </section>
    <div class="right">
      <section class="card"><div class="card-h"><h2>Recompras concluídas</h2><span class="meta">executado · {len(ex)}</span></div>
        <div class="tes-list">{''.join(exec_items)}</div></section>
      <section class="card"><div class="card-h"><h2>Encerramentos &amp; cancelamentos</h2><span class="meta">{len(enc)}</span></div>
        <div class="tes-list">{''.join(enc_items)}</div></section>
    </div>
  </div>"""
    return {"body": body, "n": n_prog}


if __name__ == "__main__":
    import sys
    yrs = [int(a) for a in sys.argv[1:] if a.isdigit()] or config.ANOS
    led = build_ledger(yrs)
    print(f"[recompra] {len(led)} eventos de recompra · {led['ticker'].nunique()} empresas")
    print(led.groupby("tipo").size().to_dict())
    ap = led[led["tipo"] == "aprovacao"]
    print(f"aprovações com qtd extraída: {ap['qtd_autorizada'].notna().sum()}/{len(ap)}")
