"""
Configuração central do monitor de insiders & tesouraria (CVM).

Tudo que você normalmente ajusta está aqui: universo de empresas,
diretórios, ano de competência e filtros de órgão. Os módulos de parsing
descobrem o schema em runtime, mas se a CVM mudar nomes de coluna e a
detecção falhar, dá pra forçar o mapeamento em COLUMN_HINTS.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Diretórios
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"          # zips/csvs baixados (raw)
STATE_DIR = BASE_DIR / "state"        # estado de download + chaves já vistas
OUTPUT_DIR = BASE_DIR / "output"      # ledger.parquet + digests html
for _d in (DATA_DIR, STATE_DIR, OUTPUT_DIR):
    _d.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Fontes (Portal de Dados Abertos da CVM)
# ---------------------------------------------------------------------------
VLMO_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/VLMO/DADOS/vlmo_cia_aberta_{ano}.zip"
IPE_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{ano}.zip"
CAD_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"

ENCODING = "latin-1"
SEP = ";"

# Anos de competência a varrer. Em produção normalmente só o ano corrente;
# inclua o anterior na virada de ano para não perder informes de dezembro.
import datetime as _dt
_ANO = _dt.date.today().year
ANOS = [_ANO]

# ---------------------------------------------------------------------------
# Filtros de evento
# ---------------------------------------------------------------------------
# Órgãos cujas movimentações interessam (match por substring, case-insensitive).
# Os rótulos da CVM são "Diretor ou Vinculado", "Conselho de Administração ou
# Vinculado", "Conselho Fiscal ou Vinculado", "Controlador ou Vinculado",
# "Órgão Estatutário ou Vinculado" — os tokens abaixo casam todos eles.
ORGAOS_INSIDER = ["diretor", "conselho de administra", "conselho fiscal", "controlador", "estatut"]
# Tesouraria: a própria companhia / ações em tesouraria.
ORGAOS_TESOURARIA = ["tesouraria", "companhia", "própria"]

# Categorias/assuntos do IPE que sinalizam recompra (regex, case-insensitive).
IPE_RECOMPRA_REGEX = (
    r"recompra|aquisi[çc][aã]o de a[çc][oõ]es|negocia[çc][aã]o de a[çc][oõ]es"
    r"|a[çc][oõ]es em tesouraria|plano de recompra"
)

# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------
LEDGER_NAME = "ledger"          # ledger.parquet (fallback: ledger.csv)
WRITE_HTML_DIGEST = True

# ---------------------------------------------------------------------------
# Override de schema (deixe vazio para detecção automática)
# ---------------------------------------------------------------------------
# Ex.: COLUMN_HINTS = {"quantidade": "Quantidade", "orgao": "Tipo_Cargo"}
COLUMN_HINTS: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Universo: Ibovespa (carteira vigente mai–ago/2026, 79 papéis / 76 emissores)
# ticker -> token de razão social usado para resolver o Codigo_CVM no cadastro
# ---------------------------------------------------------------------------
IBOV = {
    "ALOS3": "ALLOS",            "ABEV3": "AMBEV",          "ASAI3": "SENDAS",
    "AURE3": "AUREN",            "AXIA3": "AXIA",           "AXIA6": "AXIA",
    "AZZA3": "AZZAS",            "B3SA3": "B3 ",            "BBSE3": "BB SEGURIDADE",
    "BBDC3": "BRADESCO",         "BBDC4": "BRADESCO",       "BRAP4": "BRADESPAR",
    "BBAS3": "BANCO DO BRASIL",  "BRKM5": "BRASKEM",        "BRAV3": "BRAVA",
    "BPAC11": "BTG PACTUAL",     "CXSE3": "CAIXA SEGURI",   "CEAB3": "C&A",
    "CMIG4": "CEMIG",            "COGN3": "COGNA",          "CSMG3": "SANEAMENTO DE MINAS",
    "CPLE3": "COPEL",            "CSAN3": "COSAN",          "CPFE3": "CPFL",
    "CMIN3": "CSN MINERA",       "CURY3": "CURY",           "CYRE3": "CYRELA",
    "DIRR3": "DIRECIONAL",       "EMBJ3": "EMBRAER",        "ENGI11": "ENERGISA",
    "ENEV3": "ENEVA",            "EGIE3": "ENGIE",          "EQTL3": "EQUATORIAL",
    "FLRY3": "FLEURY",           "GGBR4": "GERDAU S",       "GOAU4": "METALURGICA GERDAU",
    "HAPV3": "HAPVIDA",          "HYPE3": "HYPERA",         "IGTI11": "IGUATEMI",
    "ISAE4": "ISA ",             "ITSA4": "ITAUSA",         "ITUB4": "ITAU UNIBANCO",
    "KLBN11": "KLABIN",          "RENT3": "LOCALIZA",       "LREN3": "LOJAS RENNER",
    "MGLU3": "MAGAZINE LUIZA",   "POMO4": "MARCOPOLO",      "MBRF3": "MARFRIG",
    "BEEF3": "MINERVA",          "MOTV3": "MOTIVA",         "MRVE3": "MRV",
    "MULT3": "MULTIPLAN",        "NATU3": "NATURA",         "PETR3": "PETROLEO BRASILEIRO",
    "PETR4": "PETROLEO BRASILEIRO", "RECV3": "PETRORECON",  "PSSA3": "PORTO SEGURO",
    "PRIO3": "PRIO S",           "RADL3": "RAIA DROGASIL",  "RDOR3": "REDE D",
    "RAIL3": "RUMO",             "SBSP3": "SANEAMENTO BASICO", "SANB11": "SANTANDER",
    "CSNA3": "SIDERURGICA NACIONAL", "SLCE3": "SLC AGRICOLA", "SMFT3": "SMARTFIT",
    "SUZB3": "SUZANO",           "TAEE11": "TRANSMISSORA ALIANCA", "VIVT3": "TELEFONICA",
    "TIMS3": "TIM ",             "TOTS3": "TOTVS",          "UGPA3": "ULTRAPAR",
    "USIM5": "USIMINAS",         "VALE3": "VALE",           "VAMO3": "VAMOS",
    "VBBR3": "VIBRA",            "VIVA3": "VIVARA",          "WEGE3": "WEG ",
    "YDUQ3": "YDUQS",
}

# Emissores únicos (token de razão social) -> tickers, para de-dup na resolução
def emissores() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for tk, nome in IBOV.items():
        out.setdefault(nome, []).append(tk)
    return out
