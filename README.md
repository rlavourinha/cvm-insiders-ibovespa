# CVM Insider & Tesouraria Monitor — Ibovespa

Rotina de acompanhamento de **compras/vendas de administradores** (Diretoria,
Conselho de Administração, controladores) e **movimentações de tesouraria** das
empresas do Ibovespa, a partir do Portal de Dados Abertos da CVM. Sem backfill
histórico: a cada execução detecta o **delta** de registros novos e emite um
digest visual + um ledger acumulado.

## Início rápido

```bash
make setup       # instala dependências
make demo        # gera output/dashboard_preview.html com dados de exemplo (offline)
make dashboard   # produção: coleta na CVM + ledger + dashboard.html
```

Abra `output/dashboard_preview.html` no navegador. O HTML é autossuficiente
(gráficos em SVG, sem CDN) — funciona offline e atrás de firewall corporativo.

## Abrir no Claude Code

```bash
cd cvm-insider-monitor
claude          # o Claude Code lê o CLAUDE.md e já entende a arquitetura e os comandos
```

O arquivo `CLAUDE.md` documenta convenções e invariantes do projeto para a edição assistida.

## Estrutura

```
cvm-insider-monitor/
├── CLAUDE.md            contexto do projeto p/ Claude Code
├── README.md
├── Makefile             setup / demo / dashboard / run / resolve / clean
├── pyproject.toml
├── requirements.txt
├── .gitignore
├── config.py            watchlist Ibovespa, paths, filtros
├── fetch.py             download condicional
├── resolver.py          ticker -> Codigo_CVM
├── parse_vlmo.py        parser VLMO (schema-discovery)
├── parse_ipe.py         filtro recompra/tesouraria no IPE
├── theme.py             CSS/paleta/head compartilhados
├── report.py            Fita (digest) + SVG de fluxo
├── history.py           Histórico 12m (SVG interativo)
├── dashboard.py         relatório combinado em abas
├── monitor.py           orquestração (collect/delta/ledger)
└── examples/
    └── dashboard_preview.html   amostra gerada (dados de exemplo)
```

## Fontes

| Sinal | Fonte | Observação |
|---|---|---|
| Insider (órgãos) + tesouraria | **VLMO** — Valores Mobiliários Negociados e Detidos (art. 11 Res. CVM 44) | Informe **mensal** (entrega até dia 10). Não é intraday. |
| Programas/execução de recompra | **IPE** — comunicados de recompra/negociação de ações | Entrega o **link do documento**, não a quantidade. |
| Resolução ticker → Codigo_CVM | **Cadastro** (`cad_cia_aberta.csv`) | Join por `Codigo_CVM`. |

## Instalação

```bash
pip install -r requirements.txt
```

## Uso

```bash
# 1. (opcional) resolver a watchlist e cachear o mapa ticker->Codigo_CVM
python resolver.py            # use --force para re-resolver

# 2. execução normal (baixa, parseia, calcula delta, grava ledger + digest)
python monitor.py

# RELATÓRIO ÚNICO combinado (Fita + Histórico 12m em abas) — recomendado
python dashboard.py            # produção
python dashboard.py --demo     # prévia offline

# (opcional) telas separadas
python monitor.py --demo       # só a Fita do delta
python history.py --demo       # só o Histórico 12 meses
```

Agendamento sugerido (a cadência útil é semanal, já que o portal atualiza
reapresentações semanalmente sobre o informe mensal):

```cron
0 8 * * 1  cd /caminho/cvm_insider_monitor && python monitor.py >> run.log 2>&1
```

## Saídas (`output/`)

- `digest_AAAAMMDD_HHMM.html` — relatório visual do delta da execução (a "fita").
- `ledger.parquet` — todos os eventos detectados, append-only, queryável em DuckDB
  (`SELECT * FROM 'output/ledger.parquet'`). Cai para `ledger.csv` se não houver
  engine Parquet.
- `dashboard.html` / `dashboard_preview.html` — **relatório único** com as duas telas em abas (Fita + Histórico).
- `relatorio_preview.html`, `historico_preview.html` — telas separadas (opcional).

## Arquitetura

```
config.py      watchlist Ibovespa, paths, filtros de órgão, override de schema
resolver.py    ticker -> Codigo_CVM via cadastro (cache em state/)
fetch.py       download condicional (ETag/Last-Modified) -> não re-baixa histórico
parse_vlmo.py  parser VLMO com DETECÇÃO DE SCHEMA em runtime
parse_ipe.py   filtro de recompra/tesouraria no índice IPE
theme.py       paleta + CSS compartilhado + <head> (fontes, Chart.js)
report.py      digest_fragment()/build_html() -> Fita (insiders + tesouraria)
history.py     history_fragment()/build_html() -> Histórico 12m por empresa
dashboard.py   build() -> RELATÓRIO ÚNICO combinando as duas telas em abas
monitor.py     orquestra: collect() -> delta -> ledger -> digest
```

### Detecção de schema

`parse_vlmo.py` e `parse_ipe.py` **não** dependem de nomes fixos de coluna: leem o
cabeçalho e mapeiam por padrão (regex). Isso sobrevive às reapresentações da CVM.
Se algum dia a detecção falhar, force o mapeamento em `config.COLUMN_HINTS`, ex.:

```python
COLUMN_HINTS = {"quantidade": "Quantidade", "orgao": "Tipo_Cargo", "tipo_mov": "Tipo_Movimentacao"}
```

## Sem dependências externas

Os gráficos são **SVG inline** (sem Chart.js/CDN) e as fontes degradam para o sistema se bloqueadas — o HTML abre offline e atrás de firewall corporativo.

## Limitações (por design)

- **Cadência mensal.** O VLMO é o consolidado regulatório mensal; o delta detecta
  registros novos, mas o sinal não antecipa o pregão.
- **IPE = link.** Os comunicados de recompra apontam o documento; a quantidade
  efetivamente recomprada exige leitura do PDF (não incluída).
- **Universo fixo na carteira mai–ago/2026.** No rebalanceamento (set/2026),
  atualize `config.IBOV` e rode `python resolver.py --force`.
