"""
Aba Onde agir: onde e quando agir? Trechos priorizados pela gravidade (UPS),
mapa de calor da gravidade, janelas de risco, causas por quem pode agir,
perfil da BR e o ranking completo dos trechos (antiga aba Trechos críticos).
"""
import pandas as pd

from .. import decisao, geo, graficos, mapa
from ..calculos import agregar, decimal, numero
from ..dados import DIAS_SEMANA, carregar_dados
from ..filtros import recortar
from .comum import (AJUDA, ANO_ANTERIOR, analise_do_filtro, escolher_ordem, link_ficha,
                    mesmo_periodo_anterior, montar_tabela, mostrar, painel, preparar)

SECOES = [("prioridades", "Prioridades"), ("mapa", "Mapa"), ("quando", "Quando agir"),
          ("quem-age", "Quem age"), ("trechos", "Perfil e ranking dos trechos")]


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


def tabela_por_area(tabela, nivel, ano_anterior):
    """Linhas da tabela abaixo do mapa: municípios (os 20 mais graves) ou todas as regiões."""
    ordenada = tabela[tabela["acidentes"] > 0].sort_values(["ups", "mortos"], ascending=False)
    if nivel == "municipio":
        ordenada = ordenada.head(20)
    linhas = []
    for posicao, r in enumerate(ordenada.itertuples(), start=1):
        tend = decisao.tendencia(r.ups, r.ups_ant) if pd.notna(r.ups_ant) else None
        linhas.append({
            "posicao": posicao, "nome": r.nome, "acidentes": numero(r.acidentes), "mortos": numero(r.mortos),
            "ups": numero(r.ups), "parte": decimal(r.parte_ups) + "%",
            "indice": "–" if pd.isna(r.indice) else decimal(r.indice), "tend": tend, "causa": r.causa,
        })
    return {"nivel": nivel, "titulo": geo.NOMES_NIVEIS[nivel], "linhas": linhas,
            "nota": "Os 20 municípios mais graves" if nivel == "municipio" else "Todas as regiões",
            "ano_anterior": ano_anterior}


def mapa_por_camadas(f, recorte, anterior, ranking, passo, raio):
    """Figura do mapa por camadas e as tabelas por área. None se as malhas do IBGE não estiverem em data/geo."""
    if not geo.disponivel():
        return None, []
    # Com município escolhido, as áreas mostram o estado todo (para comparar), e o mapa aproxima no município
    if f["municipio"]:
        f_area = {**f, "municipio": ""}
        recorte_area = recortar(carregar_dados(), f_area)[0]
        anterior_area = mesmo_periodo_anterior(f_area)
    else:
        f_area, recorte_area, anterior_area = f, recorte, anterior

    niveis, tabelas = {}, []
    for nivel in mapa.niveis_do_mapa(f["uf"]):
        tabela = mapa.agregar_areas(f_area, recorte_area, anterior_area, nivel)
        niveis[nivel] = (geo.malha(f["uf"] or "BR", nivel), tabela, mapa.textos_das_areas(f_area, tabela, nivel))
        tabelas.append(tabela_por_area(tabela, nivel, ANO_ANTERIOR))

    linhas, trechos = mapa.linhas_dos_trechos(ranking)
    # pontos de hover/clique só nos trechos mais graves (as linhas mostram todos); deixa a página leve
    trechos = trechos.nlargest(mapa.LIMITE_PONTOS_TRECHOS, "ups") if not trechos.empty else trechos
    if not trechos.empty:
        cores = [cor for _, _, cor in mapa.CLASSES_TRECHO]
        trechos = trechos.assign(
            cor=[cores[int(c)] for c in trechos["classe"]],
            dados=[[r.nome, r.local, numero(r.acidentes), numero(r.mortos), numero(r.ups),
                    link_ficha(f, r.uf, r.br, r.trecho_km)] for r in trechos.itertuples()])
    if not trechos.empty:
        trechos = trechos.assign(latitude=trechos["latitude"].round(4), longitude=trechos["longitude"].round(4))
    top = ranking.head(10).dropna(subset=["latitude", "longitude"])
    top = top.assign(dados=[[r.posicao, r.nome, r.local, numero(r.ups), numero(r.mortos),
                             link_ficha(f, r.uf, r.br, r.trecho_km)] for r in top.itertuples()])
    fatais = mapa.acidentes_com_morte(recorte)
    fatais = fatais.assign(
        latitude=fatais["latitude"].round(4), longitude=fatais["longitude"].round(4),
        local=fatais["municipio"].str.title() + " - " + fatais["uf"],
        rodovia="BR-" + fatais["br"].astype(str) + ", km " + fatais["km"].map(lambda k: f"{k:g}".replace(".", ",")))

    # Enquadramento: o município escolhido, senão o estado (ou o Brasil)
    malha_vista = geo.malha(f["uf"] or "BR", mapa.niveis_do_mapa(f["uf"])[0])
    if f["municipio"]:
        codigo = geo.codigo_do_municipio(f["uf"], f["municipio"])
        so_ele = [x for x in malha_vista["features"] if x["properties"]["codarea"] == codigo]
        if so_ele:
            malha_vista = {"features": so_ele}
    figura = graficos.grafico_mapa_camadas(
        niveis, mapa.niveis_do_mapa(f["uf"])[0], mapa.METRICAS, linhas, trechos, top, fatais,
        decisao.grade_densidade(recorte, passo), raio, geo.limites(malha_vista))
    return graficos.html_de(figura), tabelas


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
        passo, raio = 0.2, 8
    html = graficos.para_html({
        "grafico_calor": graficos.grafico_calor(decisao.calor_ups(recorte, DIAS_SEMANA),
                                                "de gravidade (UPS)", "UPS"),
        "grafico_grupos": graficos.grafico_grupos(analise["grupos"]),
    })
    html["grafico_mapa"], tabelas_areas = mapa_por_camadas(f, recorte, analise["anterior"], tabela, passo, raio)
    if html["grafico_mapa"] is None:  # sem as malhas do IBGE: só a mancha de calor, como antes
        html["grafico_mapa"] = graficos.html_de(
            graficos.grafico_densidade(decisao.grade_densidade(recorte, passo), raio))
    return mostrar(request, "prioridades", f, {
        "tabelas_areas": tabelas_areas, "niveis_mapa": [(t["nivel"], t["titulo"]) for t in tabelas_areas],
        "metricas_mapa": [(chave, rotulo) for chave, (_, _, rotulo) in mapa.METRICAS.items()],
        "resumo": analise["resumo"], "linhas": linhas_de_prioridade(f, recorte, tabela),
        "janelas": analise["janelas"], "grupos": analise["grupos"],
        "tem_anterior": analise["anterior"] is not None, "ajuda_ups": AJUDA["ups"],
        "perfil": perfil_da_br(f, validos), "tabela": tabela_completa,
        "n_trechos": numero(len(tabela)), "n_com_morte": numero(int((tabela["mortos"] > 0).sum())),
        "secoes": SECOES, **html,
    })
