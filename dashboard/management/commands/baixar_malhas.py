"""
Baixa do IBGE as malhas (contornos) usadas no mapa por áreas e a lista de
municípios com suas regiões imediatas e intermediárias.

Uso: python manage.py baixar_malhas
Roda uma vez só (os arquivos ficam em data/geo e vão para o repositório);
não roda no deploy, para o site não depender do IBGE estar no ar.

Fontes (API pública de serviços de dados do IBGE):
  https://servicodados.ibge.gov.br/api/docs/malhas?versao=3
  https://servicodados.ibge.gov.br/api/docs/localidades
"""
import json
import time
import urllib.request

from django.core.management.base import BaseCommand

from dashboard.dados import ESTADOS
from dashboard.geo import NIVEIS, PASTA_GEO, arquivo_malha

API = "https://servicodados.ibge.gov.br/api"
CABECALHOS = {"User-Agent": "painel-acidentes-prf/1.0", "Accept": "application/json"}


def baixar(url):
    for tentativa in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=CABECALHOS), timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - tenta de novo (o IBGE às vezes demora)
            if tentativa == 3:
                raise
            time.sleep(2 + tentativa * 3)


def arredondar(geometria, casas=4):
    """Coordenadas com 4 casas (~11 m): bem menor e sem diferença visível no mapa."""
    def r(coords):
        if isinstance(coords[0], (int, float)):
            return [round(coords[0], casas), round(coords[1], casas)]
        return [r(c) for c in coords]
    geometria["coordinates"] = r(geometria["coordinates"])
    return geometria


def gravar(caminho, malha):
    for feature in malha["features"]:
        arredondar(feature["geometry"])
        feature["properties"] = {"codarea": feature["properties"]["codarea"]}
    caminho.write_text(json.dumps(malha, separators=(",", ":")), encoding="utf-8")


class Command(BaseCommand):
    help = "Baixa do IBGE as malhas de municípios/regiões e a lista de municípios (data/geo)"

    def handle(self, *args, **options):
        PASTA_GEO.mkdir(parents=True, exist_ok=True)

        # Municípios com região imediata e intermediária
        municipios = {}
        for m in baixar(f"{API}/v1/localidades/municipios"):
            imediata = m["regiao-imediata"]
            intermediaria = imediata["regiao-intermediaria"]
            municipios[str(m["id"])] = {
                "nome": m["nome"], "uf": intermediaria["UF"]["sigla"],
                "imediata": str(imediata["id"]), "nome_imediata": imediata["nome"],
                "intermediaria": str(intermediaria["id"]), "nome_intermediaria": intermediaria["nome"],
            }
        (PASTA_GEO / "municipios.json").write_text(
            json.dumps(municipios, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        self.stdout.write(f"municipios.json: {len(municipios)} municípios")

        # Estados do Brasil (para o mapa sem estado escolhido)
        estados = {str(e["id"]): e["sigla"] for e in baixar(f"{API}/v1/localidades/estados")}
        (PASTA_GEO / "estados.json").write_text(json.dumps(estados), encoding="utf-8")
        gravar(arquivo_malha("BR", "estado"),
               baixar(f"{API}/v3/malhas/paises/BR?formato=application/vnd.geo%2Bjson&qualidade=minima&intrarregiao=UF"))

        # Municípios: uma malha por estado
        for uf in sorted(ESTADOS):
            url = (f"{API}/v3/malhas/estados/{uf}?formato=application/vnd.geo%2Bjson"
                   f"&qualidade=minima&intrarregiao=municipio")
            gravar(arquivo_malha(uf, "municipio"), baixar(url))
            self.stdout.write(f"{uf}: municípios")

        # Regiões imediatas e intermediárias: a API só entrega para o país inteiro;
        # separamos por estado (os dois primeiros dígitos do código são o estado).
        for nivel in ("imediata", "intermediaria"):
            url = (f"{API}/v3/malhas/paises/BR?formato=application/vnd.geo%2Bjson"
                   f"&qualidade=minima&intrarregiao={NIVEIS[nivel]}")
            pais = baixar(url)
            por_uf = {}
            for feature in pais["features"]:
                uf = estados[feature["properties"]["codarea"][:2]]
                por_uf.setdefault(uf, []).append(feature)
            for uf, features in por_uf.items():
                gravar(arquivo_malha(uf, nivel), {"type": "FeatureCollection", "features": features})
            self.stdout.write(f"regiões {nivel}: {len(pais['features'])} em {len(por_uf)} estados")
        tamanho = sum(a.stat().st_size for a in PASTA_GEO.glob("*.json")) / 1e6
        self.stdout.write(f"Pronto: {tamanho:.1f} MB em {PASTA_GEO}")
