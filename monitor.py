"""
Orquestrador.

  python monitor.py            produção: fetch -> parse -> delta -> ledger -> digest
  python monitor.py --demo     prévia offline (dados sintéticos)

Funções reutilizadas pelo dashboard: demo_events(), collect().
"""

from __future__ import annotations

import argparse, datetime as dt, hashlib, json, zipfile
import pandas as pd
import config, report

SEEN = config.STATE_DIR / "seen_keys.json"


def write_ledger(df):
    pq = config.OUTPUT_DIR / f"{config.LEDGER_NAME}.parquet"
    try:
        existing = pd.read_parquet(pq) if pq.exists() else pd.DataFrame()
        pd.concat([existing, df], ignore_index=True).to_parquet(pq, index=False)
        return str(pq)
    except Exception as e:
        cv = config.OUTPUT_DIR / f"{config.LEDGER_NAME}.csv"
        df.to_csv(cv, mode="a", header=not cv.exists(), index=False, encoding="utf-8")
        print(f"[ledger] parquet indisponível ({type(e).__name__}); gravado em {cv.name}")
        return str(cv)


def _key(row):
    parts = [str(row.get(k, "")) for k in
             ("fonte","cd_cvm","data_ref","data_entrega","orgao","direcao","quantidade","especie","assunto","link")]
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def compute_delta(df):
    if df.empty: return df
    seen = set(json.loads(SEEN.read_text())) if SEEN.exists() else set()
    df = df.assign(_k=df.apply(lambda r: _key(r.to_dict()), axis=1))
    new = df[~df["_k"].isin(seen)].copy()
    SEEN.write_text(json.dumps(sorted(seen | set(df["_k"]))))
    return new.drop(columns="_k")


def collect():
    """Pipeline de produção -> (vlmo, ipe, delta, n_emis)."""
    import resolver
    from fetch import download
    import parse_vlmo, parse_ipe
    mp = resolver.resolve(); keep = resolver.cd_cvm_set(mp)
    cd2tk = resolver.cd_to_tickers(mp)
    tk_of = lambda cd: (cd2tk.get(int(cd), ["—"])[0] if pd.notna(cd) else "—")
    vlmo_all, ipe_all = [], []
    for ano in config.ANOS:
        vz = download(config.VLMO_URL.format(ano=ano), config.DATA_DIR / f"vlmo_{ano}.zip")
        try: vlmo_all.append(parse_vlmo.parse(vz, keep))
        except zipfile.BadZipFile: print(f"[vlmo] {ano}: indisponível")
        ic = download(config.IPE_URL.format(ano=ano), config.DATA_DIR / f"ipe_{ano}.csv")
        ipe_all.append(parse_ipe.parse(ic, keep))
    vlmo = pd.concat(vlmo_all, ignore_index=True) if vlmo_all else pd.DataFrame()
    ipe = pd.concat(ipe_all, ignore_index=True) if ipe_all else pd.DataFrame()
    for df in (vlmo, ipe):
        if not df.empty: df["ticker"] = df["cd_cvm"].map(tk_of)
    delta = compute_delta(pd.concat([vlmo, ipe], ignore_index=True))
    if not delta.empty:
        delta = delta.assign(detected_at=dt.datetime.now().isoformat(timespec="seconds"))
        write_ledger(delta)
    return vlmo, ipe, delta, len(set(keep))


def demo_events():
    """Eventos sintéticos -> (vlmo, ipe). Compartilhado com o dashboard."""
    import random; random.seed(7)
    orgs = ["Diretoria", "Conselho de Administração", "Controlador"]
    picks = ["VALE3","PETR4","ITUB4","WEGE3","EQTL3","PRIO3","SBSP3","CSMG3","RDOR3","EMBJ3","SUZB3","RENT3","BBAS3","CPLE3"]
    rows = []
    for tk in picks:
        for _ in range(random.randint(1, 3)):
            d = random.choice(["compra","compra","venda"]); q = random.randint(8000, 1200000); p = round(random.uniform(8, 75), 2)
            rows.append(dict(data_ref=f"2026-05-{random.randint(2,28):02d}", cd_cvm=0, cnpj="", nome=tk,
                orgao=random.choice(orgs), tipo_mov=d.title(), especie="ON", quantidade=q, preco=p, volume=q*p,
                versao="1", fonte="VLMO", classe="insider", direcao=d, ticker=tk))
    for tk in ["WEGE3","ITUB4"]:
        q = random.randint(200000, 2000000); p = round(random.uniform(20, 60), 2)
        rows.append(dict(data_ref="2026-05-20", cd_cvm=0, cnpj="", nome=tk, orgao="Companhia (tesouraria)",
            tipo_mov="Compra", especie="ON", quantidade=q, preco=p, volume=q*p, versao="1",
            fonte="VLMO", classe="tesouraria", direcao="compra", ticker=tk))
    vlmo = pd.DataFrame(rows)
    ipe = pd.DataFrame([
        dict(data_ref="2026-05-22", data_entrega="2026-05-22", cd_cvm=0, cnpj="", nome="PETR4",
            categoria="Comunicado ao Mercado", tipo="Negociação de Ações",
            assunto="Aprovação de programa de recompra de até 80 mi de ações", link="https://www.rad.cvm.gov.br/",
            versao="1", fonte="IPE", ticker="PETR4"),
        dict(data_ref="2026-05-19", data_entrega="2026-05-19", cd_cvm=0, cnpj="", nome="RADL3",
            categoria="Fato Relevante", tipo="Recompra", assunto="Cancelamento de ações em tesouraria",
            link="https://www.rad.cvm.gov.br/", versao="1", fonte="IPE", ticker="RADL3"),
    ])
    return vlmo, ipe


def _emit(vlmo, ipe, delta, mode, n_emis):
    now = dt.datetime.now()
    meta = dict(universo="Ibovespa (76 emissores)", competencia="mai/2026", n_emissores=n_emis,
                gerado=now.strftime("%d/%m/%Y %H:%M"), mode=mode)
    out = config.OUTPUT_DIR / ("relatorio_preview.html" if "prév" in mode else f"digest_{now:%Y%m%d_%H%M}.html")
    out.write_text(report.build_html(vlmo, ipe, meta), encoding="utf-8")
    print(f"[digest] {out}  ({len(delta)} eventos no delta)")


def run():
    vlmo, ipe, delta, n = collect()
    _emit(vlmo, ipe, delta, "produção", n)


def demo():
    vlmo, ipe = demo_events()
    _emit(vlmo, ipe, pd.concat([vlmo, ipe], ignore_index=True), "prévia · dados de exemplo", 76)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--demo", action="store_true")
    demo() if ap.parse_args().demo else run()
