"""
Filtros do painel (equivalem às segmentações de dados do Power BI).

Todas as abas usam os mesmos filtros, que ficam na URL. Assim dá para trocar
de aba, compartilhar o link ou baixar o CSV sem perder as escolhas. Exemplo:
    /trechos/?uf=PB&br=230&clima=Chuva&mes_inicio=3
"""
from urllib.parse import urlencode

from django.urls import reverse

from .calculos import inteiro_valido
from .dados import ANO_ATUAL, CLASSIFICACOES, ESTADOS, MESES

# Filtros avançados: nome na URL -> (coluna da planilha, rótulo no formulário)
AVANCADOS = {
    "fase_dia": ("fase_dia", "Fase do dia"),
    "clima": ("condicao_metereologica", "Condição do tempo"),
    "pista": ("tipo_pista", "Tipo de pista"),
    "area": ("area", "Área"),
    "regional": ("regional", "Regional da PRF"),
    "delegacia": ("delegacia", "Delegacia da PRF"),
}


def ler_filtros(request, df):
    """Lê e valida os filtros da URL. Valores inválidos voltam ao padrão (todos)."""
    get = request.GET
    primeiro_mes, ultimo_mes = int(df["mes"].min()), int(df["mes"].max())

    # --- Local: estado > município, e rodovia > trecho ------------------
    uf = get.get("uf", "")
    if uf not in ESTADOS:
        uf = ""
    do_estado = df[df["uf"] == uf] if uf else df

    municipio = get.get("municipio", "")
    if not uf or municipio not in set(do_estado["municipio"].unique()):
        municipio = ""

    # Rodovias: só as que têm acidentes no município escolhido (ou no estado).
    # A PRF usa o número 0 quando a rodovia não foi informada; fica fora da lista.
    do_municipio = do_estado[do_estado["municipio"] == municipio] if municipio else do_estado
    rodovias = sorted(int(numero) for numero in do_municipio["br"].unique() if numero > 0)
    br = inteiro_valido(get.get("br"), 0, 1, 999)
    if br not in rodovias:
        br = 0  # zero significa "todas as rodovias"

    # Municípios: com uma BR escolhida, só os que ela atravessa (com acidentes registrados)
    na_rodovia = do_estado[do_estado["br"] == br] if br else do_estado
    municipios = sorted(na_rodovia["municipio"].unique()) if uf else []

    # Trecho de 10 km (200 = km 200 a 210). Só faz sentido com uma BR escolhida.
    trecho = inteiro_valido(get.get("trecho"), None, 0, 9990) if br else None
    if trecho is not None and trecho % 10:
        trecho = None

    # --- Gravidade e período --------------------------------------------
    classificacao = get.get("classificacao", "")
    if classificacao not in CLASSIFICACOES:
        classificacao = ""

    mes_inicio = inteiro_valido(get.get("mes_inicio"), primeiro_mes, primeiro_mes, ultimo_mes)
    mes_fim = inteiro_valido(get.get("mes_fim"), ultimo_mes, primeiro_mes, ultimo_mes)
    if mes_inicio > mes_fim:
        mes_inicio, mes_fim = mes_fim, mes_inicio

    # --- Filtros avançados ----------------------------------------------
    escolhas, campos_avancados = {}, []
    for nome, (coluna, rotulo) in AVANCADOS.items():
        vazio = "Todas"
        if nome == "delegacia":
            # a lista de delegacias depende da regional (como município depende do estado)
            regional = escolhas["regional"]
            opcoes = sorted(df.loc[df["regional"] == regional, "delegacia"].unique()) if regional else []
            if not regional:
                vazio = "Escolha uma regional antes"
        else:
            opcoes = sorted(df[coluna].unique())
        valor = get.get(nome, "")
        if valor not in opcoes:
            valor = ""
        escolhas[nome] = valor
        campos_avancados.append({
            "nome": nome, "rotulo": rotulo, "opcoes": opcoes, "valor": valor, "vazio": vazio,
            "recarrega": nome == "regional",  # trocar a regional recarrega as delegacias
            "desativado": not opcoes,
        })

    # --- Parâmetros da URL (só o que foge do padrão) ----------------------
    parametros = {"uf": uf, "municipio": municipio, "br": br or "",
                  "trecho": "" if trecho is None else trecho,
                  "classificacao": classificacao, **escolhas}
    if mes_inicio != primeiro_mes:
        parametros["mes_inicio"] = mes_inicio
    if mes_fim != ultimo_mes:
        parametros["mes_fim"] = mes_fim
    parametros = {chave: valor for chave, valor in parametros.items() if valor != ""}

    # --- Textos do cabeçalho ----------------------------------------------
    if municipio:
        local = f"{municipio.title()} - {uf}"
    elif uf:
        local = ESTADOS[uf]
    else:
        local = "Brasil"
    if br:
        local += f" · BR-{br}"
    if trecho is not None:
        local += f" · km {trecho} a {trecho + 10}"
    if mes_inicio == mes_fim:
        texto_periodo = f"{MESES[mes_inicio - 1]} de {ANO_ATUAL}"
    else:
        texto_periodo = f"{MESES[mes_inicio - 1]} a {MESES[mes_fim - 1]} de {ANO_ATUAL}"
    descricao = [classificacao or "Todos os acidentes"] + [valor for valor in escolhas.values() if valor]

    return {
        # escolhas atuais
        "uf": uf, "municipio": municipio, "br": br, "trecho": trecho,
        "trecho_fim": None if trecho is None else trecho + 10,
        "classificacao": classificacao, "mes_inicio": mes_inicio, "mes_fim": mes_fim,
        "meses_do_periodo": list(range(mes_inicio, mes_fim + 1)),
        "colunas_filtro": [(AVANCADOS[nome][0], valor) for nome, valor in escolhas.items() if valor],
        # opções dos menus
        "estados": sorted((nome, sigla) for sigla, nome in ESTADOS.items()),
        "municipios": municipios,
        "rodovias": rodovias,
        "classificacoes": CLASSIFICACOES,
        "meses": [(m, MESES[m - 1]) for m in range(primeiro_mes, ultimo_mes + 1)],
        "avancados": campos_avancados,
        "avancados_ativos": sum(1 for valor in escolhas.values() if valor),
        # textos e links
        "local": local,
        "texto_periodo": texto_periodo,
        "descricao_filtro": " · ".join(descricao),
        "filtro_ativo": bool(parametros),
        "parametros": parametros,
    }


def link(f, rota, **mudancas):
    """
    Monta o endereço de uma aba mantendo os filtros atuais. Exemplo:
    link(f, "index", br=101, trecho=60) -> "/?uf=PE&br=101&trecho=60".
    Passar None tira o filtro.
    """
    parametros = {**f["parametros"], **mudancas}
    parametros = {chave: valor for chave, valor in parametros.items() if valor not in ("", None)}
    return reverse(rota) + ("?" + urlencode(parametros) if parametros else "")


def recortar(df, f):
    """
    Aplica os filtros. Devolve (recorte, comparacao, nome_comparacao): a
    comparação é o nível acima (Brasil ou estado), usada nos percentuais.
    """
    base = df[df["mes"].between(f["mes_inicio"], f["mes_fim"])]
    if f["br"]:
        base = base[base["br"] == f["br"]]
    if f["trecho"] is not None:
        base = base[base["trecho_km"] == f["trecho"]]
    if f["classificacao"]:
        base = base[base["classificacao_acidente"] == f["classificacao"]]
    for coluna, valor in f["colunas_filtro"]:
        base = base[base[coluna] == valor]

    na_rodovia = f" na BR-{f['br']}" if f["br"] else ""
    recorte, comparacao, nome_comparacao = base, None, ""
    if f["uf"]:
        comparacao, nome_comparacao = recorte, "do Brasil" + na_rodovia
        recorte = recorte[recorte["uf"] == f["uf"]]
    if f["municipio"]:
        comparacao, nome_comparacao = recorte, "do estado" + na_rodovia
        recorte = recorte[recorte["municipio"] == f["municipio"]]
    return recorte, comparacao, nome_comparacao
