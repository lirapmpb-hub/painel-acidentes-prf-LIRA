"""
Download: os acidentes do filtro atual, com as 30 colunas originais da PRF.
"""
from django.http import HttpResponse
from django.utils.text import slugify

from ..dados import ANO_ATUAL, COLUNAS_ORIGINAIS
from .comum import preparar


def exportar(request):
    f, recorte, _, _ = preparar(request)
    nome = slugify(f"acidentes prf {ANO_ATUAL} {f['local']}")
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{nome}.csv"'
    resposta.write("﻿")  # marca BOM: faz o Excel reconhecer os acentos
    tabela = recorte[COLUNAS_ORIGINAIS].copy()
    for coluna in tabela.select_dtypes("float").columns:
        valores = tabela[coluna].dropna()
        if (valores % 1 == 0).all():  # só números inteiros: 211.0 vira 211
            tabela[coluna] = tabela[coluna].astype("Int64")
    tabela.to_csv(resposta, sep=";", decimal=",", index=False)
    return resposta
