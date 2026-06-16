"""
Tema compartilhado pelos relatórios (digest, histórico e dashboard combinado).
Centraliza paleta, CSS (superset das duas telas + abas) e o <head> com fontes
e Chart.js, para que as três saídas tenham identidade idêntica sem duplicação.
"""

CSS = r"""
:root{
  --bg:#0B1117; --panel:#121A22; --panel2:#18232E; --line:#243240;
  --paper:#E7E3D8; --muted:#8596A2; --faint:#5C6B76;
  --buy:#4FB286; --sell:#D86A4A; --gold:#D4A53A;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--paper);
  font-family:'Inter',system-ui,sans-serif;line-height:1.45;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:38px 26px 60px}
a{color:var(--gold);text-decoration:none;border-bottom:1px solid transparent}
a:hover{border-bottom-color:var(--gold)}

.kicker{font:600 11px/1 'Inter',sans-serif;letter-spacing:.22em;text-transform:uppercase;color:var(--gold);margin-bottom:14px}
h1{font-family:'Fraunces',serif;font-weight:560;font-size:clamp(30px,5vw,50px);line-height:1.02;letter-spacing:-.01em;margin:0 0 12px}
h1 em{font-style:italic;color:var(--gold)}
.sub{color:var(--muted);font-size:14px;display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center}
.sub b{color:var(--paper);font-weight:500}
.mode{font:600 10px/1 'IBM Plex Mono',monospace;letter-spacing:.14em;text-transform:uppercase;padding:5px 9px;border:1px solid var(--line);border-radius:3px;color:var(--muted)}
.mode.preview{color:var(--gold);border-color:var(--gold)}

/* abas */
.tabs{display:flex;gap:4px;margin:26px 0 24px;border-bottom:1px solid var(--line)}
.tab{appearance:none;background:none;border:0;cursor:pointer;
  font:600 13px 'Inter',sans-serif;color:var(--muted);padding:13px 18px;
  border-bottom:2px solid transparent;margin-bottom:-1px;transition:color .15s}
.tab:hover{color:var(--paper)}
.tab.active{color:var(--paper);border-bottom-color:var(--gold)}
.tab .n{font:600 11px 'IBM Plex Mono',monospace;color:var(--faint);margin-left:7px}
.panel{display:none}
.panel.active{display:block}

/* barra de competência (aba Último mês) */
.month-bar{display:flex;flex-wrap:wrap;gap:8px 26px;align-items:center;margin:0 0 22px;padding:13px 18px;
  background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--gold);border-radius:8px;
  font:500 13px 'IBM Plex Mono',monospace;color:var(--muted)}
.month-bar b{color:var(--paper);font-weight:600}

/* kpis */
.kpis{display:grid;gap:0;margin:0 0 24px;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:var(--panel)}
.kpis.c4{grid-template-columns:repeat(4,1fr)} .kpis.c5{grid-template-columns:repeat(5,1fr)}
.kpi{padding:18px 20px;border-right:1px solid var(--line)}
.kpi:last-child{border-right:0}
.kpi .lbl{font:600 10px/1 'Inter',sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);margin-bottom:10px}
.kpi .val{font:600 22px 'IBM Plex Mono',monospace}
.kpi .val.serif{font-family:'Fraunces',serif;font-weight:560;font-size:26px}
.kpi .val.pos{color:var(--buy)} .kpi .val.neg{color:var(--sell)} .kpi .val.gold{color:var(--gold)}
.kpi .foot{font-size:12px;color:var(--muted);margin-top:7px}

/* cards */
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px}
.card-h{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:16px 20px;border-bottom:1px solid var(--line)}
.card-h h2{font-family:'Fraunces',serif;font-weight:560;font-size:18px;margin:0}
.card-h .meta{font:500 11px 'IBM Plex Mono',monospace;color:var(--faint);letter-spacing:.04em}
.card-tools{display:flex;align-items:center;gap:12px}
.card-tools #tape-count{white-space:nowrap}
.sel-sm select{font:600 12px 'IBM Plex Mono',monospace;padding:7px 30px 7px 11px;min-width:150px;letter-spacing:.02em}
.sel-sm.sel::after{right:12px;font-size:12px}

/* grid digest */
.grid{display:grid;grid-template-columns:1.55fr 1fr;gap:22px;align-items:start}
.right{display:flex;flex-direction:column;gap:22px}
.chart-box{padding:14px 16px 18px}
.chart-box svg,.hist-chart svg{width:100%;height:auto;display:block}
.svg-grid{stroke:rgba(36,50,64,.7);stroke-width:1}
.svg-zero{stroke:var(--faint);stroke-width:1}
.svg-lbl{fill:var(--muted);font-family:'IBM Plex Mono',monospace;font-size:11px}
.svg-tkr{fill:var(--paper);font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:600}
.svg-val{fill:var(--muted);font-family:'IBM Plex Mono',monospace;font-size:10px}
.svg-axis{fill:var(--faint);font-family:'IBM Plex Mono',monospace;font-size:10px}

/* fita */
.tape{padding:6px 0 8px;max-height:560px;overflow-y:auto}
.tape-head,.tape-row{display:grid;grid-template-columns:78px 64px 1fr 70px 78px 84px 96px;gap:10px;align-items:center;padding:9px 20px;font-family:'IBM Plex Mono',monospace;font-size:12.5px}
.tape-head{color:var(--faint);font-size:10px;letter-spacing:.08em;text-transform:uppercase;position:sticky;top:0;background:var(--panel);border-bottom:1px solid var(--line);padding-top:12px;padding-bottom:12px}
.tape-row{border-left:2px solid transparent;border-bottom:1px solid rgba(36,50,64,.5);transition:background .12s}
.tape-row:hover{background:var(--panel2)}
.tape-row.compra{border-left-color:var(--buy)} .tape-row.venda{border-left-color:var(--sell)}
.t-tkr{font-weight:600;color:var(--paper)}
.t-org{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.t-num{text-align:right;color:var(--paper)} .t-num.strong{font-weight:600}
.t-chip{font-size:9.5px;font-weight:600;letter-spacing:.08em;text-align:center;padding:3px 0;border-radius:3px}
.t-chip.compra{color:var(--buy);background:rgba(79,178,134,.12)}
.t-chip.venda{color:var(--sell);background:rgba(216,106,74,.12)}

/* tesouraria */
.tes-list{padding:8px 0}
.tes-item{padding:13px 20px;border-bottom:1px solid rgba(36,50,64,.5)} .tes-item:last-child{border-bottom:0}
.tes-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:5px}
.tes-head .tkr{font:600 13px 'IBM Plex Mono',monospace;color:var(--paper)}
.tag{font:600 9.5px 'Inter',sans-serif;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);border:1px solid var(--line);padding:3px 7px;border-radius:3px}
.tag.gold{color:var(--gold);border-color:rgba(212,165,58,.4)}
.tes-body{font-size:13px;color:var(--paper)}
.tes-meta{font:500 11px 'IBM Plex Mono',monospace;color:var(--faint);margin-top:5px}
.empty{padding:26px 20px;color:var(--faint);font-size:13px;text-align:center}

/* método */
.method{margin-top:30px;border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:22px 24px;display:grid;grid-template-columns:repeat(3,1fr);gap:24px}
.method h3{font:600 10.5px 'Inter',sans-serif;letter-spacing:.13em;text-transform:uppercase;color:var(--gold);margin:0 0 8px}
.method p{margin:0;font-size:13px;color:var(--muted)} .method b{color:var(--paper);font-weight:500}

/* histórico: seletor + legenda */
.picker{display:flex;align-items:center;gap:14px;margin:0 0 22px;flex-wrap:wrap}
.picker label{font:600 10.5px 'Inter',sans-serif;letter-spacing:.13em;text-transform:uppercase;color:var(--faint)}
.sel{position:relative}
select{appearance:none;background:var(--panel);color:var(--paper);border:1px solid var(--line);border-radius:6px;padding:12px 42px 12px 16px;font:600 18px 'IBM Plex Mono',monospace;letter-spacing:.04em;cursor:pointer;min-width:160px}
select:focus{outline:2px solid var(--gold);outline-offset:1px}
.sel::after{content:"▾";position:absolute;right:15px;top:50%;transform:translateY(-50%);color:var(--gold);pointer-events:none;font-size:14px}
.hist-chart{padding:14px 16px 18px}
.legend{display:flex;gap:18px;padding:0 20px 16px;font-size:12px;color:var(--muted);flex-wrap:wrap}
.legend i{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.legend .ln{width:16px;height:2px;border-radius:0}

footer{margin-top:26px;color:var(--faint);font-size:11.5px;font-family:'IBM Plex Mono',monospace;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}

@media (max-width:880px){
  .kpis.c4,.kpis.c5{grid-template-columns:repeat(2,1fr)}
  .kpi:nth-child(2){border-right:0}
  .grid{grid-template-columns:1fr} .method{grid-template-columns:1fr}
  .tape-head,.tape-row{grid-template-columns:64px 56px 1fr 62px 70px}
  .tape-head span:nth-child(6),.tape-head span:nth-child(7),.tape-row .t-num:nth-child(6){display:none}
}
"""


def head(title: str) -> str:
    return f"""<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,560;9..144,620&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head>"""
