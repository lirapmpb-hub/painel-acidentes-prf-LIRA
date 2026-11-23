"""
Cache das páginas do painel.

Os dados só mudam a cada deploy, então a mesma URL (aba + filtros) sempre gera
a mesma página. Guardamos o HTML pronto na memória do servidor: a primeira
visita a um filtro calcula tudo; as seguintes saem na hora.
"""
import threading
from functools import wraps
from urllib.parse import urlencode

from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import resolve

DURACAO = 60 * 60 * 24  # o cache some de qualquer jeito quando o servidor reinicia


def chave_da_pagina(request):
    """A chave é o caminho + os filtros em ordem fixa (a ordem na URL não importa)."""
    filtros = sorted((k, v) for k in request.GET for v in request.GET.getlist(k) if v != "")
    return "pagina:" + request.path + "?" + urlencode(filtros)


def em_cache(view):
    @wraps(view)
    def com_cache(request, *args, **kwargs):
        if request.method != "GET":
            return view(request, *args, **kwargs)
        chave = chave_da_pagina(request)
        guardado = cache.get(chave)
        if guardado is not None:
            return HttpResponse(guardado, content_type="text/html; charset=utf-8")
        resposta = view(request, *args, **kwargs)
        if resposta.status_code == 200 and not resposta.streaming:
            cache.set(chave, resposta.content, DURACAO)
        return resposta
    return com_cache


# Páginas montadas assim que o servidor liga, antes da primeira visita:
# cada aba sem filtro e com o filtro da Paraíba.
# As duas primeiras são montadas antes de aceitar visitas: juntas, usam todos os
# tipos de gráfico do painel, então importam tudo que as outras páginas precisam.
PAGINAS_INICIAIS = [
    "/", "/condicoes/",
    "/?uf=PB", "/trechos/", "/vitimas/", "/estrutura/", "/anos/",
    "/condicoes/?uf=PB", "/trechos/?uf=PB", "/vitimas/?uf=PB", "/estrutura/?uf=PB", "/anos/?uf=PB",
]


# Sinal de "pode atender": fica desligado enquanto o aquecimento importa os módulos.
# Começa ligado, para o painel funcionar normalmente quando não há aquecimento
# (testes, manage.py, etc.).
_modulos_prontos = threading.Event()
_modulos_prontos.set()
ESPERA_MAXIMA = 600  # segundos


class EsperarAquecimento:
    """
    Middleware: segura as visitas até o aquecimento terminar de importar os módulos.

    Sem isto, uma visita que chega enquanto a thread de aquecimento ainda importa
    pandas, Plotly e as URLs tenta importar os mesmos módulos ao mesmo tempo, e o
    Python trava as duas threads (deadlock de importação). No plano gratuito do
    Render, com 0,1 CPU, essas importações levam bem mais que no computador.
    Fica depois do WhiteNoise, então o brasão e os outros estáticos não esperam.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _modulos_prontos.wait(ESPERA_MAXIMA)
        return self.get_response(request)


def montar(url, fabrica):
    try:
        resolve(url.split("?")[0]).func(fabrica.get(url))
    except Exception as erro:  # uma página com problema não impede as outras
        print(f"[aquecer] {url}: {erro}", flush=True)


def _aquecer():
    fabrica = RequestFactory()
    try:
        # As duas primeiras páginas importam tudo que as outras usam
        for url in PAGINAS_INICIAIS[:2]:
            montar(url, fabrica)
    finally:
        _modulos_prontos.set()  # libera as visitas, mesmo se algo deu errado
    print("[aquecer] módulos importados, atendendo visitas", flush=True)

    from .dados import carregar_todos

    carregar_todos()
    for url in PAGINAS_INICIAIS[2:]:
        montar(url, fabrica)
    print(f"[aquecer] {len(PAGINAS_INICIAIS)} páginas prontas", flush=True)


def aquecer():
    """
    Chamado quando o servidor liga (config/wsgi.py). Roda tudo em segundo plano,
    para o servidor ligar na hora (o gunicorn derruba um processo que demora
    demais para ligar). As visitas que chegarem antes esperam no middleware acima.
    """
    _modulos_prontos.clear()
    threading.Thread(target=_aquecer, name="aquecer-cache", daemon=True).start()
