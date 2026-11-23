"""
Cache das páginas do painel.

Os dados só mudam a cada deploy, então a mesma URL (aba + filtros) sempre gera
a mesma página. Guardamos o HTML pronto na memória do servidor: a primeira
visita a um filtro calcula tudo; as seguintes saem na hora.
"""
from functools import wraps
from urllib.parse import urlencode

from django.core.cache import cache
from django.http import HttpResponse

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
