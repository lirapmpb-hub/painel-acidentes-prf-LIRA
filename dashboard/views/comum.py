"""
Peças comuns a todas as abas: filtros, menu, cartões, tabelas e o desenho da página.
"""
from django.shortcuts import render
from django.urls import reverse

from .. import decisao, graficos
from ..calculos import (MINIMO_PARA_INDICE, decimal, gravidade, media_mensal, numero,
                        percentual)
from ..dados import ANO_ATUAL, ESTADOS, MESES, carregar_ano, carregar_dados
from ..filtros import ler_filtros, link, recortar

ANO_ANTERIOR = ANO_ATUAL - 1

# Abas do painel: (nome da rota em urls.py, título no menu, pergunta que a aba responde)
ABAS = [
    ("inicio", "Início", "O que é o painel"),
    ("index", "Panorama", "Qual é a situação?"),
    ("prioridades", "Onde agir", "Onde e quando agir?"),
    ("por_que", "Por quê", "O que faz os acidentes matarem?"),
    ("acompanhar", "Acompanhar", "Estamos melhorando?"),
    ("estrutura", "Estrutura PRF", "Quem cobre cada área?"),
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

# Nome de cada filtro nas etiquetas removíveis da barra de filtros
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
    """
    Junta os filtros, o menu de abas e o conteúdo da aba, e desenha a página
    dashboard/<aba>.html. contexto["secoes"] = [(âncora, título)] vira o
    atalho "Nesta página" no topo.
    """
    contexto = {
        **f,
        **contexto,
        "aba": aba,
        # o Início não leva filtros (com filtro, o endereço "/" vai para o Panorama)
        "abas": [{"titulo": titulo, "pergunta": pergunta, "ativa": nome == aba,
                  "url": reverse(nome) if nome == "inicio" else link(f, nome)}
                 for nome, titulo, pergunta in ABAS],
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


def painel(titulo, subtitulo, figura, ancora=""):
    """Um quadro branco com título, subtítulo e gráfico (ver _painel.html)."""
    return {"titulo": titulo, "subtitulo": subtitulo, "html": graficos.html_de(figura), "ancora": ancora}


def link_ficha(f, uf, br, trecho_km):
    return link(f, "ficha", uf=uf, br=br, trecho=trecho_km, municipio=None)


def escolher_ordem(request, padrao):
    """Coluna usada para ordenar as tabelas, escolhida clicando no cabeçalho."""
    ordem = request.GET.get("ordem", padrao)
    return ordem if ordem in ("acidentes", "mortos", "indice") else padrao


def montar_tabela(tabela, colunas_texto, ordem, f, aba, total, link_linha=None, limite=20, ancora=""):
    """
    Prepara uma tabela para o _tabela.html. colunas_texto = [(coluna, título)]
    das primeiras colunas; as demais são sempre as medidas de acidentes.
    ancora: a página volta para a tabela depois de reordenar.
    """
    if ordem == "indice":
        tabela = tabela[tabela["acidentes"] >= MINIMO_PARA_INDICE]
    tabela = tabela.sort_values([ordem, "acidentes"], ascending=False).head(limite)
    sufixo = f"#{ancora}" if ancora else ""

    def cabecalho(titulo, chave=None):
        if not chave:
            return {"titulo": titulo}
        return {"titulo": titulo, "link": link(f, aba, ordem=chave) + sufixo, "ativa": chave == ordem}

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
