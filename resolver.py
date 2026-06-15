"""
Resolve os tickers do Ibovespa para o Codigo_CVM (chave de join com o VLMO),
usando o cadastro de companhias abertas (cad_cia_aberta.csv).

O VLMO é chaveado por Codigo_CVM / CNPJ, não por ticker. Como o cadastro não
traz ticker, casamos por substring da razão social (tokens em config.IBOV).
O resultado é cacheado em state/cd_cvm_map.json — só re-resolve se você apagar
o cache ou passar force=True.
"""

from __future__ import annotations

import json
import re
import unicodedata

import pandas as pd

import config
from fetch import download

CACHE = config.STATE_DIR / "cd_cvm_map.json"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return s.upper().strip()


def _find_col(cols, *patterns) -> str | None:
    for p in patterns:
        for c in cols:
            if p in _norm(c).replace("_", " "):
                return c
    return None


def resolve(force: bool = False) -> dict[str, dict]:
    """Retorna {ticker: {'cd_cvm': int, 'cnpj': str, 'denom': str}}."""
    if CACHE.exists() and not force:
        return json.loads(CACHE.read_text(encoding="utf-8"))

    path = download(config.CAD_URL, config.DATA_DIR / "cad_cia_aberta.csv")
    cad = pd.read_csv(path, sep=config.SEP, encoding=config.ENCODING, dtype=str)

    col_denom = _find_col(cad.columns, "DENOM SOCIAL", "DENOM", "NOME EMPRESARIAL")
    col_cvm = _find_col(cad.columns, "CD CVM", "CODIGO CVM")
    col_cnpj = _find_col(cad.columns, "CNPJ")
    col_sit = _find_col(cad.columns, "SIT")  # situação registral
    if not (col_denom and col_cvm):
        raise RuntimeError(f"Não localizei colunas no cadastro. Cabeçalho: {list(cad.columns)}")

    # Mantém apenas registros ativos quando a coluna existir
    if col_sit:
        cad = cad[cad[col_sit].fillna("").str.upper().str.contains("ATIVO")]
    cad["_denom_norm"] = cad[col_denom].map(_norm)

    mapping: dict[str, dict] = {}
    nao_resolvidos: list[str] = []
    for ticker, token in config.IBOV.items():
        hit = cad[cad["_denom_norm"].str.contains(_norm(token), na=False)]
        if hit.empty:
            nao_resolvidos.append(f"{ticker} ({token})")
            continue
        # Em caso de múltiplos, pega o de razão social mais curta (matriz, não subsidiária)
        row = hit.loc[hit["_denom_norm"].str.len().idxmin()]
        mapping[ticker] = {
            "cd_cvm": int(str(row[col_cvm]).strip() or 0),
            "cnpj": str(row[col_cnpj]).strip() if col_cnpj else "",
            "denom": str(row[col_denom]).strip(),
        }

    CACHE.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    if nao_resolvidos:
        print(f"[resolver] {len(nao_resolvidos)} ticker(s) sem match — ajuste o token em "
              f"config.IBOV: {', '.join(nao_resolvidos)}")
    print(f"[resolver] {len(mapping)} tickers resolvidos -> {CACHE}")
    return mapping


def cd_cvm_set(mapping: dict[str, dict]) -> set[int]:
    return {v["cd_cvm"] for v in mapping.values() if v.get("cd_cvm")}


def cd_to_tickers(mapping: dict[str, dict]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for tk, v in mapping.items():
        out.setdefault(v["cd_cvm"], []).append(tk)
    return out


def cnpj_to_cd(mapping: dict[str, dict]) -> dict[str, int]:
    """{cnpj_so_digitos: cd_cvm} — usado para resolver cd_cvm na tabela de
    movimentação do VLMO, que identifica a companhia só por CNPJ."""
    out: dict[str, int] = {}
    for v in mapping.values():
        cnpj = re.sub(r"\D", "", v.get("cnpj") or "")
        if cnpj and v.get("cd_cvm"):
            out[cnpj] = v["cd_cvm"]
    return out


if __name__ == "__main__":
    import sys
    resolve(force="--force" in sys.argv)
