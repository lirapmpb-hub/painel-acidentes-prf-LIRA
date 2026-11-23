"""
Cache das páginas do painel.

Os dados só mudam a cada deploy, então a mesma URL (aba + filtros) sempre gera
a mesma página. Guardamos o HTML pronto, já comprimido em gzip, na memória do
servidor: a primeira visita a um filtro calcula tudo; as seguintes saem na hora,
sem nem precisar comprimir de novo (o servidor gratuito tem pouquíssima CPU).
"""
import gzip
import re
from functools import wraps
from urllib.parse import urlencode

from django.core.cache import cache
from django.http import HttpResponse
from django.utils.cache import patch_vary_headers

DURACAO = 60 * 60 * 24  # o cache some de qualquer jeito quando o servidor reinicia
ACEITA_GZIP = re.compile(r"\bgzip\b")


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
        comprimido = cache.get(chave)
        if comprimido is None:
            resposta = view(request, *args, **kwargs)
            if resposta.status_code != 200 or resposta.streaming:
                return resposta
            comprimido = gzip.compress(resposta.content, compresslevel=6)
            cache.set(chave, comprimido, DURACAO)

        if ACEITA_GZIP.search(request.META.get("HTTP_ACCEPT_ENCODING", "")):
            resposta = HttpResponse(comprimido, content_type="text/html; charset=utf-8")
            resposta["Content-Encoding"] = "gzip"  # o GZipMiddleware vê isto e não recomprime
        else:  # navegador raro que não aceita gzip
            resposta = HttpResponse(gzip.decompress(comprimido), content_type="text/html; charset=utf-8")
        patch_vary_headers(resposta, ("Accept-Encoding",))
        return resposta
    return com_cache
