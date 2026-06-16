"""
Dashboard combinado: as duas telas num único HTML, com abas.

  Aba 1 — Fita do delta   (digest de insiders & tesouraria do período)
  Aba 2 — Histórico 12 m  (seletor de empresa + série mensal)

  python dashboard.py          produção (collect + ledger)
  python dashboard.py --demo   prévia offline

Compõe os fragmentos de report.py e history.py sob um <head> e um header únicos;
cada script roda em IIFE isolado para não colidir escopo.
"""

from __future__ import annotations

import datetime as dt
import pandas as pd

import config, theme, report, history, monitor

_MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _comp_label(s) -> str:           # "2026-05-01" -> "mai/2026"
    try:
        return f"{_MES[int(str(s)[5:7]) - 1]}/{str(s)[:4]}"
    except Exception:
        return "—"


def _date_br(s) -> str:              # "2026-05-31" -> "31/05/2026"
    s = str(s or "")
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) >= 10 else "—"


def build(vlmo, ipe, hist_data, months, meta) -> str:
    mfrag = report.month_fragment(vlmo, ipe, meta)
    dfrag = report.digest_fragment(vlmo, ipe, meta)
    hfrag = history.history_fragment(hist_data, months, meta)
    n_mes = mfrag.get("n", 0)
    n_delta = (len(vlmo) if vlmo is not None else 0) + (len(ipe) if ipe is not None else 0)
    n_emis = len(hist_data)
    mode = meta.get("mode", "produção")
    chip = (f'<span class="mode preview">{mode}</span>'
            if ("prév" in mode.lower() or "demo" in mode.lower())
            else f'<span class="mode">{mode}</span>')
    fresh = (f'·<span>Dados até <b>{meta.get("dados_ate","—")}</b></span>'
             f'·<span><b>{meta.get("reportaram","—")}/{meta.get("n_universo","—")}</b> reportaram</span>')

    tab_js = """<script>(()=>{
  const tabs=[...document.querySelectorAll('.tab')], panels=[...document.querySelectorAll('.panel')];
  function show(id){
    tabs.forEach(t=>t.classList.toggle('active', t.dataset.t===id));
    panels.forEach(p=>p.classList.toggle('active', p.id===id));
  }
  tabs.forEach(t=>t.addEventListener('click',()=>show(t.dataset.t)));
})();</script>"""

    return f"""<!doctype html><html lang="pt-BR">{theme.head('Insiders & Tesouraria · Ibovespa')}
<body><div class="wrap">
  <header>
    <div class="kicker">Petros · Mesa de Renda Variável · Vigilância Regulatória</div>
    <h1>Insiders &amp; <em>Tesouraria</em> · Ibovespa</h1>
    <div class="sub"><span>Universo <b>{meta.get('universo','Ibovespa')}</b></span>·
      <span>Competência <b>{meta.get('competencia','—')}</b></span>{fresh}·
      <span>Gerado em <b>{meta.get('gerado','—')}</b></span>{chip}</div>
  </header>

  <nav class="tabs">
    <button class="tab active" data-t="mes">Último mês<span class="n">{n_mes}</span></button>
    <button class="tab" data-t="fita">Fita do delta<span class="n">{n_delta}</span></button>
    <button class="tab" data-t="hist">Histórico 12 meses<span class="n">{n_emis}</span></button>
  </nav>

  <section class="panel active" id="mes">{mfrag['body']}</section>
  <section class="panel" id="fita">{dfrag['body']}</section>
  <section class="panel" id="hist">{hfrag['body']}</section>

  <footer><span>cvm-insider-monitor · dashboard</span><span>{meta.get('gerado','—')}</span></footer>
</div>
{history.history_script(hist_data, months)}
{tab_js}
</body></html>"""


def main(demo: bool) -> None:
    months = history._months_window(12)
    now = dt.datetime.now()
    meta = dict(universo="Ibovespa (76 emissores)", gerado=now.strftime("%d/%m/%Y %H:%M"))
    if demo:
        vlmo, ipe = monitor.demo_events()
        hist_data = history.demo_data(months)
        info = {"competencia": "2026-05-01", "dados_ate": "2026-05-29",
                "reportaram": list(range(75)), "n_total": 76}
        meta["mode"] = "prévia · dados de exemplo"
        out = config.OUTPUT_DIR / "dashboard_preview.html"
    else:
        vlmo, ipe, _delta, n, info = monitor.collect()
        meta["mode"] = "produção"; meta["n_emissores"] = n
        pq = config.OUTPUT_DIR / f"{config.LEDGER_NAME}.parquet"
        cv = config.OUTPUT_DIR / f"{config.LEDGER_NAME}.csv"
        ledger = (pd.read_parquet(pq) if pq.exists()
                  else (pd.read_csv(cv) if cv.exists() else pd.DataFrame()))
        hist_data = history.aggregate_from_ledger(ledger, months)
        out = config.OUTPUT_DIR / "dashboard.html"
    comp = info.get("competencia")
    meta["competencia"] = _comp_label(comp)
    meta["competencia_ym"] = str(comp)[:7] if comp else ""
    meta["dados_ate"] = _date_br(info.get("dados_ate"))
    meta["reportaram"] = len(info.get("reportaram") or [])
    meta["n_universo"] = info.get("n_total") or meta.get("n_emissores") or 76
    out.write_text(build(vlmo, ipe, hist_data, months, meta), encoding="utf-8")
    print(f"[dashboard] {out}  (mês: {meta['competencia']} · fita: {len(vlmo)+len(ipe)} eventos · "
          f"histórico: {len(hist_data)} emissores · {meta['reportaram']}/{meta['n_universo']} reportaram)")


if __name__ == "__main__":
    import sys
    main(demo="--demo" in sys.argv)
