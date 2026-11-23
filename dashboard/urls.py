from django.urls import path

from . import views
from .cache_paginas import em_cache

# em_cache: a página pronta fica guardada na memória (ver cache_paginas.py).
# O download em CSV não entra no cache, porque pode ser grande.
urlpatterns = [
    path("", em_cache(views.index), name="index"),
    path("onde-agir/", em_cache(views.prioridades), name="prioridades"),
    path("condicoes/", em_cache(views.condicoes), name="condicoes"),
    path("trechos/", em_cache(views.trechos), name="trechos"),
    path("vitimas/", em_cache(views.vitimas), name="vitimas"),
    path("estrutura/", em_cache(views.estrutura), name="estrutura"),
    path("anos/", em_cache(views.anos), name="anos"),
    path("metas/", em_cache(views.metas), name="metas"),
    path("ficha/", em_cache(views.ficha), name="ficha"),
    path("exportar/", views.exportar, name="exportar"),
]
