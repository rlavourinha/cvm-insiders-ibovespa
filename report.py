"""
Digest visual (fita de insiders + tesouraria).

Expõe:
  digest_fragment(vlmo, ipe, meta) -> {'body': html, 'chart_data': dict}
  digest_script(chart_data) -> <script> (IIFE isolado) com o gráfico de fluxo
  build_html(vlmo, ipe, meta) -> página standalone completa

A mesma função alimenta o dashboard combinado, evitando divergência de layout.
"""

from __future__ import annotations

import html
import json
import math
import pandas as pd

import theme


# ---------------------------------------------------------------------------
def _brl(v, signed=False) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    a = abs(v)
    if a >= 1e9: s = f"R$ {v/1e9:,.2f} bi"
    elif a >= 1e6: s = f"R$ {v/1e6:,.2f} mi"
    elif a >= 1e3: s = f"R$ {v/1e3:,.0f} mil"
    else: s = f"R$ {v:,.0f}"
    s = s.replace(",", "·").replace(".", ",").replace("·", ".")
    return ("+" + s) if (signed and v > 0) else s


def _qtd(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{abs(v):,.0f}".replace(",", ".")


def _preco(v) -> str:
    # preço médio sempre com 2 casas decimais (ex.: R$ 10,69 / R$ 1.384,32)
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"R$ {v:,.2f}".replace(",", "·").replace(".", ",").replace("·", ".")


def _org_label(o) -> str:
    # rótulo limpo do comprador (órgão); a CVM sufixa "ou Vinculado"
    s = str(o or "").strip()
    if not s or s.lower() == "nan":
        return "—"
    return s.replace(" ou Vinculado", "").replace(" ou vinculado", "").strip() or "—"


def _short(s, n=26) -> str:
    s = str(s or "")
    return s if len(s) <= n else s[: n - 1] + "…"


# JS do filtro por comprador (string normal, não f-string, p/ não escapar { }).
_FILTER_JS = """
<script>(()=>{
  const sel=document.getElementById('org-filter');
  const cnt=document.getElementById('tape-count');
  const rows=[...document.querySelectorAll('.tape .tape-row')];
  const total=rows.length;
  function apply(){
    const v=sel?sel.value:''; let shown=0;
    rows.forEach(r=>{const ok=!v||r.dataset.org===v; r.style.display=ok?'':'none'; if(ok)shown++;});
    if(cnt)cnt.textContent = v ? (shown+' de '+total) : (total+' movimentações');
  }
  if(sel)sel.addEventListener('change',apply);
  apply();
})();</script>"""


# ---------------------------------------------------------------------------
def _flow_svg(cd: dict) -> str:
    labels = list(reversed(cd["labels"])); values = list(reversed(cd["values"]))
    n = len(labels)
    if n == 0:
        return '<div class="empty">Sem fluxo de insiders no delta.</div>'
    rowH, padT, padB, W = 22, 10, 24, 360
    labelW, rightPad = 50, 10
    x0 = labelW; plotW = W - labelW - rightPad; cx = x0 + plotW / 2
    H = padT + padB + n * rowH
    maxabs = max((abs(v) for v in values), default=1) or 1
    scale = (plotW / 2 - 28) / maxabs
    p = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Fluxo líquido por emissor">']
    p.append(f'<line class="svg-zero" x1="{cx:.1f}" y1="{padT-2}" x2="{cx:.1f}" y2="{H-padB+2}"/>')
    for i, (lb, v) in enumerate(zip(labels, values)):
        yc = padT + i * rowH + rowH / 2
        bl = v * scale; x = cx if bl >= 0 else cx + bl; bh = rowH - 9
        color = "var(--buy)" if v >= 0 else "var(--sell)"
        p.append(f'<rect x="{x:.1f}" y="{yc-bh/2:.1f}" width="{max(abs(bl),0.5):.1f}" height="{bh}" rx="2" fill="{color}"/>')
        p.append(f'<text class="svg-tkr" x="2" y="{yc+3.5:.1f}">{lb}</text>')
        vx = cx + bl + (4 if v >= 0 else -4); anch = "start" if v >= 0 else "end"
        p.append(f'<text class="svg-val" x="{vx:.1f}" y="{yc+3.5:.1f}" text-anchor="{anch}">{("+" if v>0 else "")}{v:.1f}</text>')
    p.append(f'<text class="svg-axis" x="{x0}" y="{H-7}">vendas (−)</text>')
    p.append(f'<text class="svg-axis" x="{W-rightPad}" y="{H-7}" text-anchor="end">compras (+) · R$ mi</text>')
    p.append("</svg>")
    return "".join(p)


def digest_fragment(vlmo: pd.DataFrame, ipe: pd.DataFrame, meta: dict) -> dict:
    vlmo = vlmo.copy() if vlmo is not None else pd.DataFrame()
    ipe = ipe.copy() if ipe is not None else pd.DataFrame()
    insider = vlmo[vlmo.get("classe", "insider") == "insider"] if not vlmo.empty else vlmo
    tesour = vlmo[vlmo.get("classe") == "tesouraria"] if not vlmo.empty else pd.DataFrame()

    def signed_vol(df):
        if df.empty or "volume" not in df: return pd.Series(dtype=float)
        sign = df["direcao"].map({"compra": 1, "venda": -1}).fillna(0)
        return df["volume"].fillna(0) * sign

    isv = signed_vol(insider)
    fluxo = float(isv.sum()) if len(isv) else 0.0
    n_eventos = len(vlmo) + len(ipe)
    by_tk = pd.Series(dtype=float)
    if len(isv):
        by_tk = insider.assign(_sv=isv.values).groupby("ticker")["_sv"].sum().sort_values()
    n_compra = int((by_tk > 0).sum())
    n_recompra = len(ipe) + len(tesour)

    # fita
    rows = []
    src = insider.sort_values("volume", ascending=False, na_position="last") if not insider.empty else insider
    for _, r in src.iterrows():
        d = r.get("direcao", "compra")
        org = _org_label(r.get("orgao"))
        rows.append(f"""<div class="tape-row {d}" data-org="{html.escape(org, quote=True)}">
          <span class="t-date">{_short(r.get('data_ref','—'),10)}</span>
          <span class="t-tkr">{r.get('ticker','—')}</span>
          <span class="t-org">{_short(org,24)}</span>
          <span class="t-chip {d}">{'COMPRA' if d=='compra' else 'VENDA'}</span>
          <span class="t-num">{_qtd(r.get('quantidade'))}</span>
          <span class="t-num">{_preco(r.get('preco'))}</span>
          <span class="t-num strong">{_brl(r.get('volume'))}</span></div>""")
    if not rows:
        rows.append('<div class="empty">Nenhuma movimentação de insider no delta desta execução.</div>')

    # opções do filtro por comprador (órgão), derivadas dos dados presentes
    orgaos = sorted({_org_label(o) for o in insider["orgao"].dropna()}) if (not insider.empty and "orgao" in insider) else []
    org_opts = '<option value="">Todos os compradores</option>' + "".join(
        f'<option value="{html.escape(o, quote=True)}">{html.escape(o)}</option>' for o in orgaos)

    # tesouraria/recompra
    tes = []
    for _, r in tesour.iterrows():
        tes.append(f"""<div class="tes-item">
          <div class="tes-head"><span class="tkr">{r.get('ticker','—')}</span><span class="tag">VLMO · tesouraria</span></div>
          <div class="tes-body">{r.get('direcao','—')} · {_qtd(r.get('quantidade'))} ações · {_brl(r.get('volume'))}</div></div>""")
    for _, r in ipe.iterrows():
        link = r.get("link")
        href = f'<a href="{link}" target="_blank" rel="noopener">abrir documento ↗</a>' if pd.notna(link) and link else ""
        tes.append(f"""<div class="tes-item">
          <div class="tes-head"><span class="tkr">{r.get('ticker','—')}</span><span class="tag gold">IPE · recompra</span></div>
          <div class="tes-body">{_short(r.get('assunto') or r.get('categoria') or 'Comunicado de recompra',80)}</div>
          <div class="tes-meta">{_short(r.get('data_entrega','—'),10)} {href}</div></div>""")
    if not tes:
        tes.append('<div class="empty">Sem sinais de tesouraria/recompra no delta.</div>')

    chart = by_tk.tail(14)
    chart = chart.reindex(chart.abs().sort_values().index)
    chart_data = {"labels": list(chart.index), "values": [round(v/1e6, 3) for v in chart.values]}
    flow_svg = _flow_svg(chart_data)

    body = f"""
  <section class="kpis c4">
    <div class="kpi"><div class="lbl">Eventos no delta</div><div class="val">{n_eventos}</div><div class="foot">{len(insider)} de administradores</div></div>
    <div class="kpi"><div class="lbl">Fluxo líquido de insiders</div><div class="val {'pos' if fluxo>=0 else 'neg'}">{_brl(fluxo,True)}</div><div class="foot">compras − vendas (R$)</div></div>
    <div class="kpi"><div class="lbl">Emissores com compra líquida</div><div class="val">{n_compra}<span style="color:var(--faint);font-size:15px"> / {meta.get('n_emissores','—')}</span></div><div class="foot">insider net buyers</div></div>
    <div class="kpi"><div class="lbl">Sinais de recompra</div><div class="val">{n_recompra}</div><div class="foot">VLMO tesouraria + IPE</div></div>
  </section>
  <div class="grid">
    <section class="card">
      <div class="card-h"><h2>Fita de movimentações</h2>
        <div class="card-tools"><span class="meta" id="tape-count"></span>
          <div class="sel sel-sm"><select id="org-filter" aria-label="Filtrar por comprador (órgão)">{org_opts}</select></div></div></div>
      <div class="tape-head"><span>Comp.</span><span>Papel</span><span>Órgão</span><span>Operação</span>
        <span style="text-align:right">Qtde</span><span style="text-align:right">Preço méd.</span><span style="text-align:right">Valor</span></div>
      <div class="tape">{''.join(rows)}</div>
    </section>
    <div class="right">
      <section class="card"><div class="card-h"><h2>Fluxo líquido por emissor</h2><span class="meta">R$ mi</span></div>
        <div class="chart-box">{flow_svg}</div></section>
      <section class="card"><div class="card-h"><h2>Tesouraria &amp; recompra</h2><span class="meta">VLMO + IPE</span></div>
        <div class="tes-list">{''.join(tes)}</div></section>
    </div>
  </div>
  <section class="method">
    <div><h3>O que monitora</h3><p>Compras e vendas de <b>Diretoria, Conselho de Administração e controladores</b>, e movimentações de <b>ações em tesouraria</b>, restrito ao {meta.get('universo','Ibovespa')}.</p></div>
    <div><h3>Fontes</h3><p><b>VLMO</b> (art. 11 Res. CVM 44) para insiders e tesouraria; <b>IPE</b> para recompra — este entrega o <b>link do documento</b>, não a quantidade.</p></div>
    <div><h3>Cadência &amp; chave</h3><p>Informe <b>mensal</b> (entrega até dia 10); não é intraday. Join por <b>Codigo_CVM</b>. O delta são os registros novos desde a última execução.</p></div>
  </section>"""
    return {"body": body + _FILTER_JS, "chart_data": chart_data}


def digest_script(chart_data: dict) -> str:
    # O gráfico da Fita agora é SVG estático (sem dependência de JS/biblioteca).
    return ""


def build_html(vlmo, ipe, meta) -> str:
    frag = digest_fragment(vlmo, ipe, meta)
    mode = meta.get("mode", "produção")
    chip = (f'<span class="mode preview">{mode}</span>' if ("prév" in mode.lower() or "demo" in mode.lower())
            else f'<span class="mode">{mode}</span>')
    return f"""<!doctype html><html lang="pt-BR">{theme.head('Fita de Insiders & Tesouraria · Ibovespa')}
<body><div class="wrap">
  <header><div class="kicker">Petros · Mesa de Renda Variável · Vigilância Regulatória</div>
    <h1>Fita de <em>Insiders</em> &amp; Tesouraria</h1>
    <div class="sub"><span>Universo <b>{meta.get('universo','Ibovespa')}</b></span>·
      <span>Competência <b>{meta.get('competencia','—')}</b></span>·
      <span>Gerado em <b>{meta.get('gerado','—')}</b></span>{chip}</div>
  </header>
  {frag['body']}
  <footer><span>cvm-insider-monitor · digest</span><span>{meta.get('gerado','—')}</span></footer>
</div>
{digest_script(frag['chart_data'])}
</body></html>"""
