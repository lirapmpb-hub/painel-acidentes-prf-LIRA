"""
Aba Estrutura PRF: quem cobre cada área? Regionais, delegacias e unidades operacionais.
"""
from .. import graficos
from ..calculos import agregar, gravidade, tabela_gravidade
from ..filtros import link
from .comum import escolher_ordem, montar_tabela, mostrar, painel, preparar


def estrutura(request):
    f, recorte, _, _ = preparar(request)
    ordem = escolher_ordem(request, "acidentes")
    media = gravidade(recorte)

    regionais = painel("Quais regionais têm mais acidentes e mortes?", "Uma por estado, mais o Distrito Federal",
                       graficos.grafico_condicao(tabela_gravidade(recorte, "regional"), media))
    delegacias = montar_tabela(
        agregar(recorte, ["regional", "delegacia"]),
        [("delegacia", "Delegacia"), ("regional", "Regional")], ordem, f, "estrutura", len(recorte),
        link_linha=lambda d: link(f, "index", regional=d["regional"], delegacia=d["delegacia"]),
        ancora="delegacias",
    )
    uops = montar_tabela(
        agregar(recorte, ["delegacia", "uop"]),
        [("uop", "Unidade operacional (UOP)"), ("delegacia", "Delegacia")], ordem, f, "estrutura", len(recorte),
        ancora="uops",
    )
    return mostrar(request, "estrutura", f, {
        "regionais": regionais, "delegacias": delegacias, "uops": uops,
    })
