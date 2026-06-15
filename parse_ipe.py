"""
Parser do IPE (Informações Periódicas e Eventuais).

O IPE é um índice de documentos não estruturados: cada linha é um protocolo com
categoria, assunto, data de entrega e link de download. Não traz quantidade de
ações — então aqui sinalizamos o *filing* de recompra/tesouraria e devolvemos o
link; a leitura do montante é manual ou via parse posterior do PDF.

Saída (DataFrame): data_ref, data_entrega, cd_cvm, cnpj, nome, categoria,
tipo, assunto, link, versao, fonte.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

import config


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return s.upper().strip()


def _find(cols, *patterns):
    norm = {c: _norm(c).replace("_", " ") for c in cols}
    for p in patterns:
        for c, n in norm.items():
            if re.search(p, n):
                return c
    return None


def parse(csv_path, cd_cvm_keep: set[int]) -> pd.DataFrame:
    df = pd.read_csv(csv_path, sep=config.SEP, encoding=config.ENCODING, dtype=str)
    cols = list(df.columns)

    c_cvm = _find(cols, r"C(O|Ó)DIGO CVM|CD CVM")
    c_cnpj = _find(cols, r"CNPJ")
    c_nome = _find(cols, r"NOME COMPAN|DENOM")
    c_cat = _find(cols, r"CATEGORIA")
    c_tipo = _find(cols, r"TIPO")
    c_assunto = _find(cols, r"ASSUNTO")
    c_dref = _find(cols, r"DATA REFER")
    c_dent = _find(cols, r"DATA ENTREGA|DATA RECEB")
    c_link = _find(cols, r"LINK|URL|DOWNLOAD")
    c_versao = _find(cols, r"VERS")

    blob = pd.Series("", index=df.index)
    for c in (c_cat, c_tipo, c_assunto):
        if c:
            blob = blob.str.cat(df[c].fillna(""), sep=" | ")

    mask = blob.str.contains(config.IPE_RECOMPRA_REGEX, flags=re.IGNORECASE, regex=True)
    df = df[mask].copy()
    if c_cvm:
        df = df[pd.to_numeric(df[c_cvm], errors="coerce").isin(cd_cvm_keep)]

    out = pd.DataFrame({
        "data_ref": df[c_dref] if c_dref else pd.NA,
        "data_entrega": df[c_dent] if c_dent else pd.NA,
        "cd_cvm": pd.to_numeric(df[c_cvm], errors="coerce") if c_cvm else pd.NA,
        "cnpj": df[c_cnpj] if c_cnpj else pd.NA,
        "nome": df[c_nome] if c_nome else pd.NA,
        "categoria": df[c_cat] if c_cat else pd.NA,
        "tipo": df[c_tipo] if c_tipo else pd.NA,
        "assunto": df[c_assunto] if c_assunto else pd.NA,
        "link": df[c_link] if c_link else pd.NA,
        "versao": df[c_versao] if c_versao else pd.NA,
    })
    out["fonte"] = "IPE"
    return out.reset_index(drop=True)
