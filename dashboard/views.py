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
from django.utils.html import format_html
from django.utils.text import slugify

from . import decisao, graficos
from .calculos import (FAIXAS_VEICULOS, MINIMO_PARA_INDICE, agregar, decimal, faixa_veiculos,
                       gravidade, inteiro_valido, media_mensal, numero, percentual,
                       sem_desconhecidos, separar_valores, tabela_gravidade, variacao,
                       vazio_como_zero)
from .dados import (ANO_ATUAL, COLUNAS_ORIGINAIS, DIAS_SEMANA, ESTADOS, MESES, anos_disponiveis,
                    carregar_ano, carregar_dados)
from .filtros import ler_filtros, link, recortar

ANO_ANTERIOR = ANO_ATUAL - 1

# Acima deste número de pontos o mapa fica pesado; aí mostramos só os
# acidentes com vítimas fatais.
LIMITE_PONTOS_MAPA = 8000

# Abas do painel: (nome da rota em urls.py, título no menu)
ABAS = [
    ("index", "Visão geral"),
    ("prioridades", "Onde agir"),
    ("condicoes", "Condições"),
    ("trechos", "Trechos críticos"),
    ("vitimas", "Vítimas"),
    ("estrutura", "Estrutura PRF"),
    ("anos", "Comparação anual"),
    ("metas", "Metas e avaliação"),
]

# Textos do botão ⓘ dos cartões
AJUDA = {
    "acidentes": "Todos os acidentes registrados pela PRF nas rodovias federais, no filtro e período escolhidos.",
    "mortos": "Pessoas que morreram no local do acidente, segundo o registro da PRF.",
    "feridos_graves": "Pessoas com ferimentos graves. Os feridos leves aparecem na linha de baixo.",
    "indice": "Índice de gravidade = mortos ÷ acidentes × 100. Mostra o quanto os acidentes são letais, "
              "independentemente de quantos acontecem.",
    "ups": "UPS (Unidade Padrão de Severidade, DENATRAN): cada acidente vale 1 se não teve vítimas, 4 se teve "
           "feridos, 6 se teve pedestre ferido e 13 se teve morte. A soma mede a gravidade total.",
}

# Nome de cada filtro nas etiquetas removíveis do topo
ROTULOS_FILTRO = {
    "uf": lambda v: ESTADOS.get(v, v),
    "municipio": lambda v: str(v).title(),
    "br": lambda v: f"BR-{v}",
    "trecho": lambda v: f"km {v} a {int(v) + 10}",
    "mes_inicio": lambda v: "A partir de " + MESES[int(v) - 1],
    "mes_fim": lambda v: "Até " + MESES[int(v) - 1],
}
# Ao tirar um filtro, os que dependem dele saem junto
DEPENDENTES = {"uf": ["municipio", "trecho"], "br": ["trecho"], "regional": ["delegacia"]}


# =============================================================================
# Peças comuns a todas as abas
# =============================================================================
def preparar(request):
    """Lê os filtros e recorta os acidentes do ano atual."""
    df = carregar_dados()
    f = ler_filtros(request, df)
    recorte, comparacao, nome_comparacao = recortar(df, f)
    return f, recorte, comparacao, nome_comparacao


def mesmo_periodo_anterior(f):
    """
    Os acidentes do ano anterior com os mesmos filtros e os mesmos meses, para
    a comparação ser justa. None se o arquivo do ano anterior não tiver todos os meses.
    """
    dados = carregar_ano(ANO_ANTERIOR)
    if dados is None or not set(f["meses_do_periodo"]) <= set(dados["mes"].unique()):
        return None
    return recortar(dados, f)[0]


def etiquetas_de_filtro(f, aba):
    """Uma etiqueta por filtro em uso, cada uma com o link que tira aquele filtro."""
    etiquetas = []
    for chave, valor in f["parametros"].items():
        tirar = {chave: None, **{d: None for d in DEPENDENTES.get(chave, [])}}
        texto = ROTULOS_FILTRO.get(chave, str)(valor)
        etiquetas.append({"texto": texto, "link": link(f, aba, **tirar)})
    return etiquetas


def mostrar(request, aba, f, contexto):
    """Junta os filtros, o menu de abas e o conteúdo da aba, e desenha a página."""
    contexto = {
        **f,
        **contexto,
        "aba": aba,
        "abas": [{"titulo": titulo, "url": link(f, nome), "ativa": nome == aba} for nome, titulo in ABAS],
        "etiquetas": etiquetas_de_filtro(f, aba),
        "plotly_js": graficos.PLOTLY_JS,
        "link_exportar": link(f, "exportar"),
        "link_limpar": reverse(aba),
        "ano_atual": ANO_ATUAL,
        "ano_anterior": ANO_ANTERIOR,
    }
    return render(request, f"dashboard/{aba}.html", contexto)


def analise_do_filtro(f, recorte):
    """O que o resumo executivo precisa: ano anterior, ranking, janelas e grupos de causa."""
    anterior = mesmo_periodo_anterior(f)
    ranking = decisao.ranking_trechos(recorte, anterior)
    janelas = decisao.janelas_de_risco(recorte, 8)
    grupos = decisao.tabela_grupos(recorte)
    resumo = decisao.resumo_executivo(f, recorte, anterior, ANO_ANTERIOR, ranking, janelas, grupos)
    return {"anterior": anterior, "ranking": ranking, "janelas": janelas, "grupos": grupos, "resumo": resumo}


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


def com_tendencia(kpi, atual, anterior, minimo=decisao.MINIMO_TENDENCIA):
    """Acrescenta ao cartão a variação em relação aos mesmos meses do ano anterior."""
    t = decisao.tendencia(atual, anterior, minimo)
    if t:
        kpi["tendencia"] = {**t, "rotulo": f"vs mesmos meses de {ANO_ANTERIOR}"}
    return kpi


def cartoes_principais(recorte, comparacao, nome_comparacao, n_meses, anterior=None):
    """Os quatro cartões do topo: acidentes, mortos, feridos graves e índice."""
    def cartao(titulo, total, total_acima, explicacao, ajuda, cor=graficos.PRETO, total_anterior=None):
        kpi = {"titulo": titulo, "valor": numero(total),
               "media": f"Média de {media_mensal(total, n_meses)} por mês",
               "comparacao": "", "explicacao": explicacao, "cor": cor, "ajuda": AJUDA[ajuda]}
        if comparacao is not None:
            kpi["comparacao"] = f"{percentual(total, total_acima)} do total {nome_comparacao}"
        if total_anterior is not None:
            com_tendencia(kpi, total, total_anterior)
        return kpi

    acima = comparacao if comparacao is not None else recorte
    ant = anterior is not None
    kpis = [
        cartao("Acidentes", len(recorte), len(acima), "Acidentes registrados pela PRF", "acidentes",
               total_anterior=len(anterior) if ant else None),
        cartao("Mortos", recorte["mortos"].sum(), acima["mortos"].sum(),
               "Pessoas mortas nos acidentes", "mortos", cor=graficos.VERMELHO,
               total_anterior=anterior["mortos"].sum() if ant else None),
        cartao("Feridos graves", recorte["feridos_graves"].sum(), acima["feridos_graves"].sum(),
               f"Mais {numero(recorte['feridos_leves'].sum())} feridos leves", "feridos_graves",
               cor=graficos.VERMELHO_MEDIO,
               total_anterior=anterior["feridos_graves"].sum() if ant else None),
    ]
    indice = {"titulo": "Índice de gravidade", "valor": decimal(gravidade(recorte)),
              "media": "Mortos a cada 100 acidentes", "comparacao": "",
              "explicacao": "Quanto maior, mais letais os acidentes", "cor": graficos.CINZA_ESCURO,
              "ajuda": AJUDA["indice"]}
    if comparacao is not None:
        indice["comparacao"] = f"Média {nome_comparacao}: {decimal(gravidade(comparacao))}"
    if ant and len(anterior):
        indice["comparacao"] = (indice["comparacao"] + " · " if indice["comparacao"] else "") + \
            f"{ANO_ANTERIOR}: {decimal(gravidade(anterior))}"
    kpis.append(indice)
    return kpis


# =============================================================================
# Aba 1 - Visão geral
# =============================================================================
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
        "kpis": kpis, "aviso_mapa": aviso_mapa, "titulo_ranking": titulo_ranking,
        "resumo": analise["resumo"], **html,
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
        link_linha=lambda t: link(f, "ficha", uf=t["uf"], br=t["br"], trecho=t["trecho_km"], municipio=None),
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
# Aba 2 - Onde agir: prioridades por gravidade, mapa de calor e janelas de risco
# =============================================================================
def link_ficha(f, uf, br, trecho_km):
    return link(f, "ficha", uf=uf, br=br, trecho=trecho_km, municipio=None)


def prioridades(request):
    f, recorte, _, _ = preparar(request)
    analise = analise_do_filtro(f, recorte)
    top = analise["ranking"].head(20)
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
        "resumo": analise["resumo"], "linhas": linhas, "janelas": analise["janelas"],
        "grupos": analise["grupos"], "tem_anterior": analise["anterior"] is not None,
        "ajuda_ups": AJUDA["ups"], **html,
    })


# =============================================================================
# Ficha do trecho: tudo de um trecho de 10 km, pronta para imprimir
# =============================================================================
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

    tipos = (recorte["tipo_acidente"].value_counts().head(8)
             .rename_axis("tipo").reset_index(name="acidentes"))
    html = graficos.para_html({
        "grafico_mensal": graficos.grafico_anos(mensal, "acidentes", "acidentes"),
        "grafico_calor": graficos.grafico_calor(decisao.calor_ups(recorte, DIAS_SEMANA),
                                                "de gravidade (UPS)", "UPS"),
        "grafico_grupos": graficos.grafico_grupos(grupos),
        "grafico_tipos": graficos.grafico_barras(tipos, "tipo", "acidentes", "acidentes"),
        "grafico_mapa": graficos.grafico_mapa(recorte.dropna(subset=["latitude", "longitude"])),
    })
    return mostrar(request, "ficha", f, {
        "sem_trecho": False, "vazio": recorte.empty,
        "nome_trecho": decisao.nome_trecho(f["br"], f["trecho"]), "municipio_trecho": municipio,
        "kpis": kpis, "recomendacoes": decisao.recomendacoes(recorte, anterior, ANO_ANTERIOR, janelas, grupos),
        "janelas": janelas, "grupos": grupos, "link_onde_agir": link(f, "prioridades", trecho=None),
        **html,
    })


# =============================================================================
# Aba 8 - Metas e avaliação: acompanhamento de meta e antes/depois de uma ação
# =============================================================================
def metas(request):
    f, _, _, _ = preparar(request)
    get = request.GET
    indicador = get.get("indicador", "mortos")
    if indicador not in decisao.INDICADORES:
        indicador = "mortos"
    nome = decisao.INDICADORES[indicador]
    meta = inteiro_valido(get.get("meta"), 10, 0, 90)
    contexto = {"indicador": indicador, "nome_indicador": nome, "meta": meta,
                "indicadores": list(decisao.INDICADORES.items()), "acompanhamento": None}

    # --- Acompanhamento da meta: ano atual acumulado x ano anterior - meta% ---
    atual = decisao.mensal_do_ano(carregar_dados(), f)
    base_dados = carregar_ano(ANO_ANTERIOR)
    meses_atual = [m for m in range(1, 13) if pd.notna(atual.loc[m, indicador])]
    if base_dados is not None and meses_atual:
        base = decisao.mensal_do_ano(base_dados, f)
        fator = 1 - meta / 100
        ultimo = meses_atual[-1]
        tabela = pd.DataFrame({"mes": range(1, 13),
                               "base": base[indicador].fillna(0).cumsum().to_numpy(),
                               "atual": atual[indicador].cumsum().to_numpy()})
        tabela.loc[tabela["mes"] > ultimo, "atual"] = None
        tabela["meta"] = tabela["base"] * fator
        no_mes = tabela.set_index("mes").loc[ultimo]
        a, b, m = no_mes["atual"], no_mes["base"], no_mes["meta"]
        base_ano, meta_ano = tabela["base"].iloc[-1], tabela["base"].iloc[-1] * fator
        projecao = a * base_ano / b if b else a / ultimo * 12
        dentro = a <= m
        periodo = f"Jan a {MESES[ultimo - 1]}" if ultimo > 1 else "Jan"

        cartoes = [
            com_tendencia({"titulo": f"{nome} em {ANO_ATUAL}", "valor": numero(a), "media": periodo,
                           "comparacao": f"{ANO_ANTERIOR} no mesmo período: {numero(b)}", "explicacao": "",
                           "cor": graficos.PRETO, "ajuda": AJUDA.get(indicador, "")}, a, b, minimo=0),
            {"titulo": "Limite da meta no período", "valor": numero(m),
             "media": f"{meta}% abaixo de {ANO_ANTERIOR}", "comparacao": "",
             "explicacao": "A meta acompanha a sazonalidade: cada mês é comparado com o mesmo mês do ano anterior",
             "cor": graficos.VERDE, "ajuda": ""},
            {"titulo": "Situação", "valor": "Dentro da meta" if dentro else "Acima da meta",
             "media": f"{numero(abs(m - a))} {nome.lower()} {'abaixo' if dentro else 'acima'} do limite",
             "comparacao": "", "explicacao": "", "cor": graficos.VERDE if dentro else graficos.VERMELHO,
             "ajuda": "", "valor_menor": True},
            {"titulo": f"Projeção para {ANO_ATUAL}", "valor": numero(projecao),
             "media": f"Meta do ano: até {numero(meta_ano)}", "comparacao": "",
             "explicacao": f"Mantido o ritmo atual, com a sazonalidade de {ANO_ANTERIOR}",
             "cor": graficos.VERDE if projecao <= meta_ano else graficos.VERMELHO, "ajuda": ""},
        ]
        frase_restante = ""
        restantes = 12 - ultimo
        if restantes > 0:
            limite = meta_ano - a
            base_restante = base_ano - b
            if limite <= 0:
                frase_restante = format_html(
                    "O limite do ano (<b>{}</b>) já foi ultrapassado: a meta anual não pode mais ser cumprida.",
                    numero(meta_ano))
            else:
                frase_restante = format_html(
                    "Para cumprir a meta do ano, os {} meses restantes podem ter no máximo <b>{}</b> {} "
                    "(média de <b>{}</b> por mês). No mesmo período de {} foram {} (média de {} por mês).",
                    restantes, numero(limite), nome.lower(), media_mensal(limite, restantes), ANO_ANTERIOR,
                    numero(base_restante), media_mensal(base_restante, restantes))

        linhas = []
        for mes in range(1, 13):
            v_atual, v_base = atual.loc[mes, indicador], base.loc[mes, indicador]
            limite_mes = v_base * fator if pd.notna(v_base) else None
            tem = pd.notna(v_atual)
            linhas.append({
                "mes": MESES[mes - 1], "atual": numero(v_atual) if tem else "–",
                "base": numero(v_base) if pd.notna(v_base) else "–",
                "variacao": variacao(v_atual, v_base) if tem and pd.notna(v_base) else "–",
                "limite": numero(limite_mes) if limite_mes is not None else "–",
                "ok": None if not tem or limite_mes is None else v_atual <= limite_mes,
            })
        contexto["acompanhamento"] = {
            "cartoes": cartoes, "frase_restante": frase_restante, "linhas": linhas,
            "grafico": graficos.html_de(graficos.grafico_meta(tabela, nome.lower(), ANO_ATUAL, ANO_ANTERIOR)),
        }

    # --- Antes e depois de uma intervenção -----------------------------------
    serie = decisao.serie_mensal([(ano, carregar_ano(ano)) for ano in anos_disponiveis()], f)
    opcoes = [(str(p), decisao.texto_mes(p)) for p in serie.index[1:-1]]
    escolhida = get.get("intervencao", "")
    janela = inteiro_valido(get.get("janela"), 6, 1, 12)
    resultado = intervencao = None
    if escolhida in dict(opcoes):
        intervencao = pd.Period(escolhida, freq="M")
        resultado = decisao.antes_depois(serie, intervencao, janela)
    contexto.update({
        "opcoes_intervencao": opcoes, "intervencao": escolhida, "janela": janela,
        "janelas_opcoes": [3, 6, 12], "resultado": resultado,
        "texto_intervencao": decisao.texto_mes(intervencao) if intervencao is not None else "",
        "grafico_antes_depois": graficos.html_de(
            graficos.grafico_antes_depois(serie, indicador, nome, resultado, intervencao)),
    })
    return mostrar(request, "metas", f, contexto)


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
