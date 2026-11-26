"""
Página inicial: o que é o painel e o que existe em cada aba, sem carregar os
dados de acidentes (abre rápido mesmo com o servidor acabando de ligar).
A entrada principal é a Paraíba.
"""
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode

from ..dados import ESTADOS, MESES, resumo_da_base
from .comum import ABAS

UF_PRINCIPAL = "PB"
MESES_EXTENSO = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
                 "setembro", "outubro", "novembro", "dezembro"]

# O que cada aba tem (os cartões da página inicial), na ordem do menu
CONTEUDO_DAS_ABAS = {
    "index": ["Resumo para decisão e números com variação sobre o ano anterior",
              "Evolução mês a mês, mapa, dia e hora", "Tipos de acidente e rodovias"],
    "prioridades": ["Trechos de 10 km priorizados pela gravidade, com tendência",
                    "Mapa de calor e sugestão de escala (dia e horário)",
                    "Causas agrupadas por quem pode agir e ficha de cada trecho para imprimir"],
    "por_que": ["Condições da via e do tempo que mais matam", "Causas e tipos de acidente mais letais",
                "Vítimas e veículos envolvidos"],
    "acompanhar": ["Meta de redução: situação, projeção e limite dos próximos meses",
                   "Antes e depois de uma ação (operação, radar, obra)", "Comparação entre os anos"],
    "estrutura": ["Regionais, delegacias e unidades operacionais da PRF",
                  "Onde está a carga de acidentes de cada uma"],
}


def link_aba(rota, uf=UF_PRINCIPAL):
    return reverse(rota) + ("?" + urlencode({"uf": uf}) if uf else "")


def inicio(request):
    # Links antigos com filtro (ex.: /?uf=PB) eram o Panorama: continuam levando a ele
    if request.GET:
        return redirect(reverse("index") + "?" + request.GET.urlencode())

    base = resumo_da_base()
    abas = [{"titulo": titulo, "pergunta": pergunta, "url": link_aba(nome) if nome != "inicio" else reverse("inicio"),
             "ativa": nome == "inicio"} for nome, titulo, pergunta in ABAS]
    cartoes = [{"titulo": titulo, "pergunta": pergunta, "itens": CONTEUDO_DAS_ABAS[nome],
                "link_pb": link_aba(nome), "link_brasil": link_aba(nome, None)}
               for nome, titulo, pergunta in ABAS if nome in CONTEUDO_DAS_ABAS]
    ultimo_mes = base["ultimo_mes"]
    return render(request, "dashboard/inicio.html", {
        "abas": abas, "cartoes": cartoes, "ano_atual": base["ano_atual"],
        "primeiro_ano": min(base["anos"]), "ultimo_mes_extenso": MESES_EXTENSO[ultimo_mes - 1],
        "periodo_atual": f"jan a {MESES[ultimo_mes - 1].lower()}",
        "estados": sorted((nome, sigla) for sigla, nome in ESTADOS.items() if sigla != UF_PRINCIPAL),
        "link_pb": link_aba("index"), "link_onde_agir_pb": link_aba("prioridades"),
        "link_ficha_pb": link_aba("ficha"), "link_acompanhar_pb": link_aba("acompanhar"),
        "link_brasil": reverse("index"),
    })
