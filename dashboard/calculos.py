"""
Medidas e formatação reaproveitadas por todas as páginas (equivale às
medidas DAX do Power BI).
"""
import pandas as pd

# Abaixo deste número de acidentes, o índice de gravidade oscila demais
# (1 morte em 3 acidentes daria 33,3) e não entra em destaques e rankings.
MINIMO_PARA_INDICE = 30


def numero(valor):
    """Formata 1234567 como 1.234.567 (padrão brasileiro)."""
    return f"{valor:,.0f}".replace(",", ".")


def decimal(valor):
    """Formata 8.456 como 8,5."""
    return f"{valor:.1f}".replace(".", ",")


def media_mensal(total, meses):
    media = total / meses
    return decimal(media) if 0 < media < 10 else numero(media)


def percentual(parte, todo):
    return "0%" if todo == 0 else decimal(parte / todo * 100) + "%"


def variacao(atual, anterior):
    """Variação percentual com sinal: +12,3% ou -4,0%."""
    if not anterior:
        return "–"
    v = (atual - anterior) / anterior * 100
    return ("+" if v > 0 else "") + decimal(v) + "%"


def gravidade(tabela):
    """Índice de gravidade: mortos a cada 100 acidentes."""
    return 0 if len(tabela) == 0 else tabela["mortos"].sum() / len(tabela) * 100


def inteiro_valido(texto, padrao, minimo, maximo):
    """Converte o texto recebido do formulário em número dentro dos limites."""
    try:
        valor = int(texto)
    except (TypeError, ValueError):
        return padrao
    return valor if minimo <= valor <= maximo else padrao


def agregar(recorte, chaves):
    """Agrupa os acidentes por uma ou mais colunas e calcula as medidas principais."""
    tabela = (
        recorte.groupby(chaves)
        .agg(acidentes=("id", "count"), mortos=("mortos", "sum"),
             feridos_graves=("feridos_graves", "sum"))
        .reset_index()
    )
    tabela["indice"] = tabela["mortos"] / tabela["acidentes"] * 100
    return tabela


def tabela_gravidade(recorte, coluna):
    """Acidentes, mortos e índice de gravidade de cada valor de uma coluna."""
    return agregar(recorte, coluna).rename(columns={coluna: "rotulo"})


def candidatos(tabela, n, medidas=("acidentes", "mortos"), chave="rotulo"):
    """
    Junta os n primeiros de cada medida (e do índice, com acidentes suficientes).
    Assim o gráfico pode mostrar os 10 primeiros em qualquer ordem que o
    usuário escolher (por acidentes, mortos ou letalidade).
    """
    partes = [tabela.nlargest(n, m) for m in medidas]
    if "indice" in tabela:
        partes.append(tabela[tabela["acidentes"] >= MINIMO_PARA_INDICE].nlargest(n, "indice"))
    return pd.concat(partes).drop_duplicates(subset=chave).reset_index(drop=True)


def separar_valores(recorte, coluna, separador=";"):
    """
    Algumas colunas guardam vários valores juntos ("Aclive;Curva"). Aqui cada
    valor vira uma linha; o mesmo acidente passa a contar em cada um deles.
    """
    separado = recorte.assign(**{coluna: recorte[coluna].str.split(separador)}).explode(coluna)
    separado[coluna] = separado[coluna].str.strip()
    return separado[separado[coluna] != ""]


def faixa_veiculos(quantidade):
    if quantidade >= 5:
        return "5 ou mais"
    return f"{quantidade} veículo" + ("s" if quantidade != 1 else "")


FAIXAS_VEICULOS = ["1 veículo", "2 veículos", "3 veículos", "4 veículos", "5 ou mais"]


def vazio_como_zero(tabela, ordem, coluna="rotulo"):
    """Coloca as categorias na ordem dada; as que faltarem entram com zero."""
    tabela = tabela.set_index(coluna).reindex(ordem)
    tabela[["acidentes", "mortos", "feridos_graves"]] = tabela[["acidentes", "mortos", "feridos_graves"]].fillna(0)
    tabela["indice"] = tabela["indice"].fillna(0)
    return tabela.rename_axis(coluna).reset_index()


def sem_desconhecidos(tabela):
    """Tira categorias como "Ignorado" e "Não informado" dos destaques."""
    desconhecidos = {"não informado", "ignorado", "ignorada", "(null)"}
    return tabela[~tabela["rotulo"].astype(str).str.lower().isin(desconhecidos)]
