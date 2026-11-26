"""
Ficha do trecho: tudo de um trecho de 10 km, pronta para imprimir.
"""
import pandas as pd

from .. import decisao, graficos
from ..calculos import gravidade, numero, percentual, tabela_gravidade
from ..dados import ANO_ATUAL, DIAS_SEMANA, ESTADOS, carregar_dados
from ..filtros import link, recortar
from .comum import (AJUDA, ANO_ANTERIOR, cartoes_principais, com_tendencia, link_ficha,
                    mesmo_periodo_anterior, mostrar, preparar)


def ficha(request):
    f, recorte, _, _ = preparar(request)

    if f["trecho"] is None or not f["uf"]:
        # Sem trecho escolhido: lista os mais graves do filtro para escolher
        opcoes = [{"nome": r.nome, "local": r.local, "ups": numero(r.ups), "mortos": numero(r.mortos),
                   "acidentes": numero(r.acidentes), "link": link_ficha(f, r.uf, r.br, r.trecho_km)}
                  for r in decisao.ranking_trechos(recorte).head(15).itertuples()]
        return mostrar(request, "ficha", f, {"sem_trecho": True, "opcoes": opcoes})

    anterior = mesmo_periodo_anterior(f)
    janelas = decisao.janelas_de_risco(recorte, 6)
    grupos = decisao.tabela_grupos(recorte)

    # Posição do trecho entre todos os trechos do estado (mesmo período e gravidade)
    do_estado = recortar(carregar_dados(), {**f, "municipio": "", "br": 0, "trecho": None})[0]
    ranking_estado = decisao.ranking_trechos(do_estado)
    linha = ranking_estado[(ranking_estado["br"] == f["br"]) & (ranking_estado["trecho_km"] == f["trecho"])]
    total_trechos = numero(len(ranking_estado))
    posicao = f"{linha['posicao'].iloc[0]}º mais grave de {total_trechos} trechos" if len(linha) else ""
    municipio = linha["local"].iloc[0] if len(linha) else ESTADOS[f["uf"]]

    ups_total = int(decisao.ups(recorte).sum())
    kpis = cartoes_principais(recorte, None, "", len(f["meses_do_periodo"]), anterior)[:3]
    kpi_ups = {"titulo": "Gravidade (UPS)", "valor": numero(ups_total), "media": posicao,
               "comparacao": f"{percentual(ups_total, ranking_estado['ups'].sum())} da gravidade de {ESTADOS[f['uf']]}",
               "explicacao": "", "cor": graficos.PRETO, "ajuda": AJUDA["ups"]}
    if anterior is not None:
        com_tendencia(kpi_ups, ups_total, int(decisao.ups(anterior).sum()))
    kpis.append(kpi_ups)

    def por_mes(dados, ano):
        return (dados.groupby("mes").agg(acidentes=("id", "count"), mortos=("mortos", "sum"))
                .reindex(f["meses_do_periodo"], fill_value=0).rename_axis("mes").reset_index().assign(ano=ano))
    mensal = pd.concat([por_mes(recorte, ANO_ATUAL)] +
                       ([por_mes(anterior, ANO_ANTERIOR)] if anterior is not None else []), ignore_index=True)

    html = graficos.para_html({
        "grafico_mensal": graficos.grafico_anos(mensal, "acidentes", "acidentes"),
        "grafico_calor": graficos.grafico_calor(decisao.calor_ups(recorte, DIAS_SEMANA),
                                                "de gravidade (UPS)", "UPS"),
        "grafico_grupos": graficos.grafico_grupos(grupos),
        "grafico_tipos": graficos.grafico_condicao(tabela_gravidade(recorte, "tipo_acidente"),
                                                   gravidade(recorte), "acidentes"),
        "grafico_mapa": graficos.grafico_mapa(recorte.dropna(subset=["latitude", "longitude"])),
    })
    return mostrar(request, "ficha", f, {
        "sem_trecho": False, "vazio": recorte.empty,
        "nome_trecho": decisao.nome_trecho(f["br"], f["trecho"]), "municipio_trecho": municipio,
        "kpis": kpis, "recomendacoes": decisao.recomendacoes(recorte, anterior, ANO_ANTERIOR, janelas, grupos),
        "janelas": janelas, "grupos": grupos, "link_onde_agir": link(f, "prioridades", trecho=None),
        **html,
    })
