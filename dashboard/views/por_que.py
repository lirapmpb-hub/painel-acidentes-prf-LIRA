"""
Aba Por quê: o que faz os acidentes matarem? Condições da via e do ambiente,
causas, tipos de acidente, vítimas e veículos (antigas abas Condições e Vítimas).
"""
import pandas as pd

from .. import graficos
from ..calculos import (FAIXAS_VEICULOS, MINIMO_PARA_INDICE, candidatos, decimal, faixa_veiculos,
                        gravidade, numero, percentual, sem_desconhecidos, separar_valores,
                        tabela_gravidade, vazio_como_zero)
from .comum import mostrar, painel, preparar

SECOES = [("condicoes", "Condições da via e do tempo"), ("causas", "Causas"),
          ("tipos", "Tipos de acidente"), ("vitimas", "Vítimas e veículos")]

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

GRUPOS_PESSOAS = [
    # (coluna, título, cor)
    ("mortos", "Mortos", graficos.VERMELHO),
    ("feridos_graves", "Feridos graves", graficos.VERMELHO_MEDIO),
    ("feridos_leves", "Feridos leves", graficos.VERMELHO_CLARO),
    ("ilesos", "Ilesos", graficos.VERDE),
    ("ignorados", "Ignorados", graficos.CINZA_CLARO),
]


def condicoes(recorte, media):
    """Um gráfico por condição (tempo, pista...) e, para cada uma, a categoria mais letal."""
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
    return paineis, destaques


def cartoes_de_vitimas(recorte):
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
    return cartoes


def por_que(request):
    f, recorte, _, _ = preparar(request)
    media = gravidade(recorte)
    paineis_condicoes, destaques = condicoes(recorte, media)

    causas = painel(
        "Quais causas matam mais?",
        "As 10 primeiras na ordem escolhida · começa pelas mais letais "
        f"(mortos a cada 100 acidentes, mínimo de {MINIMO_PARA_INDICE} acidentes)",
        graficos.grafico_condicao(candidatos(tabela_gravidade(recorte, "causa_acidente"), 10),
                                  media, ordem="indice", limite=10))

    letais = painel(
        "Quais tipos de acidente matam mais?",
        f"Os 10 primeiros na ordem escolhida · começa pelos mais letais (mínimo de {MINIMO_PARA_INDICE} acidentes)",
        graficos.grafico_condicao(candidatos(tabela_gravidade(recorte, "tipo_acidente"), 10),
                                  media, ordem="indice", limite=10))

    tipos = recorte.groupby("tipo_acidente")[["mortos", "feridos_graves", "feridos_leves"]].sum()
    tipos["vitimas"] = tipos.sum(axis=1)
    tipos = tipos[tipos["vitimas"] > 0].reset_index()
    tipos = candidatos(tipos, 10, ("vitimas", "mortos", "feridos_graves", "feridos_leves"), "tipo_acidente")
    vitimas_por_tipo = painel(
        "Quais tipos de acidente deixam mais vítimas?",
        "Os 10 primeiros na ordem escolhida · mortos, feridos graves e leves",
        graficos.grafico_empilhado(tipos, "tipo_acidente", GRUPOS_PESSOAS[:3], limite=10))

    situacao = pd.Series({titulo: recorte[coluna].sum() for coluna, titulo, _ in GRUPOS_PESSOAS})
    rosca = painel("O que aconteceu com os envolvidos?", "Cada pessoa aparece em uma só categoria",
                   graficos.grafico_rosca(situacao, {t: c for _, t, c in GRUPOS_PESSOAS}, "pessoas",
                                          [t for _, t, _ in GRUPOS_PESSOAS]))

    com_faixa = recorte.assign(faixa=recorte["veiculos"].map(faixa_veiculos))
    veiculos = painel(
        "Acidentes com mais veículos matam mais?", "Acidentes com 1 veículo, 2 veículos, ..., engavetamentos",
        graficos.grafico_condicao(vazio_como_zero(tabela_gravidade(com_faixa, "faixa"), FAIXAS_VEICULOS),
                                  media, ordem=None))

    return mostrar(request, "por_que", f, {
        "media": decimal(media), "minimo": MINIMO_PARA_INDICE, "secoes": SECOES,
        "destaques": destaques, "paineis_condicoes": paineis_condicoes, "causas": causas,
        "letais": letais, "vitimas_por_tipo": vitimas_por_tipo,
        "kpis_vitimas": cartoes_de_vitimas(recorte), "rosca": rosca, "veiculos": veiculos,
    })
