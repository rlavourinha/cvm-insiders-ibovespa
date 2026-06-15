# CLAUDE.md

Contexto do projeto para o Claude Code. Leia antes de editar.

## O que é

Rotina de **monitoramento de movimentações de insiders e tesouraria** das empresas
do **Ibovespa**, a partir do Portal de Dados Abertos da CVM. A cada execução baixa
os informes, detecta o **delta** de registros novos, acumula um **ledger** e gera um
**dashboard HTML** (Fita do delta + Histórico 12 meses) com gráficos em **SVG inline**.

Não há backfill histórico: o foco é acompanhar eventos novos de forma incremental.

## Comandos

```bash
make setup        # pip install -r requirements.txt
make demo         # dashboard offline com dados sintéticos (não toca a rede)
make dashboard    # produção: coleta + ledger + dashboard.html
make run          # produção: só a Fita (digest) + ledger
make resolve      # (re)resolve tickers Ibovespa -> Codigo_CVM (cache em state/)
make clean        # limpa data/ state/ output/ __pycache__
```

Sem `make`: `python dashboard.py [--demo]`, `python monitor.py [--demo]`,
`python history.py [--demo]`, `python resolver.py [--force]`.

## Arquitetura (módulos flat na raiz, importam-se entre si)

```
config.py      watchlist Ibovespa (ticker->razão social), paths, filtros, COLUMN_HINTS
fetch.py       download condicional (ETag/Last-Modified) -> não re-baixa histórico
resolver.py    ticker -> Codigo_CVM via cad_cia_aberta.csv (cache JSON em state/)
parse_vlmo.py  parser VLMO com DETECÇÃO DE SCHEMA em runtime (insiders + tesouraria)
parse_ipe.py   filtro de recompra/tesouraria no índice IPE (entrega link, não quantidade)
theme.py       paleta + CSS compartilhado + <head> (sem CDN de JS)
report.py      Fita: _flow_svg() + digest_fragment()/build_html()
history.py     Histórico 12m: history_fragment()/history_script() (SVG via JS puro)
dashboard.py   combina Fita + Histórico em abas -> dashboard.html
monitor.py     orquestra: collect() -> compute_delta() -> write_ledger() -> digest
```

Fluxo de dados: `fetch -> parse_* -> (filtra por Codigo_CVM resolvido) -> delta -> ledger (Parquet, fallback CSV) -> render SVG`.

## Convenções e invariantes (NÃO QUEBRAR)

- **Sem dependências externas no HTML.** Gráficos são **SVG inline**; nada de Chart.js
  ou outra lib via CDN (firewall corporativo bloqueia). Fontes via Google Fonts com
  fallback de sistema (degrada sem quebrar). Não reintroduza `<script src=...>` externo.
- **Parsers não hardcodam nomes de coluna.** Leem o cabeçalho e mapeiam por regex
  (`_find`). Se a CVM mudar o layout, ajuste via `config.COLUMN_HINTS`, não com nomes fixos.
- **Templates HTML usam `.replace(sentinela)`, não `str.format()`** quando há CSS/JS,
  para evitar o inferno de escapar `{` `}`. (Bug já cometido; não repita.)
- **Cadência mensal.** VLMO é informe mensal (entrega até dia 10); não prometa intraday.
- **IPE entrega link, não quantidade** de recompra.
- **Ledger:** tenta Parquet, cai para CSV se faltar engine. Mantenha o fallback.
- **Chave de join:** `Codigo_CVM`. Delta por hash de chave de registro (`monitor._key`).

## Gotchas

- A **watchlist é a carteira Ibovespa mai–ago/2026**. No rebalanceamento (set/2026),
  atualize `config.IBOV` e rode `make resolve` (ou `python resolver.py --force`).
- `data/`, `state/`, `output/` são gerados em runtime e estão no `.gitignore`.
- Validação de HTML: os scripts JS podem ser checados com `node --check`; para runtime,
  renderizar headless com `playwright` bloqueando rede externa simula o ambiente real.

## Próximos passos sugeridos (não implementados)

- Parse do PDF do IPE para extrair a quantidade efetivamente recomprada.
- Alerta (e-mail/Slack) disparado pelo delta.
- Visão combinada: a Fita filtrando pela empresa selecionada no Histórico.
- Deep-link por hash (`#hist`) para abrir direto numa aba.
