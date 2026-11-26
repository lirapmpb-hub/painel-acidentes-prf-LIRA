from django.urls import path
from django.views.generic import RedirectView

from . import views
from .cache_paginas import em_cache


def antiga(nova):
    """Endereço de uma aba antiga: redireciona para a nova, mantendo os filtros."""
    return RedirectView.as_view(pattern_name=nova, query_string=True, permanent=True)


# em_cache: a página pronta fica guardada na memória (ver cache_paginas.py).
# O download em CSV não entra no cache, porque pode ser grande.
urlpatterns = [
    path("", em_cache(views.index), name="index"),
    path("onde-agir/", em_cache(views.prioridades), name="prioridades"),
    path("por-que/", em_cache(views.por_que), name="por_que"),
    path("acompanhar/", em_cache(views.acompanhar), name="acompanhar"),
    path("estrutura/", em_cache(views.estrutura), name="estrutura"),
    path("ficha/", em_cache(views.ficha), name="ficha"),
    path("exportar/", views.exportar, name="exportar"),

    # Abas que foram juntadas: os links antigos continuam funcionando
    path("trechos/", antiga("prioridades")),
    path("condicoes/", antiga("por_que")),
    path("vitimas/", antiga("por_que")),
    path("anos/", antiga("acompanhar")),
    path("metas/", antiga("acompanhar")),
]
