"""
Áreas do mapa: municípios, regiões imediatas e intermediárias do IBGE.

As malhas (contornos) e a lista de municípios vêm do IBGE e ficam em data/geo
(ver o comando baixar_malhas). Aqui ligamos cada acidente da PRF ao código
IBGE do seu município, pelo nome (a PRF usa nomes em maiúsculas e sem acento).
"""
import json
import re
import unicodedata
from functools import lru_cache

from django.conf import settings

PASTA_GEO = settings.BASE_DIR / "data" / "geo"

# nível do mapa -> parâmetro "intrarregiao" da API de malhas do IBGE
# (municípios vêm por estado; as regiões, só do país inteiro, separadas por estado)
NIVEIS = {"municipio": "municipio", "imediata": "regiao-imediata", "intermediaria": "regiao-intermediaria"}
NOMES_NIVEIS = {"municipio": "Município", "imediata": "Região imediata", "intermediaria": "Região intermediária",
                "estado": "Estado"}

# Nomes que a PRF escreve diferente do IBGE (depois de normalizar): (UF, nome PRF) -> nome IBGE.
# Com eles, 99,99% dos acidentes de 2025-2026 ficam ligados a um município (100% na PB).
APELIDOS = {
    ("MT", "SANTOANTONIODOLEVERGER"): "SANTOANTONIODELEVERGER",
    ("RN", "ACU"): "ASSU",
    ("BA", "MUQUEMDESAOFRANCISCO"): "MUQUEMDOSAOFRANCISCO",
    ("PE", "BELEMDESAOFRANCISCO"): "BELEMDOSAOFRANCISCO",
    ("TO", "FORTALEZADOTABOCAO"): "TABOCAO",
    ("BA", "SANTATERESINHA"): "SANTATEREZINHA",
    ("RN", "ARES"): "AREZ",
    ("RN", "AUGUSTOSEVERO"): "CAMPOGRANDE",
}


def arquivo_malha(uf, nivel):
    return PASTA_GEO / f"{uf}-{nivel}.json"


def normalizar(nome):
    """'Olho d'Água' e 'OLHO DAGUA' viram 'OLHODAGUA'."""
    sem_acento = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z]", "", sem_acento.upper())


def disponivel():
    return (PASTA_GEO / "municipios.json").exists()


@lru_cache(maxsize=None)
def municipios():
    """{código IBGE: {nome, uf, imediata, nome_imediata, intermediaria, nome_intermediaria}}"""
    return json.loads((PASTA_GEO / "municipios.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def estados():
    """{código IBGE do estado: sigla}"""
    return json.loads((PASTA_GEO / "estados.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def malha(uf, nivel):
    """GeoJSON de um estado num nível (ou do Brasil por estado, com uf="BR", nivel="estado")."""
    return json.loads(arquivo_malha(uf, nivel).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _codigo_por_nome():
    tabela = {(m["uf"], normalizar(m["nome"])): codigo for codigo, m in municipios().items()}
    for (uf, apelido), oficial in APELIDOS.items():
        if (uf, oficial) in tabela:
            tabela[(uf, apelido)] = tabela[(uf, oficial)]
    return tabela


def codigo_do_municipio(uf, nome):
    return _codigo_por_nome().get((uf, normalizar(nome)))


def limites(geojson):
    """(lat_min, lat_max, lon_min, lon_max) de todas as áreas."""
    lats, lons = [], []

    def percorrer(coords):
        if isinstance(coords[0], (int, float)):
            lons.append(coords[0])
            lats.append(coords[1])
        else:
            for c in coords:
                percorrer(c)
    for feature in geojson["features"]:
        percorrer(feature["geometry"]["coordinates"])
    return min(lats), max(lats), min(lons), max(lons)
