"""
Aba Onde agir: onde e quando agir? Trechos priorizados pela gravidade (UPS),
mapa de calor da gravidade, janelas de risco, causas por quem pode agir,
perfil da BR e o ranking completo dos trechos (antiga aba Trechos críticos).
"""
from .. import decisao, graficos
from ..calculos import agregar, decimal, numero
from ..dados import DIAS_SEMANA
from .comum import (AJUDA, analise_do_filtro, escolher_ordem, link_ficha, montar_tabela, mostrar,
                    painel, preparar)

SECOES = [("prioridades", "Prioridades"), ("mapa", "Mapa"), ("quando", "Quando"),
          ("quem-age", "Quem age"), ("perfil", "Perfil da BR"), ("ranking", "Ranking completo")]


def linhas_de_prioridade(f, recorte, ranking, n=20):
    """Os n trechos mais graves, com a janela de risco e a causa principal de cada um."""
    top = ranking.head(n)
    detalhes = decisao.detalhes_trechos(recorte, top)
    linhas = []
    for r in top.itertuples():
        d = detalhes.get((r.uf, r.br, r.trecho_km), {})
        linhas.append({
            "posicao": r.posicao, "nome": r.nome, "local": r.local,
            "acidentes": numero(r.acidentes), "mortos": numero(r.mortos), "ups": numero(r.ups),
            "parte": decimal(r.parte_ups) + "%", "tend": r.tend,
            "janela": d.get("janela", ""), "causa": d.get("causa", ""), "grupo": d.get("grupo", ""),
            "link": link_ficha(f, r.uf, r.br, r.trecho_km),
        })
    return linhas


def perfil_da_br(f, validos):
    """Acidentes e mortos a cada 10 km da BR escolhida (só com estado e BR escolhidos)."""
    if not (f["uf"] and f["br"]):
        return None
    por_km = agregar(validos, "trecho_km")
    if not por_km.empty:
        faixas = range(0, int(por_km["trecho_km"].max()) + 10, 10)
        por_km = (por_km.set_index("trecho_km").reindex(faixas, fill_value=0)
                  .rename_axis("trecho_km").reset_index())
    return painel(f"Como a BR-{f['br']} se comporta ao longo dos quilômetros em {f['uf']}?",
                  "De 10 em 10 km · barras = acidentes · pontos vermelhos = mortos",
                  graficos.grafico_perfil(por_km))


def prioridades(request):
    f, recorte, _, _ = preparar(request)
    analise = analise_do_filtro(f, recorte)

    # Ranking completo, ordenável por acidentes, mortos ou letalidade (cabeçalho da tabela)
    validos = decisao.so_trechos(recorte)
    tabela = analise["ranking"]
    tabela_completa = None
    if not tabela.empty:
        tabela_completa = montar_tabela(
            tabela.assign(indice=tabela["mortos"] / tabela["acidentes"] * 100),
            [("nome", "Trecho"), ("local", "Município")], escolher_ordem(request, "mortos"),
            f, "prioridades", len(validos), ancora="ranking",
            link_linha=lambda t: link_ficha(f, t["uf"], t["br"], t["trecho_km"]),
        )

    # quadradinhos menores quanto mais perto o mapa chega
    if f["municipio"] or f["trecho"] is not None:
        passo, raio = 0.005, 16
    elif f["uf"]:
        passo, raio = 0.02, 14
    else:
        passo, raio = 0.1, 8
    html = graficos.para_html({
        "grafico_densidade": graficos.grafico_densidade(decisao.grade_densidade(recorte, passo), raio),
        "grafico_calor": graficos.grafico_calor(decisao.calor_ups(recorte, DIAS_SEMANA),
                                                "de gravidade (UPS)", "UPS"),
        "grafico_grupos": graficos.grafico_grupos(analise["grupos"]),
    })
    return mostrar(request, "prioridades", f, {
        "resumo": analise["resumo"], "linhas": linhas_de_prioridade(f, recorte, tabela),
        "janelas": analise["janelas"], "grupos": analise["grupos"],
        "tem_anterior": analise["anterior"] is not None, "ajuda_ups": AJUDA["ups"],
        "perfil": perfil_da_br(f, validos), "tabela": tabela_completa,
        "n_trechos": numero(len(tabela)), "n_com_morte": numero(int((tabela["mortos"] > 0).sum())),
        "secoes": SECOES, **html,
    })
