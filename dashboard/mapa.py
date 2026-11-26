"""
Mapa por camadas da aba Onde agir: áreas coloridas (municípios ou regiões do
IBGE), rodovias coloridas por trecho, trechos prioritários numerados, acidentes
com morte e mancha de calor. Aqui ficam os cálculos; o desenho está em graficos.py.
"""
import numpy as np
import pandas as pd

from . import decisao, geo
from .calculos import MINIMO_PARA_INDICE, decimal, numero
from .dados import ESTADOS
from .filtros import link

# Indicadores que colorem as áreas: chave -> (título da escala de cor, tipo da escala, rótulo do botão)
METRICAS = {
    "ups": ("Gravidade (UPS)", "contagem", "Gravidade"),
    "mortos": ("Mortos", "contagem", "Mortos"),
    "acidentes": ("Acidentes", "contagem", "Acidentes"),
    "indice": ("Mortos a cada 100 acidentes", "contagem", "Letalidade"),
    "variacao": ("Variação da gravidade (%)", "divergente", "Variação"),
}
MINIMO_VARIACAO = decisao.MINIMO_TENDENCIA  # abaixo disto (em UPS) a variação é ruído
CLASSES_TRECHO = [
    # (nome, fatia dos trechos mais graves, cor)
    ("Gravidade muito alta (5% mais graves)", 0.05, "#7a030a"),
    ("Gravidade alta (5% a 15%)", 0.15, "#e30613"),
    ("Gravidade média (15% a 40%)", 0.40, "#f0767c"),
    ("Gravidade baixa", 1.00, "#9d9d9d"),
]
LIMITE_FATAIS = 2000           # pontos de acidentes com morte (os mais recentes)
LIMITE_PONTOS_TRECHOS = 400    # trechos com ponto de hover/clique (os mais graves)


def niveis_do_mapa(uf):
    """Brasil inteiro: por estado. Com estado escolhido: município e regiões do IBGE."""
    return ["estado"] if not uf else ["municipio", "imediata", "intermediaria"]


def codigos_de_municipio(df):
    """Código IBGE do município de cada acidente (None se o nome não for encontrado)."""
    pares = {(u, m) for u, m in zip(df["uf"], df["municipio"])}
    tabela = {par: geo.codigo_do_municipio(*par) for par in pares}
    return pd.Series([tabela[(u, m)] for u, m in zip(df["uf"], df["municipio"])], index=df.index, dtype=object)


def area_de_cada_acidente(df, nivel):
    if nivel == "estado":
        codigo_da_sigla = {sigla: codigo for codigo, sigla in geo.estados().items()}
        return df["uf"].map(codigo_da_sigla)
    codigos = codigos_de_municipio(df)
    if nivel == "municipio":
        return codigos
    municipios = geo.municipios()
    return codigos.map(lambda c: municipios[c][nivel] if c in municipios else None)


def nomes_das_areas(nivel):
    if nivel == "estado":
        return {codigo: ESTADOS[sigla] for codigo, sigla in geo.estados().items()}
    if nivel == "municipio":
        return {codigo: m["nome"] for codigo, m in geo.municipios().items()}
    return {m[nivel]: m[f"nome_{nivel}"] for m in geo.municipios().values()}


def agregar_areas(f, recorte, anterior, nivel):
    """Uma linha por área da malha (inclusive as sem acidentes), com as medidas e a causa principal."""
    malha = geo.malha(f["uf"] or "BR", nivel)
    codigos = [feature["properties"]["codarea"] for feature in malha["features"]]
    nomes = nomes_das_areas(nivel)

    colunas = ["id", "uf", "municipio", "mortos", "feridos_graves", "classificacao_acidente",
               "tipo_acidente", "causa_acidente"]
    d = decisao.com_ups(recorte[colunas])
    d["area"] = area_de_cada_acidente(recorte, nivel)
    d = d.dropna(subset=["area"])
    tabela = d.groupby("area").agg(**decisao.MEDIDAS).reindex(codigos).fillna(0)

    # causa com mais gravidade em cada área
    if len(d):
        causa = (d.groupby(["area", "causa_acidente"])["ups"].sum().reset_index()
                 .sort_values("ups", ascending=False).drop_duplicates("area").set_index("area")["causa_acidente"])
        tabela["causa"] = causa.reindex(codigos).fillna("")
        # nome usado pela PRF (para o clique no município filtrar o painel)
        tabela["nome_prf"] = d.groupby("area")["municipio"].agg(lambda s: s.mode().iat[0]).reindex(codigos).fillna("")
    else:
        tabela["causa"], tabela["nome_prf"] = "", ""

    if anterior is not None and len(anterior):
        a = decisao.com_ups(anterior[["uf", "municipio", "classificacao_acidente", "tipo_acidente"]])
        a["area"] = area_de_cada_acidente(anterior, nivel)
        tabela["ups_ant"] = a.groupby("area")["ups"].sum().reindex(codigos).fillna(0)
    else:
        tabela["ups_ant"] = np.nan

    tabela["indice"] = np.where(tabela["acidentes"] >= MINIMO_PARA_INDICE,
                                tabela["mortos"] / tabela["acidentes"].where(tabela["acidentes"] > 0) * 100, np.nan)
    confiavel = (tabela[["ups", "ups_ant"]].max(axis=1) >= MINIMO_VARIACAO) & (tabela["ups_ant"] > 0)
    # valor real para o texto; a cor usa o valor limitado a ±100% (senão uma área estoura a escala)
    tabela["variacao_real"] = np.where(confiavel, (tabela["ups"] - tabela["ups_ant"]) / tabela["ups_ant"] * 100, np.nan)
    tabela["variacao"] = tabela["variacao_real"].clip(-100, 100)
    tabela["nome"] = [nomes.get(c, c) for c in codigos]
    tabela["parte_ups"] = tabela["ups"] / tabela["ups"].sum() * 100 if tabela["ups"].sum() else 0
    return tabela.rename_axis("codarea").reset_index()


def textos_das_areas(f, tabela, nivel):
    """Textos prontos para o hover e o link do clique (só municípios filtram o painel)."""
    def var(v):
        return "poucos casos" if pd.isna(v) else ("+" if v > 0 else "") + decimal(v) + "%"
    linhas = []
    for r in tabela.itertuples():
        url = ""
        if nivel == "municipio" and r.nome_prf:
            url = link(f, "prioridades", municipio=r.nome_prf, br=None, trecho=None) + "#mapa"
        elif nivel == "estado":
            url = link(f, "prioridades", uf=geo.estados().get(r.codarea), municipio=None, br=None, trecho=None) + "#mapa"
        linhas.append([r.nome, numero(r.acidentes), numero(r.mortos), numero(r.ups),
                       "poucos casos" if pd.isna(r.indice) else decimal(r.indice), var(r.variacao_real),
                       r.causa or "–", url])
    return linhas


def linhas_dos_trechos(ranking):
    """
    Rodovias desenhadas trecho a trecho (10 km), coloridas pela gravidade.
    Cada trecho vai do meio do caminho com o trecho anterior até o meio do
    caminho com o seguinte, passando pelo centro dos seus acidentes.
    """
    t = ranking.dropna(subset=["latitude", "longitude"])
    t = t[t["ups"] > 0]
    if t.empty:
        return [], t
    ordem = t["ups"].rank(ascending=False, method="first") / len(t)
    t = t.assign(classe=pd.cut(ordem, [0] + [c[1] for c in CLASSES_TRECHO], labels=False, include_lowest=True))
    posicao = {(r.uf, r.br, r.trecho_km): (r.latitude, r.longitude) for r in t.itertuples()}

    camadas = [{"nome": nome, "cor": cor, "lat": [], "lon": []} for nome, _, cor in CLASSES_TRECHO]
    for r in t.itertuples():
        centro = (r.latitude, r.longitude)
        pontos = []
        anterior = posicao.get((r.uf, r.br, r.trecho_km - 10))
        seguinte = posicao.get((r.uf, r.br, r.trecho_km + 10))
        if anterior:
            pontos.append(((anterior[0] + centro[0]) / 2, (anterior[1] + centro[1]) / 2))
        pontos.append(centro)
        if seguinte:
            pontos.append(((seguinte[0] + centro[0]) / 2, (seguinte[1] + centro[1]) / 2))
        if len(pontos) == 1:  # trecho isolado: um tracinho curto para aparecer
            pontos = [(centro[0] - 0.01, centro[1]), (centro[0] + 0.01, centro[1])]
        camada = camadas[int(r.classe)]
        camada["lat"] += [round(p[0], 4) for p in pontos] + [None]
        camada["lon"] += [round(p[1], 4) for p in pontos] + [None]
    return camadas, t


def acidentes_com_morte(recorte):
    fatais = recorte[recorte["classificacao_acidente"] == "Com Vítimas Fatais"].dropna(subset=["latitude", "longitude"])
    return fatais.sort_values("data", ascending=False).head(LIMITE_FATAIS)
