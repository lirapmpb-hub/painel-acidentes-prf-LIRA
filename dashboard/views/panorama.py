"""
Aba Panorama: qual é a situação? Resumo, totais, evolução, mapa, horários,
tipos de acidente e rodovias.
"""
import pandas as pd

from .. import graficos
from ..calculos import candidatos, gravidade, numero, tabela_gravidade
from ..dados import DIAS_SEMANA
from .comum import analise_do_filtro, cartoes_principais, mostrar, preparar

# Acima deste número de pontos o mapa fica pesado; aí mostramos só os
# acidentes com vítimas fatais.
LIMITE_PONTOS_MAPA = 8000

SECOES = [("evolucao", "Evolução"), ("mapa", "Mapa"), ("quando", "Dia e hora"),
          ("tipos", "Tipos"), ("rodovias", "Rodovias")]


def pontos_do_mapa(recorte):
    """Pontos dos acidentes (só os fatais, se forem pontos demais) e o aviso do mapa."""
    pontos = recorte.dropna(subset=["latitude", "longitude"])
    if len(pontos) <= LIMITE_PONTOS_MAPA:
        return pontos, "Cada ponto é um acidente"
    fatais = pontos[pontos["classificacao_acidente"] == "Com Vítimas Fatais"]
    if not fatais.empty:
        return fatais, "Mostrando só os acidentes com vítimas fatais; escolha um estado para ver todos"
    return (pontos.sample(LIMITE_PONTOS_MAPA, random_state=0),
            f"Amostra de {numero(LIMITE_PONTOS_MAPA)} acidentes; escolha um estado para ver todos")


def index(request):
    f, recorte, comparacao, nome_comparacao = preparar(request)
    analise = analise_do_filtro(f, recorte)
    kpis = cartoes_principais(recorte, comparacao, nome_comparacao, len(f["meses_do_periodo"]),
                              analise["anterior"])

    # Linha: acidentes e mortos por mês (meses sem acidente contam zero)
    tabela_linha = (
        recorte.groupby("mes").agg(acidentes=("id", "count"), mortos=("mortos", "sum"))
        .reindex(f["meses_do_periodo"], fill_value=0).rename_axis("mes").reset_index()
    )
    pontos, aviso_mapa = pontos_do_mapa(recorte)

    # Mapa de calor: dia da semana x hora (tabela cruzada, como no Excel)
    tabela_calor = pd.crosstab(recorte["dia_semana"], recorte["hora"]).reindex(
        index=DIAS_SEMANA, columns=range(24), fill_value=0)

    # Mapa de árvore: tipos de acidente (os 10 maiores e "Outros"), com os mortos de cada um
    tipos = (recorte.groupby("tipo_acidente").agg(acidentes=("id", "count"), mortos=("mortos", "sum"))
             .sort_values("acidentes", ascending=False))
    tabela_tipos = tipos.head(10).rename_axis("rotulo").reset_index()
    if len(tipos) > 10:
        tabela_tipos.loc[len(tabela_tipos)] = ["Outros", tipos["acidentes"].iloc[10:].sum(),
                                               tipos["mortos"].iloc[10:].sum()]

    # Ranking de rodovias (ou de municípios, se uma BR foi escolhida)
    if f["br"] and not f["municipio"]:
        titulo_ranking = f"Quais municípios da BR-{f['br']} concentram acidentes e mortes?"
        recorte_ranking = recorte.assign(nome=recorte["municipio"].str.title() + " - " + recorte["uf"])
    else:
        titulo_ranking = "Quais rodovias concentram acidentes e mortes?"
        nomes = ("BR-" + recorte["br"].astype(str)).where(recorte["br"] > 0, "Rodovia não informada")
        recorte_ranking = recorte.assign(nome=nomes)
    medida = "mortos" if recorte["mortos"].sum() > 0 else "acidentes"
    tabela_ranking = candidatos(tabela_gravidade(recorte_ranking, "nome"), 10)

    html = graficos.para_html({
        "grafico_linha": graficos.grafico_linha(tabela_linha),
        "grafico_classificacao": graficos.grafico_classificacao(recorte["classificacao_acidente"].value_counts()),
        "grafico_mapa": graficos.grafico_mapa(pontos),
        "grafico_calor": graficos.grafico_calor(tabela_calor),
        "grafico_tipos": graficos.grafico_arvore(tabela_tipos),
        "grafico_ranking": graficos.grafico_condicao(tabela_ranking, gravidade(recorte), medida, limite=10),
    })
    return mostrar(request, "index", f, {
        "kpis": kpis, "aviso_mapa": aviso_mapa, "titulo_ranking": titulo_ranking,
        "resumo": analise["resumo"], "secoes": SECOES, **html,
    })
