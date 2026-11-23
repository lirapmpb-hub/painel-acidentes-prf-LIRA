"""
Camada de lógica do painel (equivale às medidas DAX do Power BI).

Cada função abaixo é uma aba do painel. Todas começam do mesmo jeito: leem
os filtros da URL e recortam os acidentes (ver filtros.py). Depois calculam
as tabelas e os gráficos daquela aba.
"""
import pandas as pd
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.text import slugify

from . import graficos
from .calculos import (FAIXAS_VEICULOS, MINIMO_PARA_INDICE, agregar, decimal, faixa_veiculos,
                       gravidade, media_mensal, numero, percentual, sem_desconhecidos,
                       separar_valores, tabela_gravidade, variacao, vazio_como_zero)
from .dados import (ANO_ATUAL, COLUNAS_ORIGINAIS, DIAS_SEMANA, MESES, anos_disponiveis,
                    carregar_ano, carregar_dados)
from .filtros import ler_filtros, link, recortar

# Acima deste número de pontos o mapa fica pesado; aí mostramos só os
# acidentes com vítimas fatais.
LIMITE_PONTOS_MAPA = 8000

# Abas do painel: (nome da rota em urls.py, título no menu)
ABAS = [
    ("index", "Visão geral"),
    ("condicoes", "Condições"),
    ("trechos", "Trechos críticos"),
    ("vitimas", "Vítimas"),
    ("estrutura", "Estrutura PRF"),
    ("anos", "Comparação anual"),
]


# =============================================================================
# Peças comuns a todas as abas
# =============================================================================
def preparar(request):
    """Lê os filtros e recorta os acidentes do ano atual."""
    df = carregar_dados()
    f = ler_filtros(request, df)
    recorte, comparacao, nome_comparacao = recortar(df, f)
    return f, recorte, comparacao, nome_comparacao


def mostrar(request, aba, f, contexto):
    """Junta os filtros, o menu de abas e o conteúdo da aba, e desenha a página."""
    contexto = {
        **f,
        **contexto,
        "aba": aba,
        "abas": [{"titulo": titulo, "url": link(f, nome), "ativa": nome == aba} for nome, titulo in ABAS],
        "plotly_js": graficos.PLOTLY_JS,
        "link_exportar": link(f, "exportar"),
        "link_sem_trecho": link(f, aba, trecho=None),
        "link_limpar": reverse(aba),
        "ano_atual": ANO_ATUAL,
    }
    return render(request, f"dashboard/{aba}.html", contexto)


def painel(titulo, subtitulo, figura):
    """Um quadro branco com título, subtítulo e gráfico (ver _painel.html)."""
    return {"titulo": titulo, "subtitulo": subtitulo, "html": graficos.html_de(figura)}


def escolher_ordem(request, padrao):
    """Coluna usada para ordenar as tabelas, escolhida clicando no cabeçalho."""
    ordem = request.GET.get("ordem", padrao)
    return ordem if ordem in ("acidentes", "mortos", "indice") else padrao


def montar_tabela(tabela, colunas_texto, ordem, f, aba, total, link_linha=None, limite=20):
    """
    Prepara uma tabela para o _tabela.html. colunas_texto = [(coluna, título)]
    das primeiras colunas; as demais são sempre as medidas de acidentes.
    """
    if ordem == "indice":
        tabela = tabela[tabela["acidentes"] >= MINIMO_PARA_INDICE]
    tabela = tabela.sort_values([ordem, "acidentes"], ascending=False).head(limite)

    def cabecalho(titulo, chave=None):
        if not chave:
            return {"titulo": titulo}
        return {"titulo": titulo, "link": link(f, aba, ordem=chave), "ativa": chave == ordem}

    colunas = [cabecalho(titulo) for _, titulo in colunas_texto] + [
        cabecalho("Acidentes", "acidentes"), cabecalho("% do total"),
        cabecalho("Mortos", "mortos"), cabecalho("Feridos graves"),
        cabecalho("Mortos/100 acid.", "indice"),
    ]
    linhas = []
    for linha in tabela.to_dict("records"):
        linhas.append({
            "celulas": [linha[c] for c, _ in colunas_texto] + [
                numero(linha["acidentes"]), percentual(linha["acidentes"], total),
                numero(linha["mortos"]), numero(linha["feridos_graves"]), decimal(linha["indice"]),
            ],
            "link": link_linha(linha) if link_linha else "",
        })
    return {"colunas": colunas, "linhas": linhas, "texto": len(colunas_texto),
            "nota_indice": ordem == "indice"}


def cartoes_principais(recorte, comparacao, nome_comparacao, n_meses):
    """Os quatro cartões do topo: acidentes, mortos, feridos graves e índice."""
    def cartao(titulo, total, total_acima, explicacao, cor=graficos.PRETO):
        kpi = {"titulo": titulo, "valor": numero(total),
               "media": f"Média de {media_mensal(total, n_meses)} por mês",
               "comparacao": "", "explicacao": explicacao, "cor": cor}
        if comparacao is not None:
            kpi["comparacao"] = f"{percentual(total, total_acima)} do total {nome_comparacao}"
        return kpi

    acima = comparacao if comparacao is not None else recorte
    kpis = [
        cartao("Acidentes", len(recorte), len(acima), "Acidentes registrados pela PRF"),
        cartao("Mortos", recorte["mortos"].sum(), acima["mortos"].sum(),
               "Pessoas mortas nos acidentes", cor=graficos.VERMELHO),
        cartao("Feridos graves", recorte["feridos_graves"].sum(), acima["feridos_graves"].sum(),
               f"Mais {numero(recorte['feridos_leves'].sum())} feridos leves", cor=graficos.VERMELHO_MEDIO),
    ]
    indice = {"titulo": "Índice de gravidade", "valor": decimal(gravidade(recorte)),
              "media": "Mortos a cada 100 acidentes", "comparacao": "",
              "explicacao": "Quanto maior, mais letais os acidentes", "cor": graficos.CINZA_ESCURO}
    if comparacao is not None:
        indice["comparacao"] = f"Média {nome_comparacao}: {decimal(gravidade(comparacao))}"
    kpis.append(indice)
    return kpis


# =============================================================================
# Aba 1 - Visão geral
# =============================================================================
def index(request):
    f, recorte, comparacao, nome_comparacao = preparar(request)
    kpis = cartoes_principais(recorte, comparacao, nome_comparacao, len(f["meses_do_periodo"]))

    # Linha: acidentes e mortos por mês (meses sem acidente contam zero)
    tabela_linha = (
        recorte.groupby("mes").agg(acidentes=("id", "count"), mortos=("mortos", "sum"))
        .reindex(f["meses_do_periodo"], fill_value=0).rename_axis("mes").reset_index()
    )

    # Rosca: acidentes por gravidade
    por_classificacao = recorte["classificacao_acidente"].value_counts()

    # Mapa: pontos dos acidentes (só os fatais, se forem pontos demais)
    pontos = recorte.dropna(subset=["latitude", "longitude"])
    aviso_mapa = "Cada ponto é um acidente"
    if len(pontos) > LIMITE_PONTOS_MAPA:
        fatais = pontos[pontos["classificacao_acidente"] == "Com Vítimas Fatais"]
        if not fatais.empty:
            pontos = fatais
            aviso_mapa = ("Mostrando só os acidentes com vítimas fatais; "
                          "escolha um estado para ver todos")
        else:
            pontos = pontos.sample(LIMITE_PONTOS_MAPA, random_state=0)
            aviso_mapa = f"Amostra de {numero(LIMITE_PONTOS_MAPA)} acidentes; escolha um estado para ver todos"

    # Mapa de calor: dia da semana x hora (tabela cruzada, como no Excel)
    tabela_calor = pd.crosstab(recorte["dia_semana"], recorte["hora"]).reindex(
        index=DIAS_SEMANA, columns=range(24), fill_value=0)

    # Mapa de árvore: tipos de acidente (os 10 maiores e "Outros")
    tipos = recorte["tipo_acidente"].value_counts()
    tabela_tipos = tipos.head(10).rename_axis("rotulo").reset_index(name="acidentes")
    if tipos.iloc[10:].sum() > 0:
        tabela_tipos.loc[len(tabela_tipos)] = ["Outros", tipos.iloc[10:].sum()]

    # Barras 1: as 10 causas mais frequentes
    tabela_causas = (recorte["causa_acidente"].value_counts().head(10)
                     .rename_axis("causa").reset_index(name="acidentes"))

    # Barras 2: ranking de rodovias (ou de municípios, se uma BR foi escolhida)
    if f["br"] and not f["municipio"]:
        titulo_ranking = f"Municípios da BR-{f['br']}"
        recorte_ranking = recorte.assign(nome=recorte["municipio"].str.title() + " - " + recorte["uf"])
    else:
        titulo_ranking = "Rodovias federais"
        nomes = ("BR-" + recorte["br"].astype(str)).where(recorte["br"] > 0, "Rodovia não informada")
        recorte_ranking = recorte.assign(nome=nomes)
    medida = "mortos" if recorte["mortos"].sum() > 0 else "acidentes"
    tabela_ranking = (
        recorte_ranking.groupby("nome").agg(acidentes=("id", "count"), mortos=("mortos", "sum"))
        .sort_values([medida, "acidentes"], ascending=False).head(10).reset_index()
    )
    titulo_ranking += " com mais mortos" if medida == "mortos" else " com mais acidentes"

    html = graficos.para_html({
        "grafico_linha": graficos.grafico_linha(tabela_linha),
        "grafico_classificacao": graficos.grafico_classificacao(por_classificacao),
        "grafico_mapa": graficos.grafico_mapa(pontos),
        "grafico_calor": graficos.grafico_calor(tabela_calor),
        "grafico_tipos": graficos.grafico_arvore(tabela_tipos),
        "grafico_causas": graficos.grafico_barras(tabela_causas, "causa", "acidentes", "acidentes"),
        "grafico_ranking": graficos.grafico_barras(
            tabela_ranking, "nome", medida, medida,
            cor=graficos.VERMELHO if medida == "mortos" else graficos.GRAFITE),
    })
    return mostrar(request, "index", f, {
        "kpis": kpis, "aviso_mapa": aviso_mapa, "titulo_ranking": titulo_ranking, **html,
    })


# =============================================================================
# Aba 2 - Condições da via e do ambiente
# =============================================================================
DIMENSOES = [
    # (coluna, título, explicação)
    ("fase_dia", "Fase do dia", "Luz natural no momento do acidente"),
    ("condicao_metereologica", "Condição do tempo", "Clima registrado pela PRF"),
    ("tipo_pista", "Tipo de pista", "Simples (mão dupla), dupla ou múltipla"),
    ("area", "Área", "Urbana ou rural (campo uso_solo da PRF)"),
    ("tracado_via", "Traçado da via",
     "Um acidente pode ter mais de um traçado (ex.: curva em declive) e conta em cada um"),
    ("sentido_via", "Sentido da via", "Crescente ou decrescente em relação à quilometragem"),
]


def condicoes(request):
    f, recorte, _, _ = preparar(request)
    media = gravidade(recorte)

    paineis, destaques = [], []
    for coluna, titulo, subtitulo in DIMENSOES:
        dados_coluna = separar_valores(recorte, coluna) if coluna == "tracado_via" else recorte
        tabela = tabela_gravidade(dados_coluna, coluna)
        paineis.append(painel(titulo, subtitulo, graficos.grafico_condicao(tabela, media)))

        # Destaque: a categoria mais letal (com acidentes suficientes para confiar)
        confiaveis = sem_desconhecidos(tabela[tabela["acidentes"] >= MINIMO_PARA_INDICE])
        if media > 0 and not confiaveis.empty:
            pior = confiaveis.loc[confiaveis["indice"].idxmax()]
            destaques.append({
                "titulo": titulo, "valor": pior["rotulo"],
                "texto": f"{decimal(pior['indice'])} mortos a cada 100 acidentes",
                "detalhe": f"{decimal(pior['indice'] / media)} vezes a média · {numero(pior['acidentes'])} acidentes",
            })

    causas = tabela_gravidade(recorte, "causa_acidente")
    causas = causas[causas["acidentes"] >= MINIMO_PARA_INDICE].nlargest(10, "indice")
    painel_causas = painel(
        "Causas mais letais",
        f"As 10 causas com mais mortos a cada 100 acidentes (mínimo de {MINIMO_PARA_INDICE} acidentes)",
        graficos.grafico_condicao(causas, media, ordem="indice"),
    )
    return mostrar(request, "condicoes", f, {
        "media": decimal(media), "destaques": destaques, "paineis": paineis,
        "painel_causas": painel_causas, "minimo": MINIMO_PARA_INDICE,
    })


# =============================================================================
# Aba 3 - Trechos críticos (rodovia + faixa de 10 km)
# =============================================================================
def trechos(request):
    f, recorte, _, _ = preparar(request)
    ordem = escolher_ordem(request, "mortos")

    validos = recorte[(recorte["br"] > 0) & (recorte["trecho_km"] >= 0)]
    chave = ["uf", "br", "trecho_km"]
    posicao = validos.groupby(chave)[["latitude", "longitude"]].median().reset_index()
    # município onde o trecho tem mais acidentes (um trecho pode cruzar dois)
    principal = (validos.groupby(chave + ["municipio"]).size().reset_index(name="n")
                 .sort_values("n", ascending=False).drop_duplicates(chave)[chave + ["municipio"]])
    tabela = (agregar(validos, chave)
              .merge(posicao, on=chave, how="left").merge(principal, on=chave, how="left"))
    tabela["nome"] = ("BR-" + tabela["br"].astype(str) + " · km " + tabela["trecho_km"].astype(str)
                      + " a " + (tabela["trecho_km"] + 10).astype(str))
    tabela["local"] = tabela["municipio"].str.title() + " - " + tabela["uf"]

    # Resumo: quanto das mortes se concentra nos 20 piores trechos
    total_mortos = tabela["mortos"].sum()
    resumo = {
        "trechos": numero(len(tabela)),
        "com_morte": numero((tabela["mortos"] > 0).sum()),
        "concentracao": percentual(tabela.nlargest(20, "mortos")["mortos"].sum(), total_mortos),
        "mortos": numero(total_mortos),
    }

    tabela_html = montar_tabela(
        tabela, [("nome", "Trecho"), ("local", "Município")], ordem, f, "trechos", len(validos),
        link_linha=lambda t: link(f, "index", uf=t["uf"], br=t["br"], trecho=t["trecho_km"], municipio=None),
    )

    medida = "mortos" if total_mortos > 0 else "acidentes"
    mapa = painel("Mapa dos trechos",
                  f"Os 60 trechos com mais {medida} · bolha maior = mais {medida}",
                  graficos.grafico_bolhas(tabela.nlargest(60, medida), medida))

    perfil = None
    if f["uf"] and f["br"]:
        por_km = agregar(validos, "trecho_km")
        if not por_km.empty:
            faixas = range(0, int(por_km["trecho_km"].max()) + 10, 10)
            por_km = (por_km.set_index("trecho_km").reindex(faixas, fill_value=0)
                      .rename_axis("trecho_km").reset_index())
        perfil = painel(f"BR-{f['br']} em {f['uf']}, de 10 em 10 km",
                        "Barras = acidentes · pontos vermelhos = mortos",
                        graficos.grafico_perfil(por_km))

    return mostrar(request, "trechos", f, {
        "resumo": resumo, "tabela": tabela_html, "mapa": mapa, "perfil": perfil,
    })


# =============================================================================
# Aba 4 - Vítimas e veículos
# =============================================================================
GRUPOS_PESSOAS = [
    # (coluna, título, cor)
    ("mortos", "Mortos", graficos.VERMELHO),
    ("feridos_graves", "Feridos graves", graficos.VERMELHO_MEDIO),
    ("feridos_leves", "Feridos leves", graficos.VERMELHO_CLARO),
    ("ilesos", "Ilesos", graficos.VERDE),
    ("ignorados", "Ignorados", graficos.CINZA_CLARO),
]


def vitimas(request):
    f, recorte, _, _ = preparar(request)
    media = gravidade(recorte)
    pessoas = recorte["pessoas"].sum()

    por_acidente = decimal(pessoas / len(recorte)) if len(recorte) else "0"
    cartoes = [{"titulo": "Pessoas envolvidas", "valor": numero(pessoas),
                "media": f"{por_acidente} por acidente", "comparacao": "",
                "explicacao": "Condutores, passageiros e pedestres", "cor": graficos.PRETO}]
    for coluna, titulo, cor in GRUPOS_PESSOAS:
        total = recorte[coluna].sum()
        cartoes.append({"titulo": titulo, "valor": numero(total),
                        "media": f"{percentual(total, pessoas)} dos envolvidos",
                        "comparacao": "", "explicacao": "", "cor": cor})

    # Rosca: o que aconteceu com as pessoas envolvidas
    situacao = pd.Series({titulo: recorte[coluna].sum() for coluna, titulo, _ in GRUPOS_PESSOAS})
    rosca = painel("O que aconteceu com os envolvidos", "Cada pessoa aparece em uma só categoria",
                   graficos.grafico_rosca(situacao, {t: c for _, t, c in GRUPOS_PESSOAS}, "pessoas",
                                          [t for _, t, _ in GRUPOS_PESSOAS]))

    # Veículos por acidente: 1, 2, 3, 4, 5 ou mais
    com_faixa = recorte.assign(faixa=recorte["veiculos"].map(faixa_veiculos))
    veiculos = vazio_como_zero(tabela_gravidade(com_faixa, "faixa"), FAIXAS_VEICULOS)
    painel_veiculos = painel("Veículos envolvidos", "Acidentes com 1 veículo, 2 veículos, ..., engavetamentos",
                             graficos.grafico_condicao(veiculos, media, ordem=None))

    # Vítimas por tipo de acidente (os 10 com mais vítimas)
    tipos = recorte.groupby("tipo_acidente")[["mortos", "feridos_graves", "feridos_leves"]].sum()
    tipos["vitimas"] = tipos.sum(axis=1)
    tipos = tipos[tipos["vitimas"] > 0].nlargest(10, "vitimas").reset_index()
    painel_tipos = painel("Vítimas por tipo de acidente", "Os 10 tipos com mais mortos e feridos",
                          graficos.grafico_empilhado(tipos, "tipo_acidente", GRUPOS_PESSOAS[:3]))

    # Tipos mais letais
    letais = tabela_gravidade(recorte, "tipo_acidente")
    letais = letais[letais["acidentes"] >= MINIMO_PARA_INDICE].nlargest(10, "indice")
    painel_letais = painel("Tipos de acidente mais letais",
                           f"Mortos a cada 100 acidentes (mínimo de {MINIMO_PARA_INDICE} acidentes)",
                           graficos.grafico_condicao(letais, media, ordem="indice"))

    return mostrar(request, "vitimas", f, {
        "kpis": cartoes, "paineis": [rosca, painel_veiculos, painel_tipos, painel_letais],
    })


# =============================================================================
# Aba 5 - Estrutura da PRF (regionais, delegacias e UOPs)
# =============================================================================
def estrutura(request):
    f, recorte, _, _ = preparar(request)
    ordem = escolher_ordem(request, "acidentes")
    media = gravidade(recorte)

    regionais = painel("Regionais (superintendências)", "Uma por estado, mais o Distrito Federal",
                       graficos.grafico_condicao(tabela_gravidade(recorte, "regional"), media))

    delegacias = montar_tabela(
        agregar(recorte, ["regional", "delegacia"]),
        [("delegacia", "Delegacia"), ("regional", "Regional")], ordem, f, "estrutura", len(recorte),
        link_linha=lambda d: link(f, "index", regional=d["regional"], delegacia=d["delegacia"]),
    )
    uops = montar_tabela(
        agregar(recorte, ["delegacia", "uop"]),
        [("uop", "Unidade operacional (UOP)"), ("delegacia", "Delegacia")], ordem, f, "estrutura", len(recorte),
    )
    return mostrar(request, "estrutura", f, {
        "regionais": regionais, "delegacias": delegacias, "uops": uops,
    })


# =============================================================================
# Aba 6 - Comparação anual (mesmo período e mesmos filtros em cada ano)
# =============================================================================
def anos(request):
    df = carregar_dados()
    f = ler_filtros(request, df)

    linhas, mensal, anterior = [], [], None
    for ano in anos_disponiveis():
        dados_ano = carregar_ano(ano)
        meses_no_arquivo = sorted(dados_ano["mes"].unique())
        faltando = [m for m in f["meses_do_periodo"] if m not in meses_no_arquivo]
        recorte = recortar(dados_ano, f)[0]
        atual = {"acidentes": len(recorte), "mortos": int(recorte["mortos"].sum()),
                 "feridos_graves": int(recorte["feridos_graves"].sum()), "completo": not faltando}

        # A variação só é justa entre anos com todos os meses do período; por
        # isso cada ano é comparado com o último ano completo antes dele.
        comparavel = anterior is not None and atual["completo"]
        nota = ""
        if faltando:
            nota = f"O arquivo só tem {MESES[meses_no_arquivo[0] - 1]} a {MESES[meses_no_arquivo[-1] - 1]}"
        linhas.append({
            "ano": ano, "atual": ano == ANO_ATUAL, "nota": nota,
            "acidentes": numero(atual["acidentes"]), "mortos": numero(atual["mortos"]),
            "feridos_graves": numero(atual["feridos_graves"]), "indice": decimal(gravidade(recorte)),
            "var_acidentes": variacao(atual["acidentes"], anterior["acidentes"]) if comparavel else "–",
            "var_mortos": variacao(atual["mortos"], anterior["mortos"]) if comparavel else "–",
            "base": anterior["ano"] if comparavel else "",
        })
        if atual["completo"]:
            anterior = {**atual, "ano": ano}

        meses = [m for m in f["meses_do_periodo"] if m in meses_no_arquivo]
        mensal.append(
            recorte.groupby("mes").agg(acidentes=("id", "count"), mortos=("mortos", "sum"))
            .reindex(meses, fill_value=0).rename_axis("mes").reset_index().assign(ano=ano)
        )

    mensal = pd.concat(mensal, ignore_index=True) if mensal else pd.DataFrame(columns=["ano", "mes", "acidentes", "mortos"])
    return mostrar(request, "anos", f, {
        "linhas": linhas,
        "paineis": [
            painel("Acidentes por mês", "Uma linha por ano", graficos.grafico_anos(mensal, "acidentes", "acidentes")),
            painel("Mortos por mês", "Uma linha por ano", graficos.grafico_anos(mensal, "mortos", "mortos")),
        ],
    })


# =============================================================================
# Download - os acidentes do filtro atual, com as 30 colunas originais
# =============================================================================
def exportar(request):
    f, recorte, _, _ = preparar(request)
    nome = slugify(f"acidentes prf {ANO_ATUAL} {f['local']}")
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{nome}.csv"'
    resposta.write("﻿")  # marca BOM: faz o Excel reconhecer os acentos
    tabela = recorte[COLUNAS_ORIGINAIS].copy()
    for coluna in tabela.select_dtypes("float").columns:
        valores = tabela[coluna].dropna()
        if (valores % 1 == 0).all():  # só números inteiros: 211.0 vira 211
            tabela[coluna] = tabela[coluna].astype("Int64")
    tabela.to_csv(resposta, sep=";", decimal=",", index=False)
    return resposta
