"""
Camada de lógica do painel (equivale às medidas DAX do Power BI).

Um arquivo por aba. Todas começam do mesmo jeito: leem os filtros da URL e
recortam os acidentes (ver comum.preparar e filtros.py). Depois calculam as
tabelas e os gráficos daquela aba.

    panorama.py    Panorama: qual é a situação?
    onde_agir.py   Onde agir: onde e quando agir?
    por_que.py     Por quê: o que faz os acidentes matarem?
    acompanhar.py  Acompanhar: estamos melhorando? (metas, antes/depois, anos)
    estrutura.py   Estrutura PRF: quem cobre cada área?
    ficha.py       Ficha do trecho (aberta a partir de Onde agir)
    exportar.py    Download em CSV
    comum.py       peças usadas por todas as abas
"""
from .acompanhar import acompanhar
from .estrutura import estrutura
from .exportar import exportar
from .ficha import ficha
from .onde_agir import prioridades
from .panorama import index
from .por_que import por_que

__all__ = ["acompanhar", "estrutura", "exportar", "ficha", "index", "por_que", "prioridades"]
