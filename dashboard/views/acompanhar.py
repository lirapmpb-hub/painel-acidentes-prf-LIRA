"""
Aba Acompanhar: estamos melhorando? Meta de redução, antes e depois de uma
ação e comparação entre os anos (antigas abas Metas e Comparação anual).
"""
import pandas as pd
from django.utils.html import format_html

from .. import decisao, graficos
from ..calculos import decimal, gravidade, inteiro_valido, media_mensal, numero, variacao
from ..dados import ANO_ATUAL, MESES, anos_disponiveis, carregar_ano, carregar_dados
from ..filtros import recortar
from .comum import AJUDA, ANO_ANTERIOR, com_tendencia, mostrar, painel, preparar

SECOES = [("meta", "Meta de redução"), ("antes-depois", "Antes e depois de uma ação"),
          ("anos", "Comparação entre anos")]


# =============================================================================
# Meta: ano atual acumulado x ano anterior menos a meta
# =============================================================================
def acompanhamento_da_meta(f, indicador, nome, meta):
    atual = decisao.mensal_do_ano(carregar_dados(), f)
    base_dados = carregar_ano(ANO_ANTERIOR)
    meses_atual = [m for m in range(1, 13) if pd.notna(atual.loc[m, indicador])]
    if base_dados is None or not meses_atual:
        return None
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
            # bool(): o template compara com "is True", e o pandas devolve o booleano do numpy
            "ok": None if not tem or limite_mes is None else bool(v_atual <= limite_mes),
        })
    return {
        "cartoes": cartoes, "frase_restante": frase_restante, "linhas": linhas,
        "grafico": graficos.html_de(graficos.grafico_meta(tabela, nome.lower(), ANO_ATUAL, ANO_ANTERIOR)),
    }


# =============================================================================
# Antes e depois de uma ação
# =============================================================================
def avaliacao_antes_depois(request, f, indicador, nome):
    serie = decisao.serie_mensal([(ano, carregar_ano(ano)) for ano in anos_disponiveis()], f)
    opcoes = [(str(p), decisao.texto_mes(p)) for p in serie.index[1:-1]]
    escolhida = request.GET.get("intervencao", "")
    janela = inteiro_valido(request.GET.get("janela"), 6, 1, 12)
    resultado = intervencao = None
    if escolhida in dict(opcoes):
        intervencao = pd.Period(escolhida, freq="M")
        resultado = decisao.antes_depois(serie, intervencao, janela)
    return {
        "opcoes_intervencao": opcoes, "intervencao": escolhida, "janela": janela,
        "janelas_opcoes": [3, 6, 12], "resultado": resultado,
        "texto_intervencao": decisao.texto_mes(intervencao) if intervencao is not None else "",
        "grafico_antes_depois": graficos.html_de(
            graficos.grafico_antes_depois(serie, indicador, nome, resultado, intervencao)),
    }


# =============================================================================
# Comparação entre os anos (mesmo período e mesmos filtros em cada ano)
# =============================================================================
def comparacao_anual(f):
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
    mensal = (pd.concat(mensal, ignore_index=True) if mensal
              else pd.DataFrame(columns=["ano", "mes", "acidentes", "mortos"]))
    return {
        "linhas_anos": linhas,
        "paineis_anos": [
            painel("Acidentes por mês", "Uma linha por ano", graficos.grafico_anos(mensal, "acidentes", "acidentes")),
            painel("Mortos por mês", "Uma linha por ano", graficos.grafico_anos(mensal, "mortos", "mortos")),
        ],
    }


def acompanhar(request):
    f, _, _, _ = preparar(request)
    indicador = request.GET.get("indicador", "mortos")
    if indicador not in decisao.INDICADORES:
        indicador = "mortos"
    nome = decisao.INDICADORES[indicador]
    meta = inteiro_valido(request.GET.get("meta"), 10, 0, 90)
    return mostrar(request, "acompanhar", f, {
        "indicador": indicador, "nome_indicador": nome, "meta": meta,
        "indicadores": list(decisao.INDICADORES.items()), "secoes": SECOES,
        "acompanhamento": acompanhamento_da_meta(f, indicador, nome, meta),
        **avaliacao_antes_depois(request, f, indicador, nome),
        **comparacao_anual(f),
    })
