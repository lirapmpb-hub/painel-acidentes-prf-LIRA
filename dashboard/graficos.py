"""
Camada de apresentação (equivale aos visuais do Power BI).

Cada função recebe uma tabela já calculada e devolve um gráfico do Plotly.
Sem dados para o filtro, a função devolve None e o painel mostra um aviso.
"""
from functools import wraps
from html import escape
from math import log2

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.colors import sample_colorscale
from plotly.offline import get_plotlyjs_version, plot
from plotly.subplots import make_subplots

from .calculos import MINIMO_PARA_INDICE
from .dados import CLASSIFICACOES, DIAS_CURTOS, MESES

# --- Cores ------------------------------------------------------------------
# Paleta do Manual de Identidade Visual da PMPB (seções 2.6 e 6.1.4):
# preto #1d1d1b, vermelho #e30613, cinzas K80/K50/K30 e verde #009640.
PRETO = "#1d1d1b"
GRAFITE = "#3c3c3b"            # série principal (acidentes)
VERMELHO = "#e30613"           # mortos / acima da média
VERMELHO_MEDIO = "#f0767c"     # feridos graves (tom do vermelho oficial)
VERMELHO_CLARO = "#f8bcbf"     # feridos leves
VERDE = "#009640"              # ilesos
CINZA, CINZA_CLARO, CINZA_ESCURO = "#9d9d9d", "#c6c6c6", "#706f6f"
CORES_CLASSIFICACAO = {
    "Com Vítimas Fatais": VERMELHO,
    "Com Vítimas Feridas": VERMELHO_MEDIO,
    "Sem Vítimas": CINZA,
    "Não informado": CINZA_CLARO,
}
CORES_ANOS = {"2023": CINZA_CLARO, "2024": CINZA, "2025": CINZA_ESCURO, "2026": VERMELHO}
ESCALA_CALOR = ["#fdf0f0", "#f6a5a9", "#e30613", "#7a030a"]   # do claro ao escuro, no vermelho oficial
ESCALA_CINZA = ["#ededed", "#c6c6c6", "#706f6f", PRETO]       # do claro ao escuro, nos cinzas oficiais

# Endereço da biblioteca do Plotly; o base.html carrega uma vez para a página toda.
PLOTLY_JS = f"https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js"
CONFIG_PLOTLY = {"displayModeBar": False, "responsive": True}
AVISO_SEM_DADOS = '<p class="py-16 text-center text-sm text-pm-cinza">Sem acidentes para este filtro.</p>'


def protegido(funcao):
    """Se um gráfico der erro, a página continua abrindo e mostra a mensagem."""
    @wraps(funcao)
    def com_protecao(*args, **kwargs):
        try:
            return funcao(*args, **kwargs)
        except Exception as erro:
            mensagem = escape(f"{type(erro).__name__}: {erro}"[:400])
            return f'<p class="py-10 text-sm text-pm-vermelho-escuro">Erro ao montar este gráfico: {mensagem}</p>'
    return com_protecao


def estilo_padrao(fig, altura, legenda=False):
    """Aplica o mesmo visual limpo a todos os gráficos."""
    fig.update_layout(
        template="plotly_white",
        height=altura,
        margin={"l": 10, "r": 30, "t": 30, "b": 10},
        separators=",.",  # vírgula nos decimais e ponto nos milhares
        font={"family": "Arial, Helvetica, sans-serif", "size": 12, "color": PRETO},
        showlegend=legenda,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0, "title": {"text": ""}},
        hoverlabel={"bgcolor": PRETO, "bordercolor": VERMELHO, "font": {"color": "white"}},
    )
    fig.update_xaxes(gridcolor="#ececec", linecolor=CINZA_CLARO, zerolinecolor=CINZA_CLARO)
    fig.update_yaxes(gridcolor="#ececec", linecolor=CINZA_CLARO, zerolinecolor=CINZA_CLARO)
    return fig


def encurtar(texto, limite=42):
    """Corta nomes muito longos para caberem no eixo do gráfico."""
    texto = str(texto)
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


# =============================================================================
# Ordenação escolhida pelo usuário (botões "Ordenar por" acima do gráfico)
# =============================================================================
# Cada gráfico ordenável guarda em layout.meta a lista das categorias em cada
# ordem; os botões (ver html_de e o script do base.html) só trocam a ordem do
# eixo, sem recarregar a página. Com `limite`, mostra só os N primeiros daquela
# ordem: o gráfico recebe os candidatos de todas as ordens (ver calculos.candidatos).
ROTULOS_ORDEM = {
    "padrao": "Ordem natural", "acidentes": "Acidentes", "mortos": "Mortos",
    "indice": "Letalidade", "vitimas": "Vítimas", "feridos_graves": "Feridos graves",
    "feridos_leves": "Feridos leves", "nome": "Nome (A–Z)",
}
DICA_ORDEM = {"indice": f"Mortos a cada 100 acidentes. Categorias com menos de {MINIMO_PARA_INDICE} "
                        "acidentes ficam no fim, porque o índice oscila demais com poucos casos."}


def nomes_unicos(rotulos, limite):
    """Nomes encurtados para o eixo, sem repetição (o eixo usa o nome como chave)."""
    nomes, vistos = [], set()
    for rotulo in rotulos:
        nome = encurtar(rotulo, limite)
        while nome in vistos:
            nome += " "
        vistos.add(nome)
        nomes.append(nome)
    return nomes


def ordenar(nomes, tabela, chave, desempate):
    """Nomes do menor para o maior valor (no gráfico de barras deitadas, o maior fica no topo)."""
    if chave == "indice":
        valores = list(zip(tabela["acidentes"] >= MINIMO_PARA_INDICE, tabela["indice"], tabela["acidentes"]))
    else:
        valores = list(zip(tabela[chave], tabela[desempate]))
    return [nomes[i] for i in sorted(range(len(nomes)), key=lambda i: valores[i])]


def aplicar_ordens(fig, ordens, ativa, limite):
    """Põe o eixo na ordem ativa e guarda as outras ordens para os botões. Devolve quantas barras aparecem."""
    n = len(ordens[ativa])
    visiveis = min(n, limite) if limite else n
    fig.update_yaxes(categoryorder="array", categoryarray=ordens[ativa],
                     range=[n - visiveis - 0.5, n - 0.5], autorange=False)
    fig.update_layout(meta={"ordens": ordens, "limite": limite or 0, "ativa": ativa}, dragmode=False)
    return visiveis


# =============================================================================
# Visão geral
# =============================================================================
@protegido
def grafico_linha(tabela):
    """LINHA - acidentes por mês. Espera as colunas: mes e acidentes."""
    if tabela["acidentes"].sum() == 0:
        return None
    tabela = tabela.sort_values("mes").copy()
    x = [MESES[m - 1] for m in tabela["mes"]]
    dados = list(zip(tabela["acidentes"], tabela["mortos"]))
    dica = "%{x}: %{customdata[0]:,.0f} acidentes · %{customdata[1]:,.0f} mortos<extra></extra>"
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=x, y=tabela["acidentes"], name="Acidentes", mode="lines+markers", customdata=dados,
        line={"color": GRAFITE, "width": 2.5}, marker={"size": 8, "line": {"color": "white", "width": 1.5}},
        hovertemplate=dica,
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=x, y=tabela["mortos"], name="Mortos (eixo da direita)", mode="lines+markers", customdata=dados,
        line={"color": VERMELHO, "width": 2.5}, marker={"size": 8, "line": {"color": "white", "width": 1.5}},
        hovertemplate=dica,
    ), secondary_y=True)
    fig.update_xaxes(title=None)
    fig.update_yaxes(title="Acidentes", tickformat=",.0f", rangemode="tozero", secondary_y=False)
    fig.update_yaxes(title="Mortos", tickformat=",.0f", rangemode="tozero", showgrid=False,
                     color=VERMELHO, secondary_y=True)
    return estilo_padrao(fig, altura=360, legenda=True)


@protegido
def grafico_rosca(contagem, cores, unidade="acidentes", ordem=None):
    """ROSCA - partes de um total. Recebe uma série {categoria: quantidade}."""
    contagem = contagem[contagem > 0]
    if contagem.empty:
        return None
    tabela = contagem.rename_axis("rotulo").reset_index(name="valor")
    fig = px.pie(tabela, names="rotulo", values="valor", color="rotulo",
                 color_discrete_map=cores, hole=0.62,
                 category_orders={"rotulo": ordem or list(tabela["rotulo"])})
    fig.update_traces(
        sort=False,
        textinfo="percent",
        marker={"line": {"color": "white", "width": 2}},
        hovertemplate="%{label}<br>%{value:,.0f} " + unidade + " (%{percent})<extra></extra>",
    )
    total = f"{contagem.sum():,.0f}".replace(",", ".")
    fig.add_annotation(text=f"<b>{total}</b><br>{unidade}", x=0.5, y=0.5,
                       xref="paper", yref="paper", showarrow=False, font={"size": 16})
    estilo_padrao(fig, altura=360, legenda=True)
    fig.update_layout(legend={"yanchor": "top", "y": -0.05, "x": 0.5, "xanchor": "center"})
    return fig


def grafico_classificacao(contagem):
    """ROSCA - acidentes por gravidade. Recebe uma série {classificação: total}."""
    return grafico_rosca(contagem, CORES_CLASSIFICACAO, "acidentes", CLASSIFICACOES)


def zoom_do_mapa(pontos):
    """Escolhe o zoom pela área ocupada pelos pontos: Brasil, estado ou cidade."""
    lat = pontos["latitude"].quantile([0.02, 0.98])
    lon = pontos["longitude"].quantile([0.02, 0.98])
    extensao = max(lat.iloc[1] - lat.iloc[0], lon.iloc[1] - lon.iloc[0], 0.05)
    return min(max(log2(360 / extensao) - 1.3, 2.8), 11)


@protegido
def grafico_mapa(pontos):
    """MAPA - cada ponto é um acidente, colorido pela gravidade."""
    if pontos.empty:
        return None
    pontos = pontos.copy()
    pontos["local"] = pontos["municipio"].str.title() + " - " + pontos["uf"]
    pontos["rodovia"] = "BR-" + pontos["br"].astype(str) + ", km " + pontos["km"].map(lambda k: f"{k:g}".replace(".", ","))
    fig = px.scatter_map(
        pontos,
        lat="latitude",
        lon="longitude",
        color="classificacao_acidente",
        color_discrete_map=CORES_CLASSIFICACAO,
        category_orders={"classificacao_acidente": CLASSIFICACOES},
        custom_data=["local", "rodovia", "tipo_acidente", "mortos"],
        zoom=zoom_do_mapa(pontos),
        center={"lat": pontos["latitude"].median(), "lon": pontos["longitude"].median()},
        map_style="carto-positron",  # mapa de fundo claro, gratuito
    )
    fig.update_traces(
        marker={"size": 7, "opacity": 0.75},
        hovertemplate=("%{customdata[0]}<br>%{customdata[1]}<br>%{customdata[2]}"
                       "<br>%{customdata[3]} mortos<extra></extra>"),
    )
    estilo_padrao(fig, altura=520, legenda=True)
    fig.update_layout(margin={"l": 0, "r": 0, "t": 30, "b": 0})
    return fig


@protegido
def grafico_calor(tabela, unidade="acidentes", legenda="Acidentes"):
    """MAPA DE CALOR - dia da semana (linhas) x hora do dia (colunas)."""
    if tabela.to_numpy().sum() == 0:
        return None
    fig = px.imshow(
        tabela.to_numpy(),
        x=[f"{h}h" for h in tabela.columns],
        y=DIAS_CURTOS,
        color_continuous_scale=ESCALA_CALOR,
        aspect="auto",
    )
    fig.update_traces(xgap=2, ygap=2,
                      hovertemplate="%{y}, %{x}<br>%{z:,.0f} " + unidade + "<extra></extra>")
    fig.update_xaxes(title=None, side="bottom", tickangle=0, dtick=2)
    fig.update_yaxes(title=None)
    estilo_padrao(fig, altura=340)
    fig.update_layout(coloraxis_colorbar={"title": {"text": legenda}, "thickness": 12})
    return fig


@protegido
def grafico_arvore(tabela):
    """MAPA DE ÁRVORE - participação de cada tipo de acidente. Colunas: rotulo, acidentes."""
    if tabela.empty:
        return None
    # Cinza mais escuro para os tipos mais frequentes; texto branco só nos blocos escuros
    valores = list(tabela["acidentes"])
    maior = max(valores) or 1
    proporcoes = [v / maior for v in valores]
    cores = [sample_colorscale(ESCALA_CINZA, [0.15 + 0.85 * p])[0] for p in proporcoes]
    cores_texto = ["white" if p > 0.45 else PRETO for p in proporcoes]
    fig = go.Figure(go.Treemap(
        labels=list(tabela["rotulo"]),
        parents=[""] * len(tabela),
        values=valores,
        marker={"colors": cores, "line": {"color": "white", "width": 2}},
        root={"color": "white"},
        insidetextfont={"color": cores_texto},
        customdata=list(tabela["mortos"]) if "mortos" in tabela else [0] * len(tabela),
        texttemplate="%{label}<br>%{value:,.0f} acidentes · %{customdata:,.0f} mortos",
        hovertemplate=("%{label}<br>%{value:,.0f} acidentes (%{percentRoot:.1%} do total)"
                       "<br>%{customdata:,.0f} mortos<extra></extra>"),
        pathbar={"visible": False},
    ))
    estilo_padrao(fig, altura=420)
    fig.update_layout(margin={"l": 0, "r": 0, "t": 10, "b": 0})
    return fig


@protegido
def grafico_barras(tabela, rotulo, valor, nome_valor, cor=GRAFITE):
    """BARRAS horizontais, da maior para a menor, com o valor na ponta."""
    tabela = tabela[tabela[valor] > 0]
    if tabela.empty:
        return None
    tabela = tabela.sort_values(valor).copy()  # a maior barra fica no topo
    tabela["nome"] = tabela[rotulo].map(encurtar)
    fig = px.bar(tabela, x=valor, y="nome", orientation="h", custom_data=[rotulo],
                 color_discrete_sequence=[cor])
    fig.update_traces(
        texttemplate="%{x:,.0f}",
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{customdata[0]}<br>%{x:,.0f} " + nome_valor + "<extra></extra>",
    )
    fig.update_xaxes(title=None, showticklabels=False, showgrid=False)
    fig.update_yaxes(title=None)
    estilo_padrao(fig, altura=max(260, 30 * len(tabela) + 40))
    fig.update_layout(margin={"r": 60})
    return fig


# =============================================================================
# Condições, vítimas e estrutura
# =============================================================================
@protegido
def grafico_condicao(tabela, media, ordem="acidentes", limite=None):
    """
    BARRAS TRIPLAS - para cada categoria: quantos acidentes, quantos mortos e
    quantos mortos a cada 100 acidentes (vermelho = acima da média, linha
    pontilhada = média). Colunas: rotulo, acidentes, mortos, indice.
    ordem = ordem inicial ("acidentes", "mortos" ou "indice"); None mantém a
    ordem recebida (a primeira linha no topo). limite = quantas barras mostrar.
    Os botões "Ordenar por" trocam a ordem no navegador.
    """
    tabela = tabela[tabela["acidentes"] > 0].reset_index(drop=True)
    if tabela.empty:
        return None
    rotulos = [str(r) for r in tabela["rotulo"]]
    nomes = nomes_unicos(rotulos, 34)
    ordens = {"padrao": nomes[::-1]} if ordem is None else {}
    ordens["acidentes"] = ordenar(nomes, tabela, "acidentes", "mortos")
    ordens["mortos"] = ordenar(nomes, tabela, "mortos", "acidentes")
    ordens["indice"] = ordenar(nomes, tabela, "indice", "acidentes")
    if not limite:
        ordens["nome"] = sorted(nomes, reverse=True)

    dados = [[r, a, m, i] for r, a, m, i in zip(rotulos, tabela["acidentes"], tabela["mortos"], tabela["indice"])]
    dica = ("%{customdata[0]}<br>%{customdata[1]:,.0f} acidentes · %{customdata[2]:,.0f} mortos"
            "<br>%{customdata[3]:.1f} mortos a cada 100 acidentes<extra></extra>")
    fig = make_subplots(rows=1, cols=3, shared_yaxes=True, horizontal_spacing=0.04,
                        column_widths=[0.36, 0.28, 0.36],
                        subplot_titles=("Acidentes", "Mortos", "Mortos a cada 100 acidentes"))
    fig.add_trace(go.Bar(
        x=tabela["acidentes"], y=nomes, orientation="h", marker_color=GRAFITE, customdata=dados,
        texttemplate="%{x:,.0f}", textposition="outside", cliponaxis=False, hovertemplate=dica,
    ), row=1, col=1)
    fig.add_trace(go.Bar(
        x=tabela["mortos"], y=nomes, orientation="h", marker_color=VERMELHO, customdata=dados,
        texttemplate="%{x:,.0f}", textposition="outside", cliponaxis=False, hovertemplate=dica,
    ), row=1, col=2)
    fig.add_trace(go.Bar(
        x=tabela["indice"], y=nomes, orientation="h", customdata=dados,
        marker_color=[VERMELHO_MEDIO if v > media else CINZA_CLARO for v in tabela["indice"]],
        texttemplate="%{x:.1f}", textposition="outside", cliponaxis=False, hovertemplate=dica,
    ), row=1, col=3)
    if media > 0:
        fig.add_vline(x=media, line_width=1, line_dash="dot", line_color=CINZA_ESCURO, row=1, col=3)

    fig.update_xaxes(title=None, showticklabels=False, showgrid=False, zeroline=False, fixedrange=True)
    fig.update_xaxes(range=[0, tabela["acidentes"].max() * 1.35], row=1, col=1)
    fig.update_xaxes(range=[0, (tabela["mortos"].max() or 1) * 1.4], row=1, col=2)
    fig.update_xaxes(range=[0, max(tabela["indice"].max(), media) * 1.35 or 1], row=1, col=3)
    fig.update_yaxes(title=None)
    estilo_padrao(fig, altura=200)
    visiveis = aplicar_ordens(fig, ordens, ordem or "padrao", limite)
    fig.update_layout(height=max(200, 30 * visiveis + 70),
                      margin={"l": 10, "r": 20, "t": 40, "b": 10}, bargap=0.25)
    fig.update_annotations(font={"size": 12, "color": CINZA_ESCURO})
    return fig


@protegido
def grafico_empilhado(tabela, rotulo, series, ordem="vitimas", limite=None):
    """
    BARRAS EMPILHADAS horizontais. series = [(coluna, nome, cor), ...].
    A tabela precisa da coluna "vitimas" (soma das séries). Os botões
    "Ordenar por" escolhem a série que define a ordem.
    """
    if tabela.empty:
        return None
    tabela = tabela.reset_index(drop=True)
    rotulos = [str(r) for r in tabela[rotulo]]
    nomes = nomes_unicos(rotulos, 42)
    ordens = {"vitimas": ordenar(nomes, tabela, "vitimas", "mortos")}
    for coluna, _, _ in series:
        ordens[coluna] = ordenar(nomes, tabela, coluna, "vitimas")
    fig = go.Figure()
    for coluna, nome, cor in series:
        fig.add_trace(go.Bar(
            x=tabela[coluna], y=nomes, name=nome, orientation="h", marker_color=cor,
            customdata=[[r, v] for r, v in zip(rotulos, tabela["vitimas"])],
            hovertemplate="%{customdata[0]}<br>%{x:,.0f} " + nome.lower() +
                          " de %{customdata[1]:,.0f} vítimas<extra></extra>",
        ))
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title=None, tickformat=",.0f", fixedrange=True)
    fig.update_yaxes(title=None)
    estilo_padrao(fig, altura=280, legenda=True)
    visiveis = aplicar_ordens(fig, ordens, ordem, limite)
    fig.update_layout(height=max(280, 30 * visiveis + 80))
    return fig


# =============================================================================
# Trechos críticos
# =============================================================================
@protegido
def grafico_bolhas(tabela, medida):
    """MAPA DE BOLHAS - cada bolha é um trecho de 10 km; tamanho = mortos ou acidentes."""
    tabela = tabela.dropna(subset=["latitude", "longitude"])
    tabela = tabela[tabela[medida] > 0]
    if tabela.empty:
        return None
    fig = px.scatter_map(
        tabela, lat="latitude", lon="longitude", size=medida, size_max=30,
        color_discrete_sequence=[VERMELHO if medida == "mortos" else GRAFITE],
        custom_data=["nome", "local", "acidentes", "mortos"],
        zoom=zoom_do_mapa(tabela),
        center={"lat": tabela["latitude"].median(), "lon": tabela["longitude"].median()},
        map_style="carto-positron",
    )
    fig.update_traces(
        marker={"opacity": 0.6},
        hovertemplate=("%{customdata[0]}<br>%{customdata[1]}<br>"
                       "%{customdata[2]:,.0f} acidentes · %{customdata[3]:,.0f} mortos<extra></extra>"),
    )
    estilo_padrao(fig, altura=480)
    fig.update_layout(margin={"l": 0, "r": 0, "t": 0, "b": 0})
    return fig


@protegido
def grafico_perfil(tabela):
    """
    PERFIL DA RODOVIA - acidentes (barras) e mortos (pontos) a cada 10 km.
    Colunas: trecho_km, acidentes, mortos.
    """
    if tabela["acidentes"].sum() == 0:
        return None
    inicio, fim = tabela["trecho_km"], tabela["trecho_km"] + 10
    faixa = [f"km {a} a {b}" for a, b in zip(inicio, fim)]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=inicio + 5, y=tabela["acidentes"], width=9, name="Acidentes", marker_color=GRAFITE,
        customdata=faixa, hovertemplate="%{customdata}<br>%{y:,.0f} acidentes<extra></extra>",
    ), secondary_y=False)
    com_mortes = tabela["mortos"] > 0
    fig.add_trace(go.Scatter(
        x=inicio[com_mortes] + 5, y=tabela.loc[com_mortes, "mortos"], name="Mortos",
        mode="markers", marker={"color": VERMELHO, "size": 9, "line": {"color": "white", "width": 1}},
        customdata=[f for f, m in zip(faixa, com_mortes) if m],
        hovertemplate="%{customdata}<br>%{y:,.0f} mortos<extra></extra>",
    ), secondary_y=True)
    fig.update_xaxes(title="km da rodovia")
    fig.update_yaxes(title="Acidentes", tickformat=",.0f", secondary_y=False)
    fig.update_yaxes(title="Mortos", showgrid=False, rangemode="tozero", secondary_y=True)
    return estilo_padrao(fig, altura=340, legenda=True)


# =============================================================================
# Comparação anual
# =============================================================================
@protegido
def grafico_anos(tabela, valor, nome):
    """LINHAS - uma linha por ano, mês a mês. Colunas: ano, mes e a coluna valor."""
    if tabela.empty or tabela[valor].sum() == 0:
        return None
    tabela = tabela.sort_values(["ano", "mes"]).copy()
    tabela["mes_nome"] = tabela["mes"].map(lambda m: MESES[m - 1])
    tabela["Ano"] = tabela["ano"].astype(str)
    fig = px.line(tabela, x="mes_nome", y=valor, color="Ano", markers=True,
                  color_discrete_map=CORES_ANOS, category_orders={"mes_nome": MESES})
    fig.update_traces(hovertemplate="%{x}: %{y:,.0f} " + nome + "<extra>%{fullData.name}</extra>")
    fig.update_traces(line={"width": 3}, selector={"name": "2026"})
    fig.update_xaxes(title=None)
    fig.update_yaxes(title=None, tickformat=",.0f", rangemode="tozero")
    return estilo_padrao(fig, altura=340, legenda=True)


# =============================================================================
# Apoio à decisão (Onde agir, Ficha do trecho, Metas e avaliação)
# =============================================================================
# Do transparente ao vermelho escuro: as áreas sem acidentes ficam com o mapa limpo
ESCALA_DENSIDADE = [[0, "rgba(227,6,19,0)"], [0.15, "rgba(246,165,169,0.6)"],
                    [0.5, "rgba(227,6,19,0.85)"], [1, "#7a030a"]]


@protegido
def grafico_densidade(grade, raio):
    """MAPA DE CALOR GEOGRÁFICO - mancha mais escura onde a gravidade (UPS) é maior."""
    if grade.empty or grade["ups"].sum() == 0:
        return None
    fig = px.density_map(
        grade, lat="latitude", lon="longitude", z="ups", radius=raio,
        custom_data=["acidentes", "mortos", "ups"],
        color_continuous_scale=ESCALA_DENSIDADE,
        zoom=zoom_do_mapa(grade),
        center={"lat": grade["latitude"].median(), "lon": grade["longitude"].median()},
        map_style="carto-positron",
    )
    fig.update_traces(hovertemplate=("%{customdata[0]:,.0f} acidentes · %{customdata[1]:,.0f} mortos"
                                     "<br>Gravidade: %{customdata[2]:,.0f} UPS<extra></extra>"))
    estilo_padrao(fig, altura=520)
    fig.update_layout(margin={"l": 0, "r": 0, "t": 0, "b": 0}, coloraxis_showscale=False)
    return fig


ESCALA_AREAS = [[0, "#fdf0f0"], [0.2, "#f6a5a9"], [0.55, "#e30613"], [1, "#7a030a"]]
ESCALA_VARIACAO = [[0, "#00632a"], [0.3, "#6fbf8c"], [0.5, "#f5f5f5"], [0.7, "#f6a5a9"], [1, "#b3050f"]]


def teto_da_escala(valores):
    """Topo da escala de cor: o 95º percentil, para uma área muito acima das outras
    (ex.: a capital) não deixar todas as demais com a mesma cor clara."""
    v = [x for x in valores if pd.notna(x) and x > 0]
    if not v:
        return 1
    return float(pd.Series(v).quantile(0.95)) if len(v) >= 5 else float(max(v))


def zoom_dos_limites(lat_min, lat_max, lon_min, lon_max):
    extensao = max(lat_max - lat_min, (lon_max - lon_min) * 0.8, 0.05)
    return min(max(log2(360 / extensao) - 1.15, 2.8), 11)


@protegido
def grafico_mapa_camadas(niveis, nivel_inicial, metricas, linhas, trechos, prioritarios, fatais, grade, raio, vista):
    """
    MAPA POR CAMADAS. niveis = {nível: (geojson, tabela, textos)}; cada nível vira
    uma camada de áreas coloridas (só a escolhida aparece). As outras camadas:
    rodovias por trecho, trechos prioritários, acidentes com morte e mancha de calor.
    layout.meta["mapa"] guarda o que os controles acima do mapa precisam (ver base.html).
    """
    fig = go.Figure()
    meta = {"niveis": {}, "metricas": {}, "nivel": nivel_inicial, "metrica": "ups",
            "camadas": {"rodovias": [], "prioritarios": [], "fatais": [], "calor": []}}
    for chave, (titulo, tipo, _) in metricas.items():
        divergente = tipo == "divergente"
        meta["metricas"][chave] = {"titulo": titulo, "escala": ESCALA_VARIACAO if divergente else ESCALA_AREAS,
                                   "zmin": -100 if divergente else 0}

    dica_area = ("<b>%{customdata[0]}</b><br>%{customdata[1]} acidentes · %{customdata[2]} mortos"
                 "<br>Gravidade: %{customdata[3]} UPS · letalidade %{customdata[4]}"
                 "<br>Variação sobre o ano anterior: %{customdata[5]}"
                 "<br>Causa mais grave: %{customdata[6]}<extra></extra>")
    for nivel, (geojson, tabela, textos) in niveis.items():
        zs = {k: [None if pd.isna(v) else round(float(v), 2) for v in tabela[k]] for k in metricas}
        tetos = {k: (100 if metricas[k][1] == "divergente" else teto_da_escala(tabela[k])) for k in metricas}
        meta["niveis"][nivel] = {"trace": len(fig.data), "z": zs, "zmax": tetos}
        fig.add_trace(go.Choroplethmap(
            geojson=geojson, featureidkey="properties.codarea", locations=list(tabela["codarea"]),
            z=zs["ups"], zmin=0, zmax=tetos["ups"], colorscale=ESCALA_AREAS,
            marker={"opacity": 0.62, "line": {"width": 0.7, "color": "white"}},
            customdata=textos, hovertemplate=dica_area, name=nivel, showlegend=False,
            visible=nivel == nivel_inicial,
            colorbar={"title": {"text": "Gravidade (UPS)", "side": "right"}, "thickness": 12, "len": 0.55,
                      "x": 0.995, "xanchor": "right", "y": 0.5, "bgcolor": "rgba(255,255,255,0.85)"},
        ))

    # Rodovias coloridas por trecho (uma linha por classe de gravidade) + pontos de hover/clique
    for camada in linhas:
        meta["camadas"]["rodovias"].append(len(fig.data))
        fig.add_trace(go.Scattermap(lat=camada["lat"], lon=camada["lon"], mode="lines", name=camada["nome"],
                                    line={"width": 4.5, "color": camada["cor"]}, hoverinfo="skip"))
    if not trechos.empty:
        meta["camadas"]["rodovias"].append(len(fig.data))
        fig.add_trace(go.Scattermap(
            lat=trechos["latitude"], lon=trechos["longitude"], mode="markers", showlegend=False,
            marker={"size": 9, "color": trechos["cor"], "opacity": 0.95}, customdata=trechos["dados"].tolist(),
            hovertemplate=("<b>%{customdata[0]}</b> · %{customdata[1]}<br>%{customdata[2]} acidentes · "
                           "%{customdata[3]} mortos · %{customdata[4]} UPS<br>Clique para abrir a ficha<extra></extra>"),
        ))

    # Acidentes com morte (desligado no início)
    if not fatais.empty:
        meta["camadas"]["fatais"].append(len(fig.data))
        fig.add_trace(go.Scattermap(
            lat=fatais["latitude"], lon=fatais["longitude"], mode="markers", name="Acidente com morte",
            marker={"size": 7, "color": PRETO, "opacity": 0.85}, visible=False,
            customdata=fatais[["local", "rodovia", "mortos"]].values.tolist(),
            hovertemplate="%{customdata[0]}<br>%{customdata[1]}<br>%{customdata[2]} mortos<extra></extra>",
        ))

    # Mancha de calor da gravidade (desligada no início)
    if not grade.empty:
        meta["camadas"]["calor"].append(len(fig.data))
        fig.add_trace(go.Densitymap(
            lat=grade["latitude"], lon=grade["longitude"], z=grade["ups"], radius=raio,
            colorscale=ESCALA_DENSIDADE, showscale=False, visible=False, name="Mancha de calor", hoverinfo="skip",
        ))

    # Trechos prioritários numerados como no ranking (por cima de tudo)
    if not prioritarios.empty:
        meta["camadas"]["prioritarios"].append(len(fig.data))
        fig.add_trace(go.Scattermap(
            lat=prioritarios["latitude"], lon=prioritarios["longitude"], mode="markers+text",
            name="Trecho prioritário (nº do ranking)", text=[str(p) for p in prioritarios["posicao"]],
            textposition="middle center", textfont={"color": "white", "size": 11},
            marker={"size": 22, "color": PRETO, "opacity": 0.95}, customdata=prioritarios["dados"].tolist(),
            hovertemplate=("<b>%{customdata[0]}º · %{customdata[1]}</b><br>%{customdata[2]}<br>"
                           "%{customdata[3]} UPS · %{customdata[4]} mortos<br>Clique para abrir a ficha<extra></extra>"),
        ))

    lat_min, lat_max, lon_min, lon_max = vista
    fig.update_layout(
        map={"style": "carto-positron", "zoom": zoom_dos_limites(*vista),
             "center": {"lat": (lat_min + lat_max) / 2, "lon": (lon_min + lon_max) / 2}},
        meta={"mapa": meta},
    )
    estilo_padrao(fig, altura=620, legenda=True)
    fig.update_layout(margin={"l": 0, "r": 0, "t": 0, "b": 0},
                      legend={"orientation": "v", "x": 0.01, "y": 0.99, "xanchor": "left", "yanchor": "top",
                              "bgcolor": "rgba(255,255,255,0.88)", "bordercolor": CINZA_CLARO, "borderwidth": 1,
                              "font": {"size": 11}})
    return fig


@protegido
def grafico_grupos(grupos):
    """BARRAS - parte da gravidade de cada grupo de causas (quem pode agir)."""
    grupos = [g for g in grupos if g["ups"] > 0]
    if not grupos:
        return None
    grupos = grupos[::-1]  # o maior fica no topo
    fig = go.Figure(go.Bar(
        x=[g["parte_num"] for g in grupos], y=[g["grupo"] for g in grupos], orientation="h",
        marker_color=[g["cor"] for g in grupos],
        customdata=[[g["quem"], g["acidentes"], g["mortos"]] for g in grupos],
        text=[f"{g['parte']} · {g['mortos']:,} mortos".replace(",", ".") for g in grupos],
        textposition="outside", cliponaxis=False,
        hovertemplate=("%{y}: %{x:.1f}% da gravidade<br>%{customdata[1]:,.0f} acidentes · "
                       "%{customdata[2]:,.0f} mortos<br>Quem age: %{customdata[0]}<extra></extra>"),
    ))
    fig.update_xaxes(title=None, showticklabels=False, showgrid=False,
                     range=[0, max(g["parte_num"] for g in grupos) * 1.45])
    fig.update_yaxes(title=None)
    estilo_padrao(fig, altura=max(240, 42 * len(grupos) + 40))
    fig.update_layout(margin={"r": 20})
    return fig


@protegido
def grafico_meta(tabela, nome, ano, ano_base):
    """LINHAS ACUMULADAS - ano atual x ano base x meta. Colunas: mes, atual, base, meta (acumulados)."""
    if tabela["base"].sum() == 0 and tabela["atual"].sum() == 0:
        return None
    x = [MESES[m - 1] for m in tabela["mes"]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=tabela["base"], name=f"{ano_base}", mode="lines",
                             line={"color": CINZA, "width": 2},
                             hovertemplate="%{x}: %{y:,.0f} " + nome + f" em {ano_base}<extra></extra>"))
    fig.add_trace(go.Scatter(x=x, y=tabela["meta"], name="Meta", mode="lines",
                             line={"color": VERDE, "width": 2, "dash": "dash"},
                             hovertemplate="%{x}: meta de até %{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=x, y=tabela["atual"], name=f"{ano}", mode="lines+markers",
                             line={"color": VERMELHO, "width": 3},
                             marker={"size": 7, "line": {"color": "white", "width": 1}},
                             hovertemplate="%{x}: %{y:,.0f} " + nome + f" em {ano}<extra></extra>"))
    fig.update_xaxes(title=None, categoryorder="array", categoryarray=MESES)
    fig.update_yaxes(title=None, tickformat=",.0f", rangemode="tozero")
    return estilo_padrao(fig, altura=360, legenda=True)


@protegido
def grafico_antes_depois(serie, coluna, nome, resultado, intervencao):
    """LINHA MENSAL com o período antes (cinza) e depois (vermelho) da intervenção."""
    if serie.empty:
        return None
    x = serie.index.to_timestamp()
    fig = go.Figure(go.Scatter(
        x=x, y=serie[coluna], mode="lines+markers", line={"color": GRAFITE, "width": 2},
        marker={"size": 5}, hovertemplate="%{x|%m/%Y}: %{y:,.0f} " + nome.lower() + "<extra></extra>",
    ))
    if resultado:
        meio = pd.Timedelta(days=15)
        fig.add_vrect(x0=resultado["inicio_antes"].to_timestamp() - meio,
                      x1=resultado["fim_antes"].to_timestamp() + meio,
                      fillcolor=CINZA_CLARO, opacity=0.35, line_width=0,
                      annotation_text="Antes", annotation_position="top left")
        fig.add_vrect(x0=resultado["inicio_depois"].to_timestamp() - meio,
                      x1=resultado["fim_depois"].to_timestamp() + meio,
                      fillcolor=VERMELHO_CLARO, opacity=0.35, line_width=0,
                      annotation_text="Depois", annotation_position="top left")
        fig.add_vline(x=intervencao.to_timestamp(), line_color=VERMELHO, line_dash="dot")
    fig.update_xaxes(title=None, dtick="M3", tickformat="%m/%Y")
    fig.update_yaxes(title=None, tickformat=",.0f", rangemode="tozero")
    return estilo_padrao(fig, altura=340)


# =============================================================================
# Conversão para HTML
# =============================================================================
def botoes_de_ordem(meta):
    """Botões "Ordenar por" de um gráfico ordenável (o clique é tratado no base.html)."""
    botoes = []
    for chave in meta["ordens"]:
        pressionado = "true" if chave == meta["ativa"] else "false"
        dica = f' title="{escape(DICA_ORDEM[chave])}"' if chave in DICA_ORDEM else ""
        botoes.append(f'<button type="button" class="botao-ordem" data-ordem="{chave}" '
                      f'aria-pressed="{pressionado}"{dica}>{ROTULOS_ORDEM.get(chave, chave)}</button>')
    return ('<div class="mb-1 flex flex-wrap items-center gap-1 print:hidden">'
            '<span class="mr-1 text-xs text-pm-cinza">Ordenar por:</span>' + "".join(botoes) + "</div>")


def html_de(fig):
    """Converte um gráfico em HTML (ou devolve o aviso de sem dados / erro)."""
    if fig is None:
        return AVISO_SEM_DADOS
    if isinstance(fig, str):  # mensagem de erro vinda de @protegido
        return fig
    div = plot(fig, output_type="div", include_plotlyjs=False, config=CONFIG_PLOTLY)
    meta = fig.layout.meta
    if meta and "ordens" in meta and len(meta["ordens"]) > 1:
        return f'<div class="ordenavel">{botoes_de_ordem(meta)}{div}</div>'
    return div


def para_html(figuras):
    """Converte {nome: gráfico} em {nome: HTML}."""
    return {nome: html_de(fig) for nome, fig in figuras.items()}
