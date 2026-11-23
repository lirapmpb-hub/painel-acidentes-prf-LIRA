from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("condicoes/", views.condicoes, name="condicoes"),
    path("trechos/", views.trechos, name="trechos"),
    path("vitimas/", views.vitimas, name="vitimas"),
    path("estrutura/", views.estrutura, name="estrutura"),
    path("anos/", views.anos, name="anos"),
    path("exportar/", views.exportar, name="exportar"),
]
