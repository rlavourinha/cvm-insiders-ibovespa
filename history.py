"""
Viewer interativo de histórico (12 meses) por empresa.

Expõe:
  history_fragment(data, months, meta) -> {'body', 'options'}
  history_script(data, months) -> <script> IIFE com seletor + gráfico mensal
  build_html(...) -> página standalone
  aggregate_from_ledger / demo_data -> dados

Sem str.format(): scripts montados com .replace(sentinela).
"""

from __future__ import annotations

import datetime as dt
import json
import pandas as pd

import config
import theme

_MES = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"]


def _months_window(n=12, ref=None):
    ref = ref or dt.date.today().replace(day=1)
    out, y, m = [], ref.year, ref.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0: m, y = 12, y - 1
    return list(reversed(out))


def _label(ym):
    y, m = ym.split("-")
    return f"{_MES[int(m)-1]}/{y[2:]}"


def aggregate_from_ledger(ledger, months):
    data = {}
    if ledger.empty: return data
    ledger = ledger.copy()
    comp = ledger.get("data_ref")
    if "data_entrega" in ledger:
        comp = comp.fillna(ledger["data_entrega"])
    ledger["_ym"] = pd.to_datetime(comp, errors="coerce").dt.strftime("%Y-%m")
    idx = {ym: i for i, ym in enumerate(months)}
    for tk, g in ledger.groupby("ticker"):
        c, v, rec = [0.0]*len(months), [0.0]*len(months), [0]*len(months)
        for _, r in g.iterrows():
            i = idx.get(r["_ym"])
            if i is None: continue
            if r.get("fonte") == "IPE" or r.get("classe") == "tesouraria": rec[i] += 1
            if r.get("fonte") == "VLMO" and r.get("classe") == "insider":
                val = float(r.get("volume") or 0)
                (c if r.get("direcao") == "compra" else v).__setitem__(i, (c if r.get("direcao")=="compra" else v)[i] + val)
        data[tk] = {"compras": c, "vendas": v, "recompra": rec}
    return data


def demo_data(months):
    import random
    random.seed(11)
    data = {}
    for tk in config.IBOV:
        intens = random.choice([0.2, 0.5, 1.0, 1.8])
        c, v, rec = [], [], []
        for _ in months:
            c.append(round(random.uniform(0, 60e6) * intens * (random.random() > 0.35), 0))
            v.append(round(random.uniform(0, 45e6) * intens * (random.random() > 0.45), 0))
            rec.append(1 if random.random() > 0.85 else 0)
        data[tk] = {"compras": c, "vendas": v, "recompra": rec}
    return data


def history_fragment(data, months, meta) -> dict:
    tickers = sorted(data.keys())
    options = "".join(f'<option value="{t}">{t}</option>' for t in tickers)
    janela = f"{_label(months[0])} – {_label(months[-1])}"
    body = f"""
  <div class="picker">
    <label for="emp">Empresa</label>
    <div class="sel"><select id="emp">{options}</select></div>
    <span class="sub" id="hint" style="color:var(--faint)">selecione um emissor do Ibovespa</span>
  </div>
  <section class="kpis c5">
    <div class="kpi"><div class="lbl">Fluxo líquido 12m</div><div class="val" id="k_net">—</div></div>
    <div class="kpi"><div class="lbl">Compras (R$)</div><div class="val pos" id="k_buy">—</div></div>
    <div class="kpi"><div class="lbl">Vendas (R$)</div><div class="val neg" id="k_sell">—</div></div>
    <div class="kpi"><div class="lbl">Meses c/ compra líq.</div><div class="val" id="k_pos">—</div></div>
    <div class="kpi"><div class="lbl">Sinais de recompra</div><div class="val gold" id="k_rec">—</div></div>
  </section>
  <section class="card">
    <div class="card-h"><h2 id="h_title">—</h2><span class="meta">{janela} · R$ mi/mês</span></div>
    <div class="legend">
      <span><i style="background:var(--buy)"></i>Compras de insiders</span>
      <span><i style="background:var(--sell)"></i>Vendas de insiders</span>
      <span><i class="ln" style="background:var(--gold)"></i>Fluxo líquido</span>
      <span><i style="background:var(--gold);opacity:.5"></i>Mês com recompra/tesouraria</span>
    </div>
    <div class="hist-chart" id="histsvg"></div>
  </section>"""
    return {"body": body, "options": options}


def history_script(data, months) -> str:
    labels = [_label(m) for m in months]
    default = "VALE3" if "VALE3" in data else (sorted(data)[0] if data else "")
    js = r"""<script>(()=>{
  const DATA = __PAYLOAD_DATA__;
  const META = __PAYLOAD_META__;
  const sel = document.getElementById('emp'); if(!sel) return;
  const box = document.getElementById('histsvg');
  const fmtBRL=(v,signed)=>{ if(v==null||isNaN(v))return '\u2014'; const a=Math.abs(v); let s;
    if(a>=1e9)s='R$ '+(v/1e9).toFixed(2)+' bi'; else if(a>=1e6)s='R$ '+(v/1e6).toFixed(1)+' mi';
    else if(a>=1e3)s='R$ '+Math.round(v/1e3).toLocaleString('en-US')+' mil'; else s='R$ '+Math.round(v).toLocaleString('en-US');
    return (signed&&v>0?'+':'')+s; };
  function makeSVG(d){
    const L=META.labels, n=L.length;
    const W=720,H=340,padL=46,padR=14,padT=16,padB=42;
    const plotW=W-padL-padR, plotH=H-padT-padB, y0=padT+plotH/2;
    const buy=d.compras.map(v=>v/1e6), sell=d.vendas.map(v=>v/1e6);
    const net=d.compras.map((v,i)=>(v-d.vendas[i])/1e6);
    const maxabs=Math.max(1,...buy,...sell,...net.map(Math.abs));
    const sc=(plotH/2-8)/maxabs, slot=plotW/n, bw=slot*0.46;
    let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Histórico mensal de movimentações">`;
    s+=`<line class="svg-grid" x1="${padL}" y1="${padT}" x2="${W-padR}" y2="${padT}"/>`;
    s+=`<line class="svg-grid" x1="${padL}" y1="${padT+plotH}" x2="${W-padR}" y2="${padT+plotH}"/>`;
    s+=`<line class="svg-zero" x1="${padL}" y1="${y0}" x2="${W-padR}" y2="${y0}"/>`;
    s+=`<text class="svg-lbl" x="${padL-7}" y="${padT+4}" text-anchor="end">+${maxabs.toFixed(0)}</text>`;
    s+=`<text class="svg-lbl" x="${padL-7}" y="${y0+4}" text-anchor="end">0</text>`;
    s+=`<text class="svg-lbl" x="${padL-7}" y="${padT+plotH+4}" text-anchor="end">\u2212${maxabs.toFixed(0)}</text>`;
    const pts=[];
    for(let i=0;i<n;i++){
      const xc=padL+slot*i+slot/2;
      const hb=buy[i]*sc; if(hb>0.3) s+=`<rect x="${(xc-bw/2).toFixed(1)}" y="${(y0-hb).toFixed(1)}" width="${bw.toFixed(1)}" height="${hb.toFixed(1)}" rx="2" fill="var(--buy)"/>`;
      const hs=sell[i]*sc; if(hs>0.3) s+=`<rect x="${(xc-bw/2).toFixed(1)}" y="${y0.toFixed(1)}" width="${bw.toFixed(1)}" height="${hs.toFixed(1)}" rx="2" fill="var(--sell)"/>`;
      pts.push(`${xc.toFixed(1)},${(y0-net[i]*sc).toFixed(1)}`);
      if(d.recompra[i]>0){ s+=`<path d="M ${xc-5} ${y0} L ${xc} ${y0-5} L ${xc+5} ${y0} L ${xc} ${y0+5} Z" fill="rgba(212,165,58,.5)" stroke="var(--gold)"/>`; }
      s+=`<text class="svg-axis" x="${xc.toFixed(1)}" y="${(padT+plotH+18).toFixed(1)}" text-anchor="middle">${L[i]}</text>`;
    }
    s+=`<polyline points="${pts.join(' ')}" fill="none" stroke="var(--gold)" stroke-width="2"/>`;
    for(let i=0;i<n;i++){ const xc=padL+slot*i+slot/2; s+=`<circle cx="${xc.toFixed(1)}" cy="${(y0-net[i]*sc).toFixed(1)}" r="2.6" fill="var(--gold)"/>`; }
    s+=`</svg>`; return s;
  }
  function render(tk){
    const d=DATA[tk]||{compras:[],vendas:[],recompra:[]};
    const tB=d.compras.reduce((a,b)=>a+b,0), tS=d.vendas.reduce((a,b)=>a+b,0), tN=tB-tS;
    const net=d.compras.map((v,i)=>v-d.vendas[i]); const mp=net.filter(v=>v>0).length;
    const tR=d.recompra.reduce((a,b)=>a+b,0);
    document.getElementById('h_title').textContent=tk+' \u00b7 hist\u00f3rico mensal';
    const hint=document.getElementById('hint'); if(hint) hint.textContent='';
    const K=(id,val,cls)=>{const e=document.getElementById(id);e.textContent=val;if(cls)e.className='val '+cls;};
    K('k_net',fmtBRL(tN,true),tN>=0?'pos':'neg'); K('k_buy',fmtBRL(tB),'pos'); K('k_sell',fmtBRL(tS),'neg');
    K('k_pos',mp+' / 12',''); K('k_rec',tR,'gold');
    if(box) box.innerHTML=makeSVG(d);
  }
  sel.value=META.default; render(META.default);
  sel.addEventListener('change',e=>render(e.target.value));
})();</script>"""
    import json as _j
    return js.replace("__PAYLOAD_DATA__", _j.dumps(data, ensure_ascii=False)) \
             .replace("__PAYLOAD_META__", _j.dumps({"labels": labels, "default": default}, ensure_ascii=False))


def build_html(data, months, mode) -> str:
    frag = history_fragment(data, months, {})
    chip = (f'<span class="mode preview">{mode}</span>' if ("prév" in mode.lower() or "demo" in mode.lower())
            else f'<span class="mode">{mode}</span>')
    janela = f"{_label(months[0])} – {_label(months[-1])}"
    return f"""<!doctype html><html lang="pt-BR">{theme.head('Histórico 12 meses · Insiders & Tesouraria')}
<body><div class="wrap">
  <header><div class="kicker">Petros · Mesa de Renda Variável</div>
    <h1>Histórico <em>12 meses</em></h1>
    <div class="sub"><span>Movimentações de insiders &amp; tesouraria · VLMO + IPE</span>·
      <span>Janela <b>{janela}</b></span>{chip}</div></header>
  {frag['body']}
  <footer><span>cvm-insider-monitor · histórico</span><span>{dt.datetime.now():%d/%m/%Y %H:%M}</span></footer>
</div>
{history_script(data, months)}
</body></html>"""


def main(demo):
    months = _months_window(12)
    if demo:
        data, mode = demo_data(months), "prévia · dados de exemplo"
    else:
        import os
        pq = config.OUTPUT_DIR / f"{config.LEDGER_NAME}.parquet"
        cv = config.OUTPUT_DIR / f"{config.LEDGER_NAME}.csv"
        if pq.exists(): ledger = pd.read_parquet(pq)
        elif cv.exists(): ledger = pd.read_csv(cv)
        else:
            print("[history] ledger ausente — rode 'python monitor.py' ou use --demo"); return
        data, mode = aggregate_from_ledger(ledger, months), "produção"
    out = config.OUTPUT_DIR / ("historico_preview.html" if demo else "historico.html")
    out.write_text(build_html(data, months, mode), encoding="utf-8")
    print(f"[history] {out}  ({len(data)} emissores)")


if __name__ == "__main__":
    import sys
    main(demo="--demo" in sys.argv)
