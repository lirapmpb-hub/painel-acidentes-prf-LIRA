"""
Camada de dados do painel (equivale ao Power Query do Power BI).

Lê as planilhas de acidentes da PRF (data/datatranAAAA.csv), corrige os tipos
das colunas e cria colunas auxiliares (mês, hora, área, trecho) usadas pelos
gráficos. O ano principal do painel é ANO_ATUAL; os outros servem para a aba
de comparação anual.
"""
from functools import lru_cache

import pandas as pd
from django.conf import settings

PASTA_DADOS = settings.BASE_DIR / "data"
ANO_ATUAL = 2026
ANOS = [2023, 2024, 2025, 2026]  # cada ano é um arquivo datatranAAAA.csv na pasta data

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sábado", "domingo"]
DIAS_CURTOS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

CLASSIFICACOES = ["Com Vítimas Fatais", "Com Vítimas Feridas", "Sem Vítimas"]
NAO_INFORMADO = "Não informado"

# Sigla: nome do estado
ESTADOS = {
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia",
    "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MG": "Minas Gerais", "MS": "Mato Grosso do Sul", "MT": "Mato Grosso",
    "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco", "PI": "Piauí", "PR": "Paraná",
    "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RO": "Rondônia", "RR": "Roraima",
    "RS": "Rio Grande do Sul", "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo",
    "TO": "Tocantins",
}

# As 30 colunas do arquivo da PRF, na ordem original (usadas no download em CSV)
COLUNAS_ORIGINAIS = [
    "id", "data_inversa", "dia_semana", "horario", "uf", "br", "km", "municipio",
    "causa_acidente", "tipo_acidente", "classificacao_acidente", "fase_dia", "sentido_via",
    "condicao_metereologica", "tipo_pista", "tracado_via", "uso_solo", "pessoas", "mortos",
    "feridos_leves", "feridos_graves", "ilesos", "ignorados", "feridos", "veiculos",
    "latitude", "longitude", "regional", "delegacia", "uop",
]
COLUNAS_TEXTO = [
    "dia_semana", "municipio", "causa_acidente", "tipo_acidente", "classificacao_acidente",
    "fase_dia", "sentido_via", "condicao_metereologica", "tipo_pista", "tracado_via",
    "uso_solo", "regional", "delegacia", "uop",
]
COLUNAS_CONTAGEM = ["pessoas", "mortos", "feridos_leves", "feridos_graves", "ilesos",
                    "ignorados", "feridos", "veiculos"]


def arquivo_do_ano(ano):
    return PASTA_DADOS / f"datatran{ano}.csv"


def ler_csv(caminho):
    """A PRF já publicou arquivos em latin-1 e em utf-8; tentamos os dois."""
    for codificacao in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(
                caminho,
                sep=";",               # as colunas são separadas por ponto e vírgula
                encoding=codificacao,  # codificação do arquivo (acentos)
                decimal=",",           # números com vírgula: -7,29 -> -7.29
                na_values=["NA"],      # "NA" significa valor vazio
                low_memory=False,
            )
        except UnicodeDecodeError:
            continue


def para_numero(coluna):
    """Aceita -7.29 ou "-7,29": alguns anos vêm com vírgula, outros com ponto."""
    if not pd.api.types.is_numeric_dtype(coluna):
        coluna = coluna.astype(str).str.replace(",", ".", regex=False)
    return pd.to_numeric(coluna, errors="coerce")


def preparar(df):
    """Corrige os tipos e cria as colunas auxiliares."""
    for coluna in ("latitude", "longitude", "km"):
        df[coluna] = para_numero(df[coluna])
    df["br"] = para_numero(df["br"]).fillna(0).astype(int)
    for coluna in COLUNAS_CONTAGEM:
        df[coluna] = para_numero(df[coluna]).fillna(0).astype(int)
    for coluna in COLUNAS_TEXTO:
        df[coluna] = df[coluna].fillna(NAO_INFORMADO).astype(str).str.strip()
    df["dia_semana"] = df["dia_semana"].str.lower()

    # A coluna se chama "data_inversa" porque a data vem como ano-mês-dia.
    df["data"] = pd.to_datetime(df["data_inversa"], errors="coerce", format="mixed")
    df = df.dropna(subset=["data"]).copy()
    df["ano"] = df["data"].dt.year
    df["mes"] = df["data"].dt.month
    df["hora"] = pd.to_numeric(df["horario"].astype(str).str[:2], errors="coerce").fillna(0).astype(int)

    # uso_solo = "Sim" quando o acidente foi em área urbana
    df["area"] = df["uso_solo"].map({"Sim": "Urbana", "Não": "Rural"}).fillna(NAO_INFORMADO)
    # Trecho: faixa de 10 km da rodovia (km 237,4 -> trecho 230, ou seja, km 230 a 240)
    df["trecho_km"] = (df["km"] // 10 * 10).fillna(-10).astype(int)
    return df


@lru_cache(maxsize=None)  # cada arquivo é lido uma vez só, enquanto o servidor roda
def _ler_ano(ano):
    df = preparar(ler_csv(arquivo_do_ano(ano)))
    return df[df["ano"] == ano]  # descarta linhas de outros anos, se houver


def carregar_ano(ano):
    """DataFrame de um ano, ou None se o arquivo não existir."""
    return _ler_ano(ano) if arquivo_do_ano(ano).exists() else None


def anos_disponiveis():
    return [ano for ano in ANOS if arquivo_do_ano(ano).exists()]


def carregar_dados():
    """Devolve o DataFrame do ano atual, com uma linha por acidente."""
    if not arquivo_do_ano(ANO_ATUAL).exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {arquivo_do_ano(ANO_ATUAL)}")
    return _ler_ano(ANO_ATUAL)
