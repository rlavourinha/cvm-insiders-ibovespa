"""
Parser do VLMO (Valores Mobiliários Negociados e Detidos — art. 11 Res. CVM 44).

Estratégia: o zip anual traz vários CSVs (header + blocos por órgão). Em vez de
hardcodar nomes de coluna (que a CVM altera em reapresentações), abrimos cada
CSV, lemos o cabeçalho e detectamos as colunas por padrão. Identificamos a
tabela de movimentação (a que tem chave de companhia + quantidade) e normalizamos
para um schema único de evento.

Saída (DataFrame): data_ref, cd_cvm, cnpj, nome, orgao, classe, tipo_mov,
especie, quantidade, preco, volume, versao, fonte.
"""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile

import pandas as pd

import config


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return s.upper().strip()


def _find(cols, *patterns) -> str | None:
    # respeita override manual de config.COLUMN_HINTS
    norm = {c: _norm(c).replace("_", " ") for c in cols}
    for p in patterns:
        for c, n in norm.items():
            if re.search(p, n):
                return c
    return None


def _to_num(s: pd.Series) -> pd.Series:
    # A CVM mistura convenções: o VLMO atual usa PONTO como decimal
    # (ex.: "10.6914225726", "1597410097.34") e quantidade inteira sem milhar,
    # mas reapresentações antigas usam vírgula decimal e ponto de milhar.
    # Heurística: trata como BR (ponto=milhar) só quando há vírgula OU mais de
    # um ponto; caso contrário, o ponto já é o separador decimal.
    x = s.astype(str).str.strip()
    br = x.str.contains(",", regex=False) | (x.str.count(r"\.") > 1)
    x = x.where(~br, x.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(x, errors="coerce")


def _only_digits(s) -> str:
    return re.sub(r"\D", "", str(s))


def _classify_orgao(orgao: str) -> str | None:
    o = _norm(orgao)
    if any(_norm(t) in o for t in config.ORGAOS_TESOURARIA):
        return "tesouraria"
    if any(_norm(t) in o for t in config.ORGAOS_INSIDER):
        return "insider"
    return None


def _pick_movement_table(zf: zipfile.ZipFile) -> str | None:
    """Escolhe o CSV que parece a tabela de movimentação consolidada."""
    best, best_score = None, -1
    for name in zf.namelist():
        if not name.lower().endswith(".csv"):
            continue
        with zf.open(name) as fh:
            header = fh.readline().decode(config.ENCODING, "ignore")
        cols = header.strip().split(config.SEP)
        score = 0
        if _find(cols, r"C(O|Ó)DIGO CVM|CD CVM"):
            score += 1
        if _find(cols, r"QUANTIDADE"):
            score += 2
        if _find(cols, r"CARGO|ORGAO|CATEGORIA|TIPO CARGO"):
            score += 1
        if _find(cols, r"MOVIMENTA|OPERA|NEGOCIA"):
            score += 1
        if score > best_score:
            best, best_score = name, score
    return best if best_score >= 3 else best  # devolve o melhor de qualquer forma


def parse(zip_path, cd_cvm_keep: set[int], cnpj_to_cd: dict[str, int] | None = None) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as zf:
        member = _pick_movement_table(zf)
        if member is None:
            return pd.DataFrame()
        raw = zf.read(member)
    df = pd.read_csv(io.BytesIO(raw), sep=config.SEP, encoding=config.ENCODING, dtype=str)
    cols = list(df.columns)

    h = config.COLUMN_HINTS
    c_cvm = h.get("cd_cvm") or _find(cols, r"C(O|Ó)DIGO CVM|CD CVM")
    c_cnpj = h.get("cnpj") or _find(cols, r"CNPJ")
    c_nome = h.get("nome") or _find(cols, r"NOME COMPAN|DENOM")
    c_data = h.get("data_ref") or _find(cols, r"DATA REFER|REFERENCIA|COMPETEN")
    c_versao = h.get("versao") or _find(cols, r"VERS")
    c_orgao = h.get("orgao") or _find(cols, r"TIPO CARGO|CARGO|ORGAO|CATEGORIA")
    c_mov = h.get("tipo_mov") or _find(cols, r"TIPO MOVIMENTA|INTENCAO|NATUREZA")
    c_oper = h.get("operacao") or _find(cols, r"TIPO OPERA|OPERACAO")
    c_esp = h.get("especie") or _find(cols, r"ESP(E|É)CIE|CARACTER|TIPO ATIVO|VALOR MOBILI")
    c_qtd = h.get("quantidade") or _find(cols, r"QUANTIDADE")
    c_prc = h.get("preco") or _find(cols, r"PRE(Ç|C)O")
    c_vol = h.get("volume") or _find(cols, r"VOLUME")

    # A tabela de movimentação do VLMO identifica a companhia por CNPJ (sem
    # Codigo_CVM). Usamos cd_cvm da coluna quando existe; senão resolvemos pelo
    # CNPJ via mapa do resolver (cad_cia_aberta traz os dois).
    if c_cvm:
        cd_cvm = pd.to_numeric(df[c_cvm], errors="coerce")
    elif c_cnpj and cnpj_to_cd:
        cd_cvm = df[c_cnpj].map(lambda x: cnpj_to_cd.get(_only_digits(x)))
        cd_cvm = pd.to_numeric(cd_cvm, errors="coerce")
    else:
        cd_cvm = pd.Series(pd.NA, index=df.index)

    if not (c_qtd and (c_cvm or (c_cnpj and cnpj_to_cd))):
        raise RuntimeError(f"VLMO: schema não reconhecido em '{member}'. Cabeçalho: {cols}\n"
                           f"Defina config.COLUMN_HINTS manualmente.")

    out = pd.DataFrame({
        "data_ref": df[c_data] if c_data else pd.NA,
        "cd_cvm": cd_cvm,
        "cnpj": df[c_cnpj] if c_cnpj else pd.NA,
        "nome": df[c_nome] if c_nome else pd.NA,
        "orgao": df[c_orgao] if c_orgao else pd.NA,
        "tipo_mov": df[c_mov] if c_mov else pd.NA,
        "operacao": df[c_oper] if c_oper else pd.NA,
        "especie": df[c_esp] if c_esp else pd.NA,
        "quantidade": _to_num(df[c_qtd]),
        "preco": _to_num(df[c_prc]) if c_prc else pd.NA,
        "volume": _to_num(df[c_vol]) if c_vol else pd.NA,
        "versao": df[c_versao] if c_versao else pd.NA,
    })
    out["fonte"] = "VLMO"

    # "Saldo Inicial/Final" são marcadores de posição, não negociações: descarta.
    mov_norm = out["tipo_mov"].map(lambda x: _norm(x) if pd.notna(x) else "")
    out = out[~mov_norm.str.contains("SALDO")]

    # filtros: watchlist, classe de órgão (insider/tesouraria), movimento real
    out = out[out["cd_cvm"].isin(cd_cvm_keep)]
    out["classe"] = out["orgao"].map(_classify_orgao)
    out = out[out["classe"].notna()]
    out = out[out["quantidade"].fillna(0) != 0]

    # direção: Tipo_Operacao (Crédito/Débito) é o sinal autoritativo; cai para o
    # tipo_mov e, por fim, para o sinal da quantidade.
    def _dir(row):
        op = _norm(row.get("operacao") if pd.notna(row.get("operacao")) else "")
        if "CREDITO" in op:
            return "compra"
        if "DEBITO" in op:
            return "venda"
        m = _norm(row["tipo_mov"])
        if re.search(r"COMPRA|AQUISI|SUBSCRI|EXERC|ENTRADA", m):
            return "compra"
        if re.search(r"VENDA|ALIENA|BAIXA|DOA(Ç|C)|SA(Í|I)DA|DESLIG", m):
            return "venda"
        return "compra" if (row["quantidade"] or 0) > 0 else "venda"

    out["direcao"] = out.apply(_dir, axis=1)
    if out["volume"].isna().all() and out["preco"].notna().any():
        out["volume"] = (out["quantidade"].abs() * out["preco"]).where(out["preco"].notna())
    return out.reset_index(drop=True)
