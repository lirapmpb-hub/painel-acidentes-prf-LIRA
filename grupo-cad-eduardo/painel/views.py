from urllib.parse import urlencode

from django.conf import settings
from django.http import Http404
from django.shortcuts import render
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ---------- 1. DADOS (carregados uma única vez, quando o servidor liga) ----------
df = pd.read_csv(settings.BASE_DIR / "DATA" / "datatran2026.csv",
                 sep=";", encoding="latin-1", decimal=",")

df["mes"] = pd.to_datetime(df["data_inversa"]).dt.month

# Primeira e última data da base (usadas na seção "Metodologia e limitações")
DATA_INICIO = pd.to_datetime(df["data_inversa"]).min().strftime("%d/%m/%Y")
DATA_FIM = pd.to_datetime(df["data_inversa"]).max().strftime("%d/%m/%Y")
df["hora"] = df["horario"].str.slice(0, 2).astype(int)
df["dia"] = df["dia_semana"].map({
    "segunda-feira": "Seg", "terça-feira": "Ter", "quarta-feira": "Qua",
    "quinta-feira": "Qui", "sexta-feira": "Sex", "sábado": "Sáb", "domingo": "Dom"})

UFS = sorted(df["uf"].unique())

# Nome por extenso das 27 UFs (usado no cabeçalho)
NOMES_UF = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo",
    "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina",
    "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
}
# Preposição certa antes do nome do estado: "da Paraíba", "do Ceará", "de Pernambuco"
PREPOSICAO_UF = {uf: "da" for uf in ["BA", "PB"]}
PREPOSICAO_UF.update({uf: "de" for uf in ["AL", "GO", "MG", "PE", "RO", "RR", "SC", "SP", "SE"]})
# as demais UFs usam "do" (do Acre, do Ceará, do Rio de Janeiro...)

# Municípios de cada UF, em ordem alfabética (usados no filtro "Município")
MUNICIPIOS = {uf: sorted(nomes.unique()) for uf, nomes in df.groupby("uf")["municipio"]}
MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
         "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
ULTIMO_MES = int(df["mes"].max())          # a base vai até setembro
DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
df["acidentes"] = 1                         # cada linha da base é um acidente

# O que os gráficos medem: o usuário escolhe no seletor "Ver por"
MEDIDAS = {
    "acidentes": {"nome": "Acidentes", "singular": "acidente", "plural": "acidentes"},
    "mortos": {"nome": "Mortos", "singular": "morto", "plural": "mortos"},
    "feridos": {"nome": "Feridos", "singular": "ferido", "plural": "feridos"},
}
TODAS = ["acidentes", "mortos", "feridos"]

# ---------- 2. AS ABAS DO PAINEL (endereço, nome no menu, título, explicação) ----------
ABAS = [
    {"slug": "ranking", "menu": "Ranking dos estados",
     "titulo": "1. Ranking dos estados",
     "descricao": "Gravidade dos acidentes em cada UF: vítimas a cada 100 acidentes.",
     "como_ler": "Cada barra é um estado. Quanto maior a barra, mais vítimas a cada 100 acidentes. A linha tracejada é a média do Brasil. O estado escolhido no filtro aparece destacado."},
    {"slug": "mensal", "menu": "Evolução mensal",
     "titulo": "2. Evolução mensal",
     "descricao": "Total de cada mês do período.",
     "como_ler": "Cada barra é um mês. Quanto mais alta, maior o número. Passe o mouse para ver acidentes, mortos e feridos do mês."},
    {"slug": "causas", "menu": "Causas",
     "titulo": "3. Principais causas dos acidentes",
     "descricao": "As 10 causas com os maiores números.",
     "como_ler": "Cada barra é uma causa, da maior (no topo) para a menor. Passe o mouse para ver acidentes, mortos e feridos."},
    {"slug": "horarios", "menu": "Dia e horário",
     "titulo": "4. Dia da semana e horário",
     "descricao": "Totais por dia da semana e hora do dia.",
     "como_ler": "Cada quadradinho é um dia da semana (linha) em uma hora (coluna). Quanto mais escuro, maior o número naquele momento."},
    {"slug": "tipos", "menu": "Tipos mais graves",
     "titulo": "5. Tipos de acidente mais graves",
     "descricao": "Vítimas a cada 100 acidentes de cada tipo.",
     "como_ler": "Cada barra é um tipo de acidente. Quanto maior, mais vítimas a cada 100 acidentes daquele tipo. Passe o mouse para ver acidentes, mortos e feridos."},
    {"slug": "trechos", "menu": "Trechos críticos",
     "titulo": "6. Trechos críticos das BRs",
     "descricao": "Os 10 trechos de 5 km com os maiores números.",
     "como_ler": "Cada barra é um trecho de 5 km de uma BR. Passe o mouse para ver o município, os acidentes, os mortos e os feridos."},
    {"slug": "fatores", "menu": "Fatores de risco",
     "titulo": "7. Fatores de risco",
     "descricao": "Gravidade dos acidentes conforme o tipo de pista, a zona, o horário e o tempo.",
     "como_ler": "Cada par de barras compara duas situações. Quanto maior a barra, mais vítimas a cada 100 acidentes naquela situação. São associações, não causas isoladas: os fatores se sobrepõem."},
]
SLUGS = [a["slug"] for a in ABAS]

# ---------- 3. IDENTIDADE VISUAL ----------
AZUL = "#0F2540"
DOURADO = "#C9A227"
VERMELHO = "#B42318"


def milhar(n):
    """12345 vira 12.345 (padrão brasileiro)."""
    return f"{int(n):,}".replace(",", ".")


def decimal(n):
    """3.456 vira 3,5."""
    return f"{n:.1f}".replace(".", ",")


def qtd(n, medida):
    """Número com a palavra certa: 1 morto, 2 mortos."""
    m = MEDIDAS[medida]
    return f"{milhar(n)} {m['singular'] if n == 1 else m['plural']}"


def outros(linha, medida):
    """Os outros dois números da linha: se a medida é mortos, mostra acidentes e feridos."""
    partes = [qtd(linha[m], m) for m in TODAS if m != medida]
    return " e ".join(partes)


def cautela(frase, valor):
    """Se o número citado na frase for menor que 10, avisa que são poucos casos."""
    if valor < 10:
        frase += " Poucos casos: interprete com cautela."
    return frase


def somar(dados, chaves):
    """Soma acidentes, mortos e feridos por grupo (como uma tabela dinâmica)."""
    return dados.groupby(chaves)[TODAS].sum()


def quebrar(texto, limite=30):
    """Quebra um nome longo em linhas de até 30 letras (para os rótulos)."""
    linhas, atual = [], ""
    for palavra in texto.split():
        if atual and len(atual) + len(palavra) + 1 > limite:
            linhas.append(atual)
            atual = palavra
        else:
            atual = (atual + " " + palavra).strip()
    linhas.append(atual)
    return "<br>".join(linhas)


def ler_mes(valor, padrao):
    try:
        mes = int(valor)
    except (TypeError, ValueError):
        return padrao
    return mes if 1 <= mes <= ULTIMO_MES else padrao


def padronizar(fig, altura=480):
    """Mesmo acabamento para todos os gráficos."""
    fig.update_layout(
        template="plotly_white", height=altura, separators=",.",
        margin=dict(l=10, r=30, t=10, b=10),
        font=dict(family="Inter, Arial, sans-serif", size=13, color="#1E293B"),
        legend=dict(orientation="h", y=-0.2, title_text=""),
        plot_bgcolor="white", paper_bgcolor="white", bargap=0.35,
    )
    # visual "clean": linhas de grade bem claras, sem linhas de eixo
    fig.update_xaxes(gridcolor="#EEF1F5", zeroline=False, showline=False,
                     title_font=dict(size=12, color="#64748B"), tickfont=dict(color="#64748B"))
    fig.update_yaxes(gridcolor="#EEF1F5", zeroline=False, showline=False,
                     title_font=dict(size=12, color="#64748B"), tickfont=dict(color="#334155"))
    return fig.to_html(full_html=False, include_plotlyjs="cdn",
                       config={"displayModeBar": False, "responsive": True})


def barras(tabela, x, y, cor, texto, hover, rotulos):
    """Gráfico de barras horizontais no padrão do painel."""
    fig = px.bar(tabela, x=x, y=y, orientation="h", text=x,
                 hover_data=hover, labels=rotulos)
    fig.update_traces(marker_color=cor, texttemplate=texto,
                      textposition="outside", cliponaxis=False)
    fig.update_yaxes(ticksuffix="  ")
    return fig


# ---------- 4. OS 5 GRÁFICOS (cada função devolve o gráfico e a frase) ----------
# "medida" é o que o usuário escolheu ver: acidentes, mortos ou feridos.
# Em todos os gráficos, passar o mouse mostra os três números.
HOVER = {"acidentes": ":,.0f", "mortos": ":,.0f", "feridos": ":,.0f"}
ROTULOS = {"acidentes": "Acidentes", "mortos": "Mortos", "feridos": "Feridos"}


def grafico_mensal(dados, medida, mes_ini, mes_fim):
    mensal = (somar(dados, "mes")
                   .reindex(range(mes_ini, mes_fim + 1), fill_value=0)
                   .reset_index())
    mensal["Mês"] = mensal["mes"].map(lambda m: MESES[m - 1])
    cor = VERMELHO if medida == "mortos" else AZUL
    fig = px.bar(mensal, x="Mês", y=medida, text=medida, hover_data=HOVER,
                 labels=ROTULOS)
    fig.update_traces(marker_color=cor, texttemplate="%{text:,.0f}",
                      textposition="outside", cliponaxis=False)
    fig.update_xaxes(title_text="")
    pico = mensal.loc[mensal[medida].idxmax()]
    if mes_ini == mes_fim:
        frase = (f"Em {pico['Mês']} foram {qtd(pico['acidentes'], 'acidentes')}, "
                 f"com {qtd(pico['mortos'], 'mortos')} e {qtd(pico['feridos'], 'feridos')}. "
                 f"Amplie o período para comparar meses.")
        frase = cautela(frase, pico[medida])
    elif pico[medida] == 0:
        frase = f"Não houve {MEDIDAS[medida]['plural']} no período."
    else:
        frase = (f"{pico['Mês']} foi o mês com mais {MEDIDAS[medida]['plural']} "
                 f"({milhar(pico[medida])}). Naquele mês também houve "
                 f"{outros(pico, medida)}.")
        frase = cautela(frase, pico[medida])
    return fig, frase


def grafico_causas(dados, medida, *_):
    causas = (somar(dados, "causa_acidente")
                   .sort_values([medida, "acidentes"], ascending=False).head(10)
                   .iloc[::-1].reset_index())
    causas["rotulo"] = causas["causa_acidente"].map(quebrar)
    cor = VERMELHO if medida == "mortos" else AZUL
    fig = barras(causas, medida, "rotulo", cor, "%{text:,.0f}", HOVER,
                 {**ROTULOS, "rotulo": ""})
    topo = causas.iloc[-1]
    total = dados[medida].sum()
    frase = (f"A causa com mais {MEDIDAS[medida]['plural']} é \"{topo['causa_acidente']}\": "
             f"{qtd(topo[medida], medida)} "
             f"({decimal(topo[medida] / total * 100) if total else '0,0'}% do total), "
             f"além de {outros(topo, medida)}.")
    return fig, cautela(frase, topo[medida])


def grafico_horarios(dados, medida, *_):
    calor = (dados.pivot_table(index="dia", columns="hora", values=medida,
                               aggfunc="sum", fill_value=0)
                  .reindex(index=DIAS, columns=range(24), fill_value=0))
    fig = px.imshow(calor, aspect="auto",
                    color_continuous_scale=["#F1F5F9", DOURADO, VERMELHO],
                    labels={"x": "Hora do dia", "y": "", "color": MEDIDAS[medida]["nome"]})
    fig.update_xaxes(dtick=2, ticksuffix="h")
    dia, hora = calor.stack().idxmax()
    total = calor.values.sum()
    fds = calor.loc[["Sáb", "Dom"]].values.sum()
    frase = (f"O momento com mais {MEDIDAS[medida]['plural']} é {dia}, entre {hora}h e {hora + 1}h "
             f"({milhar(calor.loc[dia, hora])}). Os fins de semana concentram "
             f"{decimal(fds / total * 100) if total else '0,0'}% dos {MEDIDAS[medida]['plural']}.")
    return fig, cautela(frase, calor.loc[dia, hora])


# Faixas do dia para o resumo abaixo do mapa de calor (hora final não entra)
FAIXAS = [("Madrugada", 0, 6), ("Manhã", 6, 12), ("Tarde", 12, 18), ("Noite", 18, 24)]


def resumo_faixas(dados, medida):
    """Total e percentual da medida escolhida em cada faixa do dia."""
    total = dados[medida].sum()
    resumo = []
    for nome, ini, fim in FAIXAS:
        valor = dados.loc[(dados["hora"] >= ini) & (dados["hora"] < fim), medida].sum()
        resumo.append({
            "nome": nome, "horas": f"{ini}h–{fim}h",
            "total": qtd(valor, medida),
            "percentual": decimal(valor / total * 100) if total else "0,0",
        })
    return resumo


def grafico_tipos(dados, medida, *_):
    # Gravidade: quantas vítimas a cada 100 acidentes de cada tipo
    vitima = "feridos" if medida == "feridos" else "mortos"
    tipos = somar(dados, "tipo_acidente")
    total = len(dados)
    minimo = max(10, int(total * 0.005))   # ignora tipos com poucos casos
    if (tipos["acidentes"] >= minimo).any():
        tipos = tipos[tipos["acidentes"] >= minimo]
    tipos["indice"] = (tipos[vitima] / tipos["acidentes"] * 100).round(1)
    tipos = tipos.sort_values("indice").tail(10).reset_index()
    nome_indice = f"{MEDIDAS[vitima]['nome']} a cada 100 acidentes"
    fig = barras(tipos, "indice", "tipo_acidente",
                 VERMELHO if vitima == "mortos" else AZUL, "%{text:.1f}", HOVER,
                 {**ROTULOS, "indice": nome_indice, "tipo_acidente": ""})
    media = dados[vitima].sum() / total * 100
    pior = tipos.iloc[-1]
    if pior["indice"] == 0:
        frase = f"Nenhum tipo de acidente teve {MEDIDAS[vitima]['plural']} no período escolhido."
    else:
        frase = (f"\"{pior['tipo_acidente']}\" é o tipo mais grave: "
                 f"{decimal(pior['indice'])} {MEDIDAS[vitima]['plural']} a cada 100 acidentes, "
                 f"{decimal(pior['indice'] / media)} vezes a média ({decimal(media)}). "
                 f"No total, foram {qtd(pior['acidentes'], 'acidentes')}, "
                 f"{qtd(pior['mortos'], 'mortos')} e {qtd(pior['feridos'], 'feridos')}.")
    if total < 100:
        frase += " Atenção: poucos acidentes no filtro, interprete com cautela."
    elif pior["indice"] > 0:
        # o índice vem de poucas vítimas? então avisa
        frase = cautela(frase, pior[vitima])
    return fig, frase


def grafico_trechos(dados, medida, *_):
    trechos = dados.assign(km_ini=(dados["km"] // 5 * 5).astype(int))
    cidades = trechos.groupby(["br", "km_ini"])["municipio"].agg(lambda m: m.mode().iat[0])
    trechos = (somar(trechos, ["br", "km_ini"]).join(cidades)
                      .sort_values([medida, "acidentes"], ascending=False)
                      .head(10).reset_index())
    trechos["trecho"] = trechos.apply(
        lambda t: f"BR-{t['br']} · km {t['km_ini']} a {t['km_ini'] + 5}", axis=1)
    trechos["cidade"] = trechos["municipio"].str.title()
    trechos = trechos.iloc[::-1]          # maior no topo do gráfico
    cor = VERMELHO if medida == "mortos" else AZUL
    fig = barras(trechos, medida, "trecho", cor, "%{text:,.0f}",
                 {"cidade": True, **HOVER},
                 {**ROTULOS, "trecho": "", "cidade": "Município"})
    t1 = trechos.iloc[-1]
    frase = (f"O trecho com mais {MEDIDAS[medida]['plural']} é a BR-{t1['br']}, entre os km "
             f"{t1['km_ini']} e {t1['km_ini'] + 5} ({t1['cidade']}): "
             f"{qtd(t1[medida], medida)}, além de {outros(t1, medida)}.")
    return fig, cautela(frase, t1[medida])


# Pares comparados na aba "Fatores de risco":
# (nome do par, coluna do CSV, [(valor no CSV, rótulo), (valor no CSV, rótulo)])
PARES = [
    ("Pista", "tipo_pista", [("Simples", "Pista simples"), ("Dupla", "Pista dupla")]),
    ("Zona", "uso_solo", [("Não", "Zona rural"), ("Sim", "Zona urbana")]),
    ("Horário", "fase_dia", [("Plena Noite", "Noite"), ("Pleno dia", "Dia")]),
    ("Tempo", "condicao_metereologica", [("Chuva", "Chuva"), ("Céu Claro", "Céu claro")]),
]
MINIMO_FATORES = 30     # situação com menos acidentes que isso não entra no gráfico


def grafico_fatores(dados, medida, *_):
    # Mesma regra do grafico_tipos: feridos se "Ver por" = feridos; senão, mortos
    vitima = "feridos" if medida == "feridos" else "mortos"
    plural = MEDIDAS[vitima]["plural"]

    # 1) índice de cada situação; o par só entra se os dois lados tiverem >= 30 acidentes
    pares = {}
    for grupo, coluna, lados in PARES:
        linhas = []
        for valor, rotulo in lados:
            parte = dados[dados[coluna] == valor]
            n = len(parte)
            if n < MINIMO_FATORES:
                break
            vitimas = int(parte[vitima].sum())
            linhas.append({"grupo": grupo, "rotulo": rotulo, "acidentes": n,
                           "vitimas": vitimas, "indice": round(vitimas / n * 100, 1)})
        if len(linhas) == 2:
            pares[grupo] = linhas

    if not pares:
        frase = (f"Dados insuficientes: nenhuma situação teve ao menos {MINIMO_FATORES} "
                 f"acidentes nos dois lados do par com o filtro escolhido.")
        return go.Figure(), frase

    # 2) gráfico: barras horizontais, agrupadas por par; a mais grave do par em vermelho
    barras_ = [l for g in pares.values() for l in g]
    cores = []
    for g in pares.values():
        maior = max(l["indice"] for l in g)
        cores += [VERMELHO if l["indice"] == maior and g[0]["indice"] != g[1]["indice"]
                  else AZUL for l in g]
    fig = go.Figure(go.Bar(
        x=[l["indice"] for l in barras_],
        y=[[l["grupo"] for l in barras_], [l["rotulo"] for l in barras_]],
        orientation="h", marker_color=cores,
        text=[l["indice"] for l in barras_], texttemplate="%{x:.1f}",
        textposition="outside", cliponaxis=False,
        customdata=[[l["rotulo"], l["acidentes"], l["vitimas"]] for l in barras_],
        hovertemplate=("<b>%{customdata[0]}</b><br>"
                       f"{MEDIDAS[vitima]['nome']} a cada 100 acidentes: " "%{x:.1f}<br>"
                       "Acidentes: %{customdata[1]:,.0f}<br>"
                       f"{MEDIDAS[vitima]['nome']}: " "%{customdata[2]:,.0f}<extra></extra>"),
    ))
    fig.update_yaxes(autorange="reversed", ticksuffix="  ")   # primeiro par no topo
    fig.update_xaxes(title_text=f"{MEDIDAS[vitima]['nome']} a cada 100 acidentes")

    # 3) frase, só com os pares que sobraram
    def comparar(grupo, inicio, meio, fim):
        a, b = pares[grupo]
        return f"{inicio}{decimal(a['indice'])}{meio}{decimal(b['indice'])}{fim}"

    partes = []
    if "Pista" in pares:
        a, b = pares["Pista"]
        vezes = (f" ({decimal(a['indice'] / b['indice'])} vezes mais)"
                 if b["indice"] and a["indice"] > b["indice"] else "")
        partes.append(f"Em pista simples há {decimal(a['indice'])} {plural} a cada 100 acidentes, "
                      f"contra {decimal(b['indice'])} em pista dupla{vezes}.")
    outras = []
    if "Zona" in pares:
        outras.append(comparar("Zona", "na zona rural, ", " contra ", " na urbana"))
    if "Horário" in pares:
        outras.append(comparar("Horário", "à noite, ", " contra ", " de dia"))
    if outras:
        texto = "; ".join(outras)
        if "Pista" not in pares:
            texto += f" ({plural} a cada 100 acidentes)"
        partes.append(texto[0].upper() + texto[1:] + ".")
    if "Tempo" in pares:
        a, b = pares["Tempo"]
        if abs(a["indice"] - b["indice"]) < 1.0:
            partes.append("Chuva e céu claro têm índices parecidos.")
        else:
            partes.append(comparar("Tempo", "Com chuva, ", " contra ", " com céu claro."))
    frase = " ".join(partes)

    # aviso de poucos casos (regra do ponto 1): menor nº de vítimas entre as situações
    return fig, cautela(frase, min(l["vitimas"] for l in barras_))


MINIMO_RANKING = 200    # UF com menos acidentes que isso ganha " *" (poucos casos)
NOTA_RANKING = f"* Menos de {MINIMO_RANKING} acidentes no período: interprete com cautela."


def no_estado(uf):
    """"na Paraíba", "no Ceará", "em Pernambuco"."""
    return {"da": "na", "do": "no", "de": "em"}[PREPOSICAO_UF.get(uf, "do")] + " " + NOMES_UF.get(uf, uf)


def grafico_ranking(dados, medida, mes_ini, mes_fim, uf=""):
    # "dados" aqui é a base filtrada SÓ pelo período (todas as UFs); "uf" só destaca a barra
    vitima = "feridos" if medida == "feridos" else "mortos"
    plural = MEDIDAS[vitima]["plural"]
    tabela = somar(dados, "uf")
    tabela["indice_exato"] = tabela[vitima] / tabela["acidentes"] * 100
    tabela = tabela.sort_values("indice_exato", ascending=False).reset_index()  # desempate sem arredondar
    tabela["indice"] = tabela["indice_exato"].round(1)
    tabela["rotulo"] = tabela["uf"] + tabela["acidentes"].map(lambda n: " *" if n < MINIMO_RANKING else "")
    tabela["nome"] = tabela["uf"].map(lambda u: NOMES_UF.get(u, u))
    media = dados[vitima].sum() / len(dados) * 100

    fig = go.Figure(go.Bar(
        x=tabela["indice"].tolist(), y=tabela["rotulo"].tolist(), orientation="h",
        marker_color=[VERMELHO if u == uf else AZUL for u in tabela["uf"]],
        texttemplate="%{x:.1f}", textposition="outside", cliponaxis=False,
        customdata=tabela[["nome", "acidentes", "mortos", "feridos"]].values.tolist(),
        hovertemplate=("<b>%{customdata[0]}</b><br>"
                       f"{MEDIDAS[vitima]['nome']} a cada 100 acidentes: " "%{x:.1f}<br>"
                       "Acidentes: %{customdata[1]:,.0f}<br>"
                       "Mortos: %{customdata[2]:,.0f}"
                       + ("<br>Feridos: %{customdata[3]:,.0f}" if vitima == "feridos" else "")
                       + "<extra></extra>"),
    ))
    fig.add_vline(x=media, line_dash="dash", line_color="#64748B", line_width=1.5,
                  annotation_text=f"Brasil: {decimal(media)}", annotation_position="top",
                  annotation_font=dict(size=12, color="#475569"))
    fig.update_yaxes(autorange="reversed", ticksuffix="  ")   # o mais grave no topo
    fig.update_xaxes(title_text=f"{MEDIDAS[vitima]['nome']} a cada 100 acidentes")

    n = len(tabela)
    if uf in set(tabela["uf"]):
        linha = tabela[tabela["uf"] == uf].iloc[0]
        posicao = int(tabela.index[tabela["uf"] == uf][0]) + 1
        if linha["indice_exato"] > media:
            lado = "acima"
        elif linha["indice_exato"] < media:
            lado = "abaixo"
        else:
            lado = "igual à"
        frase = (f"{linha['nome']} ocupa a {posicao}ª posição entre {n} estados, com "
                 f"{decimal(linha['indice'])} {plural} a cada 100 acidentes, "
                 f"{lado} da média do Brasil ({decimal(media)}).").replace("igual à da", "igual à")
    else:
        primeiro, ultimo = tabela.iloc[0], tabela.iloc[-1]
        frase = (f"{primeiro['nome']} tem o maior índice: {decimal(primeiro['indice'])} {plural} "
                 f"a cada 100 acidentes, contra {decimal(ultimo['indice'])} {no_estado(ultimo['uf'])}. "
                 f"A média do Brasil é {decimal(media)}.")
    return fig, frase


GRAFICOS = {"ranking": grafico_ranking, "mensal": grafico_mensal, "causas": grafico_causas,
            "horarios": grafico_horarios, "tipos": grafico_tipos,
            "trechos": grafico_trechos, "fatores": grafico_fatores}


# ---------- 5. A PÁGINA (a mesma função serve a página principal e as 5 abas) ----------
def index(request, aba="inicio"):
    if aba != "inicio" and aba not in SLUGS:
        raise Http404("Aba não encontrada")

    # 5.1 Filtros escolhidos na tela (validados)
    uf = request.GET.get("uf", "")
    if uf not in UFS:
        uf = ""
    mes_ini = ler_mes(request.GET.get("mes_ini"), 1)
    mes_fim = ler_mes(request.GET.get("mes_fim"), ULTIMO_MES)
    if mes_ini > mes_fim:
        mes_ini, mes_fim = mes_fim, mes_ini
    medida = request.GET.get("medida", "acidentes")
    if medida not in MEDIDAS:
        medida = "acidentes"
    # o município só vale junto com a UF (há nomes repetidos em UFs diferentes)
    municipio = request.GET.get("municipio", "")
    if not uf or municipio not in MUNICIPIOS.get(uf, []):
        municipio = ""

    dados = df[(df["mes"] >= mes_ini) & (df["mes"] <= mes_fim)]
    base_periodo = dados                 # todas as UFs no período (usada pelo Ranking)
    if uf:
        dados = dados[dados["uf"] == uf]
    dados_uf = dados                     # a UF inteira (para comparar com o município)
    if municipio:
        dados = dados[dados["municipio"] == municipio]

    if municipio:
        lugar = f"{municipio.title()} ({uf})"
    else:
        lugar = NOMES_UF.get(uf, uf) if uf else "Brasil"
    periodo = (MESES[mes_ini - 1] if mes_ini == mes_fim
               else MESES[mes_ini - 1] + " a " + MESES[mes_fim - 1]) + " de 2026"

    # 5.2 Indicadores (cartões)
    acidentes = len(dados)
    mortos = int(dados["mortos"].sum())
    feridos = int(dados["feridos"].sum())
    graves = int(dados["feridos_graves"].sum())
    gravidade = mortos / acidentes * 100 if acidentes else 0

    contexto = {
        "aba": aba, "abas": ABAS,
        "medidas": MEDIDAS, "medida": medida,
        "ufs": UFS, "uf": uf,
        "municipios": MUNICIPIOS.get(uf, []) if uf else [], "municipio": municipio,
        "meses": list(enumerate(MESES[:ULTIMO_MES], start=1)),
        "mes_ini": mes_ini, "mes_fim": mes_fim,
        "lugar": lugar, "periodo": periodo,
        # mantém os filtros ao trocar de aba
        "consulta": urlencode({"uf": uf, "municipio": municipio, "mes_ini": mes_ini,
                               "mes_fim": mes_fim, "medida": medida}),
        "kpi_acidentes": milhar(acidentes),
        "kpi_mortos": milhar(mortos),
        "kpi_feridos": milhar(feridos),
        "kpi_graves": milhar(graves),
        "kpi_gravidade": decimal(gravidade),
        "sem_dados": acidentes == 0,
        # metodologia: período coberto e tamanho da base, calculados dos dados
        "data_inicio": DATA_INICIO, "data_fim": DATA_FIM,
        "total_registros": milhar(len(df)),
    }

    # 5.2.1 Comparação com o Brasil no mesmo período (só quando há UF escolhida)
    if uf:
        brasil = df[(df["mes"] >= mes_ini) & (df["mes"] <= mes_fim)]
        br_acidentes = len(brasil)
        br_mortos = int(brasil["mortos"].sum())
        br_feridos = int(brasil["feridos"].sum())

        def parte(valor, total):
            """Participação da UF no Brasil, em %."""
            return decimal(valor / total * 100) if total else "0,0"

        contexto["br"] = {
            "acidentes": f"{parte(acidentes, br_acidentes)}% do Brasil ({milhar(br_acidentes)})",
            "mortos": f"{parte(mortos, br_mortos)}% do Brasil ({milhar(br_mortos)})",
            "feridos": f"{parte(feridos, br_feridos)}% do Brasil ({milhar(br_feridos)})",
            "gravidade": f"Brasil: {decimal(br_mortos / br_acidentes * 100) if br_acidentes else '0,0'}",
        }

        # com município: compara também com a UF inteira (ex.: "29,7% da Paraíba")
        if municipio:
            uf_acidentes = len(dados_uf)
            uf_mortos = int(dados_uf["mortos"].sum())
            uf_feridos = int(dados_uf["feridos"].sum())
            nome_uf = NOMES_UF.get(uf, uf)
            de_uf = f"{PREPOSICAO_UF.get(uf, 'do')} {nome_uf}"
            contexto["br"].update({
                "uf_acidentes": f"{parte(acidentes, uf_acidentes)}% {de_uf}",
                "uf_mortos": f"{parte(mortos, uf_mortos)}% {de_uf}",
                "uf_feridos": f"{parte(feridos, uf_feridos)}% {de_uf}",
                "uf_gravidade": f"{nome_uf}: {decimal(uf_mortos / uf_acidentes * 100) if uf_acidentes else '0,0'}",
            })
    if acidentes == 0:
        return render(request, "painel/index.html", contexto)

    def desenhar(slug):
        """O Ranking usa todas as UFs do período (a UF só destaca a barra);
        as demais abas usam os dados filtrados por UF e município."""
        if slug == "ranking":
            return grafico_ranking(base_periodo, medida, mes_ini, mes_fim, uf=uf)
        return GRAFICOS[slug](dados, medida, mes_ini, mes_fim)

    if aba == "inicio":
        # 5.3 Página principal: um resumo de cada aba, com a frase de cada gráfico
        resumo = []
        for a in ABAS:
            _, frase = desenhar(a["slug"])
            resumo.append({**a, "frase": frase})
        contexto["resumo"] = resumo
    else:
        # 5.4 Uma aba: desenha só o gráfico dela, em tamanho grande
        fig, frase = desenhar(aba)
        contexto["atual"] = next(a for a in ABAS if a["slug"] == aba)
        contexto["grafico"] = padronizar(fig, altura=750 if aba == "ranking" else 480)
        if aba == "ranking" and (somar(base_periodo, "uf")["acidentes"] < MINIMO_RANKING).any():
            contexto["nota"] = NOTA_RANKING
        contexto["frase"] = frase
        if aba == "horarios":
            contexto["faixas"] = resumo_faixas(dados, medida)
            contexto["nome_medida"] = MEDIDAS[medida]["nome"]

    return render(request, "painel/index.html", contexto)