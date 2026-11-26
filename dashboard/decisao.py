"""
Cálculos de apoio à decisão: onde, quando e o que fazer.

- UPS: gravidade ponderada de cada acidente (padrão do DENATRAN), usada para
  priorizar trechos em vez de contar só acidentes.
- Ranking de trechos com tendência em relação ao mesmo período do ano anterior.
- Janelas de risco: dia da semana + faixa de 3 horas.
- Causas agrupadas por quem pode agir (fiscalização, órgão da via, educação...).
- Resumo executivo e recomendações em texto, gerados a partir dos números.
"""
import numpy as np
import pandas as pd
from django.utils.html import format_html

from .calculos import decimal, numero, percentual, variacao
from .filtros import recortar

# =============================================================================
# UPS - Unidade Padrão de Severidade (DENATRAN)
# =============================================================================
PESO_SEM_VITIMAS, PESO_FERIDOS, PESO_PEDESTRE, PESO_FATAL = 1, 4, 6, 13
PEDESTRE = "Atropelamento de Pedestre"


def ups(df):
    """Peso de cada acidente: 1 sem vítimas, 4 com feridos, 6 com feridos e pedestre, 13 com mortos."""
    classe = df["classificacao_acidente"].to_numpy()
    pedestre = (df["tipo_acidente"] == PEDESTRE).to_numpy()
    feridos = classe == "Com Vítimas Feridas"
    peso = np.select([classe == "Com Vítimas Fatais", feridos & pedestre, feridos],
                     [PESO_FATAL, PESO_PEDESTRE, PESO_FERIDOS], PESO_SEM_VITIMAS)
    return pd.Series(peso, index=df.index)


def com_ups(df):
    return df.assign(ups=ups(df))


MEDIDAS = {"acidentes": ("id", "count"), "mortos": ("mortos", "sum"),
           "feridos_graves": ("feridos_graves", "sum"), "ups": ("ups", "sum")}


def agregar_ups(df, chaves):
    return com_ups(df).groupby(chaves).agg(**MEDIDAS).reset_index()


# =============================================================================
# Tendência em relação ao ano anterior
# =============================================================================
MINIMO_TENDENCIA = 15  # abaixo disto (em UPS ou mortos) a variação é ruído
VERDE_TEXTO = "text-[#007a33]"
VERMELHO_TEXTO = "text-pm-vermelho-escuro"


def tendencia(atual, anterior, minimo=MINIMO_TENDENCIA):
    """Seta, texto e cor da variação. nivel: -2 melhorou muito ... +2 piorou muito."""
    if anterior is None:
        return None
    if max(atual, anterior) < minimo:
        return {"seta": "·", "texto": "poucos casos", "classe": "text-pm-cinza-medio", "nivel": 0}
    if anterior == 0:
        return {"seta": "▲▲", "texto": "novo", "classe": VERMELHO_TEXTO, "nivel": 2}
    v = (atual - anterior) / anterior
    texto = variacao(atual, anterior)
    if v >= 0.25:
        return {"seta": "▲▲", "texto": texto, "classe": VERMELHO_TEXTO, "nivel": 2}
    if v >= 0.05:
        return {"seta": "▲", "texto": texto, "classe": VERMELHO_TEXTO, "nivel": 1}
    if v <= -0.25:
        return {"seta": "▼▼", "texto": texto, "classe": VERDE_TEXTO, "nivel": -2}
    if v <= -0.05:
        return {"seta": "▼", "texto": texto, "classe": VERDE_TEXTO, "nivel": -1}
    return {"seta": "=", "texto": texto, "classe": "text-pm-cinza", "nivel": 0}


# =============================================================================
# Trechos (BR + faixa de 10 km, dentro de cada estado)
# =============================================================================
CHAVE_TRECHO = ["uf", "br", "trecho_km"]
COLUNAS_RANKING = CHAVE_TRECHO + ["acidentes", "mortos", "feridos_graves", "ups", "latitude",
                                  "longitude", "municipio", "nome", "local", "posicao", "parte_ups",
                                  "ups_ant", "tend"]


def so_trechos(df):
    return df[(df["br"] > 0) & (df["trecho_km"] >= 0)]


def nome_trecho(br, km):
    return f"BR-{br} · km {km} a {km + 10}"


def ranking_trechos(recorte, anterior=None):
    """Trechos do mais grave (maior UPS) ao menos grave, com tendência se houver ano anterior."""
    validos = com_ups(so_trechos(recorte))
    if validos.empty:
        return pd.DataFrame(columns=COLUNAS_RANKING)
    t = validos.groupby(CHAVE_TRECHO).agg(
        **MEDIDAS, latitude=("latitude", "median"), longitude=("longitude", "median")).reset_index()
    # município onde o trecho tem mais acidentes (um trecho pode cruzar dois)
    principal = (validos.groupby(CHAVE_TRECHO + ["municipio"]).size().reset_index(name="n")
                 .sort_values("n", ascending=False).drop_duplicates(CHAVE_TRECHO)[CHAVE_TRECHO + ["municipio"]])
    t = t.merge(principal, on=CHAVE_TRECHO, how="left")
    t["nome"] = [nome_trecho(b, k) for b, k in zip(t["br"], t["trecho_km"])]
    t["local"] = t["municipio"].str.title() + " - " + t["uf"]
    t = t.sort_values(["ups", "mortos", "acidentes"], ascending=False).reset_index(drop=True)
    t["posicao"] = t.index + 1
    t["parte_ups"] = t["ups"] / t["ups"].sum() * 100

    if anterior is not None:
        a = agregar_ups(so_trechos(anterior), CHAVE_TRECHO).rename(columns={"ups": "ups_ant"})
        t = t.merge(a[CHAVE_TRECHO + ["ups_ant"]], on=CHAVE_TRECHO, how="left")
        t["ups_ant"] = t["ups_ant"].fillna(0)
        t["tend"] = [tendencia(u, ua) for u, ua in zip(t["ups"], t["ups_ant"])]
    else:
        t["ups_ant"] = np.nan
        t["tend"] = None
    return t


def detalhes_trechos(recorte, trechos):
    """Para cada trecho dado: a janela de risco e a causa com mais gravidade."""
    if trechos.empty:
        return {}
    sub = com_ups(so_trechos(recorte)).merge(trechos[CHAVE_TRECHO], on=CHAVE_TRECHO)
    sub["faixa"] = sub["hora"] // FAIXA_HORAS * FAIXA_HORAS
    janela = (sub.groupby(CHAVE_TRECHO + ["dia_semana", "faixa"])["ups"].sum().reset_index()
              .sort_values("ups", ascending=False).drop_duplicates(CHAVE_TRECHO))
    causa = (sub.groupby(CHAVE_TRECHO + ["causa_acidente"])["ups"].sum().reset_index()
             .sort_values("ups", ascending=False).drop_duplicates(CHAVE_TRECHO))
    detalhes = {}
    for r in janela.itertuples():
        detalhes.setdefault((r.uf, r.br, r.trecho_km), {})["janela"] = texto_janela(r.dia_semana, r.faixa)
    for r in causa.itertuples():
        d = detalhes.setdefault((r.uf, r.br, r.trecho_km), {})
        d["causa"] = r.causa_acidente
        d["grupo"] = grupo_da_causa(pd.Series([r.causa_acidente])).iloc[0]
    return detalhes


# =============================================================================
# Janelas de risco: dia da semana + faixa de 3 horas
# =============================================================================
FAIXA_HORAS = 3
N_JANELAS = 7 * 24 // FAIXA_HORAS


def texto_janela(dia, faixa):
    return f"{dia.capitalize()}, das {faixa}h às {faixa + FAIXA_HORAS}h"


def janelas_de_risco(recorte, n=5):
    """As n janelas (dia + 3 horas) com mais gravidade, com a parte de cada uma."""
    if recorte.empty:
        return []
    d = com_ups(recorte[["id", "dia_semana", "hora", "mortos", "feridos_graves",
                         "classificacao_acidente", "tipo_acidente"]])
    d["faixa"] = d["hora"] // FAIXA_HORAS * FAIXA_HORAS
    g = d.groupby(["dia_semana", "faixa"]).agg(**MEDIDAS).reset_index()
    total = g["ups"].sum()
    media = total / N_JANELAS
    top = g.sort_values(["ups", "mortos"], ascending=False).head(n)
    return [{
        "dia": r.dia_semana.capitalize(), "horario": f"{r.faixa}h às {r.faixa + FAIXA_HORAS}h",
        "texto": texto_janela(r.dia_semana, r.faixa),
        "acidentes": numero(r.acidentes), "mortos": numero(r.mortos),
        "parte": percentual(r.ups, total), "parte_num": r.ups / total * 100 if total else 0,
        "vezes": decimal(r.ups / media) if media else "0",
    } for r in top.itertuples()]


def calor_ups(recorte, dias):
    """Tabela dia da semana x hora com a soma de UPS (para o mapa de calor)."""
    d = com_ups(recorte[["dia_semana", "hora", "classificacao_acidente", "tipo_acidente"]])
    return pd.crosstab(d["dia_semana"], d["hora"], values=d["ups"], aggfunc="sum").reindex(
        index=dias, columns=range(24)).fillna(0)


# =============================================================================
# Causas agrupadas por quem pode agir
# =============================================================================
INFRACAO, VEICULO, VIA = "Infrações de trânsito", "Condição do veículo", "Falhas da via"
PEDESTRES, CONDUTOR, AMBIENTE = "Pedestres", "Atenção do condutor", "Ambiente e outros"

GRUPOS_CAUSA = {
    # grupo: (quem pode agir, cor no gráfico, causas da PRF)
    INFRACAO: ("Fiscalização: PM e PRF (blitz, radar, Lei Seca)", "#e30613", [
        "Ingestão de álcool pelo condutor", "Velocidade Incompatível", "Ultrapassagem Indevida",
        "Transitar na contramão", "Trafegar com motocicleta (ou similar) entre as faixas",
        "Conversão proibida", "Retorno proibido", "Acesso irregular", "Transitar no Acostamento",
        "Condutor usando celular", "Estacionar ou parar em local proibido",
        "Condutor desrespeitou a iluminação vermelha do semáforo",
        "Ingestão de substâncias psicoativas pelo condutor", "Participar de racha",
        "Desrespeitar a preferência no cruzamento", "Carga excessiva e/ou mal acondicionada",
        "Modificação proibida", "Deixar de acionar o farol da motocicleta (ou similar)",
        "Condutor não acionou o farol baixo durante o dia em rodovias de pista simples",
        "Transitar na calçada",
    ]),
    VEICULO: ("Fiscalização veicular: PRF e Detran", "#3c3c3b", [
        "Demais falhas mecânicas ou elétricas", "Avarias e/ou desgaste excessivo no pneu",
        "Problema com o freio", "Problema na suspensão", "Faróis desregulados",
    ]),
    VIA: ("Órgão da via: DNIT, DER ou concessionária", "#706f6f", [
        "Pista Escorregadia", "Acumulo de água sobre o pavimento", "Pista esburacada",
        "Acumulo de areia ou detritos sobre o pavimento", "Demais falhas na via",
        "Afundamento ou ondulação no pavimento", "Ausência de sinalização",
        "Acumulo de óleo sobre o pavimento", "Curva acentuada", "Acostamento em desnível",
        "Deficiência do Sistema de Iluminação/Sinalização", "Iluminação deficiente",
        "Área urbana sem a presença de local apropriado para a travessia de pedestres",
        "Falta de acostamento", "Sinalização mal posicionada",
        "Falta de elemento de contenção que evite a saída do leito carroçável", "Desvio temporário",
        "Declive acentuado", "Restrição de visibilidade em curvas horizontais",
        "Restrição de visibilidade em curvas verticais", "Faixas de trânsito com largura insuficiente",
        "Redutor de velocidade em desacordo", "Semáforo com defeito", "Sinalização encoberta",
        "Objeto estático sobre o leito carroçável",
    ]),
    PEDESTRES: ("Travessias seguras e educação: prefeituras, DNIT e Detran", "#f0767c", [
        "Entrada inopinada do pedestre", "Pedestre andava na pista",
        "Pedestre cruzava a pista fora da faixa",
        "Pedestre - Ingestão de álcool/ substâncias psicoativas",
    ]),
    CONDUTOR: ("Educação e campanhas; fiscalizar distância e tempo de direção", "#1d1d1b", [
        "Ausência de reação do condutor", "Reação tardia ou ineficiente do condutor",
        "Acessar a via sem observar a presença dos outros veículos",
        "Condutor deixou de manter distância do veículo da frente", "Manobra de mudança de faixa",
        "Condutor Dormindo", "Frear bruscamente", "Mal súbito do condutor",
        "Suicídio (presumido)", "Transtornos Mentais (exceto suicidio)",
    ]),
    AMBIENTE: ("Alertas, sinalização temporária e manejo de animais", "#c6c6c6", [
        "Chuva", "Neblina", "Fumaça", "Demais Fenômenos da natureza", "Animais na Pista",
    ]),
}
_GRUPO_DA_CAUSA = {causa.lower(): grupo for grupo, (_, _, causas) in GRUPOS_CAUSA.items() for causa in causas}


def grupo_da_causa(causas):
    """Série de causas -> série de grupos (causas novas ou não listadas caem em "Ambiente e outros")."""
    return causas.str.lower().map(_GRUPO_DA_CAUSA).fillna(AMBIENTE)


def tabela_grupos(recorte, causas_por_grupo=3):
    """Cada grupo de causas com acidentes, mortos, parte da gravidade e as principais causas."""
    if recorte.empty:
        return []
    d = com_ups(recorte[["id", "causa_acidente", "mortos", "feridos_graves",
                         "classificacao_acidente", "tipo_acidente"]])
    d["grupo"] = grupo_da_causa(d["causa_acidente"])
    total = d["ups"].sum()
    por_causa = d.groupby(["grupo", "causa_acidente"]).agg(**MEDIDAS).reset_index()
    linhas = []
    for grupo, g in por_causa.groupby("grupo"):
        quem, cor, _ = GRUPOS_CAUSA[grupo]
        principais = g.sort_values(["ups", "acidentes"], ascending=False).head(causas_por_grupo)
        linhas.append({
            "grupo": grupo, "quem": quem, "cor": cor,
            "acidentes": int(g["acidentes"].sum()), "mortos": int(g["mortos"].sum()),
            "ups": int(g["ups"].sum()), "parte": percentual(g["ups"].sum(), total),
            "parte_num": g["ups"].sum() / total * 100 if total else 0,
            "causas": [{"nome": c.causa_acidente, "acidentes": numero(c.acidentes), "mortos": numero(c.mortos)}
                       for c in principais.itertuples()],
        })
    return sorted(linhas, key=lambda linha: -linha["ups"])


def achar_grupo(grupos, nome):
    return next((g for g in grupos if g["grupo"] == nome), None)


# =============================================================================
# Mapa de calor geográfico (grade de pontos)
# =============================================================================
def grade_densidade(recorte, passo):
    """Junta os acidentes em quadradinhos de `passo` graus, somando a gravidade."""
    d = recorte.dropna(subset=["latitude", "longitude"])
    d = d[d["latitude"].between(-34, 6) & d["longitude"].between(-74, -34)]  # descarta coordenadas erradas
    if d.empty:
        return pd.DataFrame(columns=["latitude", "longitude", "ups", "acidentes", "mortos"])
    d = com_ups(d[["id", "latitude", "longitude", "mortos", "feridos_graves",
                   "classificacao_acidente", "tipo_acidente"]])
    # arredonda de novo no fim: 0.1 * 73 = 7.300000000000001 ocuparia espaço à toa na página
    d["latitude"] = ((d["latitude"] / passo).round() * passo).round(4)
    d["longitude"] = ((d["longitude"] / passo).round() * passo).round(4)
    return d.groupby(["latitude", "longitude"]).agg(**MEDIDAS).reset_index()


# =============================================================================
# Séries mensais (metas e antes/depois)
# =============================================================================
INDICADORES = {"mortos": "Mortos", "acidentes": "Acidentes", "feridos_graves": "Feridos graves",
               "ups": "Gravidade (UPS)"}


def mensal_do_ano(dados, f):
    """Totais por mês de um ano inteiro, com os filtros (menos o intervalo de meses).
    Meses que o arquivo ainda não tem ficam vazios (NaN)."""
    recorte = recortar(dados, {**f, "mes_inicio": 1, "mes_fim": 12})[0]
    tabela = agregar_ups(recorte, "mes").set_index("mes")[list(INDICADORES)]
    meses_no_arquivo = set(dados["mes"].unique())
    tabela = tabela.reindex(range(1, 13))
    for mes in tabela.index:
        if mes in meses_no_arquivo:
            tabela.loc[mes] = tabela.loc[mes].fillna(0)
    return tabela


def serie_mensal(anos_e_dados, f):
    """Todos os anos em sequência, um mês por linha (índice = período AAAA-MM)."""
    partes = []
    for ano, dados in anos_e_dados:
        m = mensal_do_ano(dados, f).dropna(how="all")
        m.index = pd.PeriodIndex([pd.Period(year=ano, month=int(mes), freq="M") for mes in m.index])
        partes.append(m)
    return pd.concat(partes).sort_index() if partes else pd.DataFrame(columns=list(INDICADORES))


MESES_CURTOS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def texto_mes(periodo):
    return f"{MESES_CURTOS[periodo.month - 1]}/{periodo.year}"


def texto_intervalo(indice):
    return texto_mes(indice[0]) if len(indice) == 1 else f"{texto_mes(indice[0])} a {texto_mes(indice[-1])}"


def antes_depois(serie, intervencao, janela):
    """
    Compara a média mensal antes e depois de uma intervenção (o mês dela fica de
    fora, por ser de transição). Os dois lados têm o mesmo número de meses. Como
    controle da sazonalidade, mostra a mesma comparação um ano antes.
    """
    antes = serie[(serie.index >= intervencao - janela) & (serie.index < intervencao)]
    depois = serie[(serie.index > intervencao) & (serie.index <= intervencao + janela)]
    n = min(len(antes), len(depois))
    if n == 0:
        return None
    antes, depois = antes.iloc[-n:], depois.iloc[:n]
    antes_ctrl = serie.reindex(antes.index - 12)
    depois_ctrl = serie.reindex(depois.index - 12)
    tem_controle = not (antes_ctrl.isna().any().any() or depois_ctrl.isna().any().any())

    linhas = []
    for coluna, nome in INDICADORES.items():
        a, d = antes[coluna].mean(), depois[coluna].mean()
        linha = {"nome": nome, "antes": decimal(a), "depois": decimal(d), "variacao": variacao(d, a),
                 "controle": "–", "efeito": "–", "classe": "", "classe_efeito": ""}
        if a:
            v = (d - a) / a * 100
            linha["classe"] = VERMELHO_TEXTO if v > 0 else VERDE_TEXTO if v < 0 else ""
        if tem_controle:
            ac, dc = antes_ctrl[coluna].mean(), depois_ctrl[coluna].mean()
            linha["controle"] = variacao(dc, ac)
            if a and ac:
                efeito = (d - a) / a * 100 - (dc - ac) / ac * 100
                linha["efeito"] = ("+" if efeito > 0 else "") + decimal(efeito) + " p.p."
                linha["classe_efeito"] = VERMELHO_TEXTO if efeito > 0 else VERDE_TEXTO if efeito < 0 else ""
        linhas.append(linha)
    return {
        "meses": n, "antes": texto_intervalo(antes.index), "depois": texto_intervalo(depois.index),
        "controle_antes": texto_intervalo(antes_ctrl.index) if tem_controle else "",
        "controle_depois": texto_intervalo(depois_ctrl.index) if tem_controle else "",
        "tem_controle": tem_controle, "linhas": linhas,
        "inicio_antes": antes.index[0], "fim_antes": antes.index[-1],
        "inicio_depois": depois.index[0], "fim_depois": depois.index[-1],
    }


# =============================================================================
# Textos: resumo executivo e recomendações
# =============================================================================
def resumo_executivo(f, recorte, anterior, ano_anterior, ranking, janelas, grupos):
    """Frases curtas com o que mais importa no filtro atual (HTML seguro)."""
    if recorte.empty:
        return ["Sem acidentes para este filtro."]
    frases = []
    mortos = int(recorte["mortos"].sum())
    frase = format_html("<b>{}</b> acidentes e <b>{}</b> mortos em {}, {}.", numero(len(recorte)),
                        numero(mortos), f["local"], f["texto_periodo"])
    if anterior is not None and len(anterior):
        frase = format_html("{} Nos mesmos meses de {}: acidentes <b>{}</b>, mortes <b>{}</b>.", frase,
                            ano_anterior, variacao(len(recorte), len(anterior)),
                            variacao(mortos, int(anterior["mortos"].sum())))
    frases.append(frase)

    if len(ranking) >= 10:
        top = ranking.head(10)
        acumulado = ranking["ups"].cumsum() / ranking["ups"].sum()
        metade = int((acumulado < 0.5).sum()) + 1
        frases.append(format_html(
            "Os <b>10 trechos</b> mais graves concentram <b>{}</b> da gravidade e <b>{}</b> das mortes. "
            "Metade de toda a gravidade está em <b>{}</b> dos {} trechos com acidentes.",
            percentual(top["ups"].sum(), ranking["ups"].sum()),
            percentual(top["mortos"].sum(), ranking["mortos"].sum()), numero(metade), numero(len(ranking))))
    if not ranking.empty and f["trecho"] is None:
        r = ranking.iloc[0]
        frases.append(format_html("Trecho mais crítico: <b>{}</b> ({}), com {} acidentes e {} mortos.",
                                  r["nome"], r["local"], numero(r["acidentes"]), numero(r["mortos"])))
        pioraram = [r for r in ranking.head(20).itertuples() if r.tend and r.tend["nivel"] >= 2]
        if pioraram:
            exemplos = "; ".join(f"{p.nome} ({p.tend['texto']})" for p in pioraram[:3])
            frases.append(format_html("<b>{}</b> dos 20 trechos mais graves pioraram 25% ou mais em relação a {}: {}.",
                                      len(pioraram), ano_anterior, exemplos))
    if janelas:
        j = janelas[0]
        frases.append(format_html("Janela de maior risco: <b>{}</b>, com {} vezes a gravidade de um horário médio da semana.",
                                  j["texto"], j["vezes"]))
    infracoes = achar_grupo(grupos, INFRACAO)
    if infracoes and infracoes["causas"]:
        c = infracoes["causas"][0]
        frases.append(format_html("Principal causa que a fiscalização pode atacar: <b>{}</b> ({} acidentes, {} mortos).",
                                  c["nome"], c["acidentes"], c["mortos"]))
    via = achar_grupo(grupos, VIA)
    if via and via["acidentes"]:
        frases.append(format_html(
            "Falhas da via (para encaminhar ao DNIT/DER): <b>{}</b> acidentes e <b>{}</b> mortos; a principal é {}.",
            numero(via["acidentes"]), numero(via["mortos"]), via["causas"][0]["nome"].lower()))
    return frases


def recomendacoes(recorte, anterior, ano_anterior, janelas, grupos):
    """Ações sugeridas para um trecho, cada uma com quem age."""
    recs = []
    if janelas:
        top = janelas[:3]
        soma = sum(j["parte_num"] for j in top)
        recs.append({"tipo": "Quando", "quem": GRUPOS_CAUSA[INFRACAO][0],
                     "texto": format_html("Concentrar o policiamento em <b>{}</b>. Juntas, essas janelas somam {} da gravidade do trecho.",
                                          "; ".join(j["texto"] for j in top), decimal(soma) + "%")})
    infracoes = achar_grupo(grupos, INFRACAO)
    if infracoes and infracoes["causas"]:
        recs.append({"tipo": "O que fiscalizar", "quem": infracoes["quem"],
                     "texto": format_html("Foco da operação: <b>{}</b>. Infrações de trânsito respondem por {} da gravidade aqui.",
                                          "; ".join(c["nome"] for c in infracoes["causas"]), infracoes["parte"])})
    via = achar_grupo(grupos, VIA)
    if via and via["acidentes"]:
        recs.append({"tipo": "Encaminhar", "quem": via["quem"],
                     "texto": format_html("Ofício ao órgão da via: <b>{}</b> acidentes ({} mortos) ligados a falhas da via, principalmente {}.",
                                          numero(via["acidentes"]), numero(via["mortos"]),
                                          "; ".join(c["nome"].lower() for c in via["causas"]))})
    atropelamentos = recorte[recorte["tipo_acidente"] == PEDESTRE]
    if len(atropelamentos):
        recs.append({"tipo": "Pedestres", "quem": GRUPOS_CAUSA[PEDESTRES][0],
                     "texto": format_html("<b>{}</b> atropelamentos ({} mortos): avaliar travessias, iluminação e ações educativas no trecho.",
                                          numero(len(atropelamentos)), numero(atropelamentos["mortos"].sum()))})
    veiculo = achar_grupo(grupos, VEICULO)
    if veiculo and veiculo["parte_num"] >= 10:
        recs.append({"tipo": "Veículos", "quem": veiculo["quem"],
                     "texto": format_html("Falhas de veículo respondem por {} da gravidade: incluir checagem de pneus, freios e equipamentos nas abordagens.",
                                          veiculo["parte"])})
    if anterior is not None:
        t = tendencia(ups(recorte).sum(), ups(anterior).sum())
        if t and t["nivel"]:
            sentido = "subiu" if t["nivel"] > 0 else "caiu"
            recs.append({"tipo": "Tendência", "quem": "",
                         "texto": format_html("A gravidade {} <b>{}</b> em relação aos mesmos meses de {}.",
                                              sentido, t["texto"], ano_anterior)})
    return recs
